import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS person_sightings (
    name        TEXT PRIMARY KEY,
    total       INTEGER NOT NULL DEFAULT 0,
    last_seen   REAL
);
"""


class PersonSightingsRepository:
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

    def record_sighting(self, name: str, ts: float) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO person_sightings (name, total, last_seen)
                VALUES (?, 1, ?)
                ON CONFLICT(name) DO UPDATE SET
                    total = total + 1,
                    last_seen = excluded.last_seen
                """,
                (name, ts),
            )

    def stats(self) -> dict[str, tuple[int, float | None]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name, total, last_seen FROM person_sightings"
            ).fetchall()
        return {r["name"]: (int(r["total"]), r["last_seen"]) for r in rows}

    def delete(self, name: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM person_sightings WHERE name = ?", (name,))
