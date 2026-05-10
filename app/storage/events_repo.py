import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import numpy as np

from app.core.alert_event import AlertEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    timestamp       REAL    NOT NULL,
    kind            TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    detail          TEXT,
    zone_name       TEXT,
    bbox_x1         INTEGER,
    bbox_y1         INTEGER,
    bbox_x2         INTEGER,
    bbox_y2         INTEGER,
    clip_path       TEXT,
    snapshot_path   TEXT,
    face_embedding  BLOB
);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);
"""


class EventsRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            # Migration: додати колонки, які з'явились пізніше (для існуючих БД).
            cols = {r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()}
            if "face_embedding" not in cols:
                conn.execute("ALTER TABLE events ADD COLUMN face_embedding BLOB")
            if "snapshot_path" not in cols:
                conn.execute("ALTER TABLE events ADD COLUMN snapshot_path TEXT")

    def save(self, ev: AlertEvent) -> None:
        bbox = ev.detection_bbox or (None, None, None, None)
        clip_path_str = str(ev.clip_path) if ev.clip_path is not None else None
        snap_str = str(ev.snapshot_path) if ev.snapshot_path is not None else None
        emb_blob: bytes | None = None
        if ev.face_embedding is not None:
            emb_blob = ev.face_embedding.astype(np.float32).tobytes()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO events
                (id, timestamp, kind, title, detail, zone_name,
                 bbox_x1, bbox_y1, bbox_x2, bbox_y2, clip_path,
                 snapshot_path, face_embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ev.id, ev.timestamp, ev.kind, ev.title, ev.detail,
                    ev.zone_name, bbox[0], bbox[1], bbox[2], bbox[3],
                    clip_path_str, snap_str, emb_blob,
                ),
            )

    def query(
        self,
        from_ts: float | None = None,
        to_ts: float | None = None,
        kind: str | None = None,
        only_with_clip: bool = False,
        limit: int = 500,
    ) -> list[AlertEvent]:
        clauses: list[str] = []
        params: list = []
        if from_ts is not None:
            clauses.append("timestamp >= ?")
            params.append(from_ts)
        if to_ts is not None:
            clauses.append("timestamp <= ?")
            params.append(to_ts)
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if only_with_clip:
            clauses.append("clip_path IS NOT NULL")
        where = " AND ".join(clauses) if clauses else "1=1"
        sql = f"SELECT * FROM events WHERE {where} ORDER BY timestamp DESC LIMIT ?"
        params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_event(r) for r in rows]

    def distinct_kinds(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT kind FROM events ORDER BY kind"
            ).fetchall()
        return [r["kind"] for r in rows]

    def count(self, since_ts: float | None = None) -> int:
        sql = "SELECT COUNT(*) FROM events"
        params: list = []
        if since_ts is not None:
            sql += " WHERE timestamp >= ?"
            params.append(since_ts)
        with self._connect() as conn:
            return conn.execute(sql, params).fetchone()[0]

    def count_by_kind(self, since_ts: float | None = None) -> dict[str, int]:
        sql = "SELECT kind, COUNT(*) FROM events"
        params: list = []
        if since_ts is not None:
            sql += " WHERE timestamp >= ?"
            params.append(since_ts)
        sql += " GROUP BY kind ORDER BY COUNT(*) DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return {r[0]: int(r[1]) for r in rows}

    def count_by_zone(self, since_ts: float | None = None) -> dict[str, int]:
        sql = "SELECT zone_name, COUNT(*) FROM events WHERE zone_name IS NOT NULL"
        params: list = []
        if since_ts is not None:
            sql += " AND timestamp >= ?"
            params.append(since_ts)
        sql += " GROUP BY zone_name ORDER BY COUNT(*) DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return {r[0]: int(r[1]) for r in rows}

    def count_by_hour(
        self, from_ts: float, until_ts: float
    ) -> list[tuple[float, int]]:
        sql = """
        SELECT CAST(timestamp / 3600 AS INTEGER) * 3600 AS hour_bucket, COUNT(*)
        FROM events
        WHERE timestamp >= ? AND timestamp < ?
        GROUP BY hour_bucket
        ORDER BY hour_bucket
        """
        with self._connect() as conn:
            rows = conn.execute(sql, (from_ts, until_ts)).fetchall()
        return [(float(r[0]), int(r[1])) for r in rows]

    def delete_all(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM events")

    def find_by_embedding(
        self,
        query: np.ndarray,
        threshold: float = 0.4,
        limit: int = 200,
    ) -> list[tuple[AlertEvent, float]]:
        """Шукає події з face_embedding, що мають cosine similarity ≥ threshold
        до `query`. Повертає список (event, similarity), відсортований за
        спаданням схожості. Embedding'и нормалізовані → dot product = cosine."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE face_embedding IS NOT NULL "
                "ORDER BY timestamp DESC"
            ).fetchall()
        if not rows:
            return []
        try:
            embs = np.stack([
                np.frombuffer(r["face_embedding"], dtype=np.float32) for r in rows
            ])
        except Exception:
            return []
        if embs.shape[1] != query.shape[0]:
            return []
        sims = embs @ query.astype(np.float32)
        matches: list[tuple[AlertEvent, float]] = []
        for r, sim in zip(rows, sims):
            sim_f = float(sim)
            if sim_f >= threshold:
                matches.append((self._row_to_event(r), sim_f))
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:limit]

    @staticmethod
    def _row_to_event(r: sqlite3.Row) -> AlertEvent:
        bbox = None
        if r["bbox_x1"] is not None:
            bbox = (r["bbox_x1"], r["bbox_y1"], r["bbox_x2"], r["bbox_y2"])
        clip = Path(r["clip_path"]) if r["clip_path"] else None
        try:
            snap_str = r["snapshot_path"]
        except (IndexError, KeyError):
            snap_str = None
        snap = Path(snap_str) if snap_str else None
        try:
            emb_blob = r["face_embedding"]
        except (IndexError, KeyError):
            emb_blob = None
        emb = np.frombuffer(emb_blob, dtype=np.float32) if emb_blob else None
        return AlertEvent(
            id=r["id"],
            timestamp=r["timestamp"],
            kind=r["kind"],
            title=r["title"],
            detail=r["detail"] or "",
            zone_name=r["zone_name"],
            detection_bbox=bbox,
            clip_path=clip,
            snapshot_path=snap,
            face_embedding=emb,
        )
