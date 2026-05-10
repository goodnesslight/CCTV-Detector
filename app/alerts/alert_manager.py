import time
import uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import cv2

from PySide6.QtCore import QObject, Signal

from app.alerts.clip_manager import ClipManager
from app.alerts.sound import SoundPlayer, TTSPlayer
from app.core.alert_event import AlertEvent
from app.core.settings import Settings
from app.core.types import Detection, ProcessingResult
from app.storage.events_repo import EventsRepository


@runtime_checkable
class AlertRule(Protocol):
    def evaluate(self, result: ProcessingResult, ts: float) -> list[AlertEvent]: ...


class UnknownFaceRule:
    """Stateful temporal smoothing для алерту 'Незнайоме обличчя'.

    Алерт спрацьовує лише якщо незнайоме обличчя було в принаймні `min_hits`
    з останніх `window` кадрів. Захищає від хибних спрацьовувань коли
    знайома особа на 1-3 кадрах класифікується як незнайома (поганий ракурс
    / motion blur при поверненні в кадр)."""

    def __init__(self, window: int = 10, min_hits: int = 10) -> None:
        self._window = window
        self._min_hits = min_hits
        self._history: deque[bool] = deque(maxlen=window)

    def evaluate(self, result: ProcessingResult, ts: float) -> list[AlertEvent]:
        unknown = [d for d in result.detections if d.label == "unknown_face"]
        self._history.append(bool(unknown))

        if len(self._history) < self._window:
            return []
        if sum(self._history) < self._min_hits:
            return []
        if not unknown:
            return []

        d = unknown[0]
        return [
            AlertEvent(
                id=uuid.uuid4().hex[:12],
                timestamp=ts,
                kind="unknown_face",
                title="Незнайоме обличчя",
                detail=f"в кадрі: {len(unknown)}",
                detection_bbox=d.bbox,
                face_embedding=d.face_embedding,
            )
        ]

    def reset(self) -> None:
        self._history.clear()


class ZoneIntrusionRule:
    def evaluate(self, result: ProcessingResult, ts: float) -> list[AlertEvent]:
        by_zone: dict[str, list[Detection]] = {}
        for d in result.detections:
            if d.zone_name is not None:
                by_zone.setdefault(d.zone_name, []).append(d)
        events: list[AlertEvent] = []
        for zone_name, dets in by_zone.items():
            d = dets[0]
            events.append(
                AlertEvent(
                    id=uuid.uuid4().hex[:12],
                    timestamp=ts,
                    kind=f"zone:{zone_name}",
                    title="Вторгнення в зону",
                    detail=zone_name,
                    detection_bbox=d.bbox,
                    zone_name=zone_name,
                )
            )
        return events


@dataclass
class _TrackInZone:
    track_id: int
    zone_name: str
    enter_ts: float
    fired: bool = False


class LoiteringRule:
    """Stateful-правило. Відстежує час перебування кожної пари (track_id, zone)
    у зоні. Спрацьовує один раз на пару при перевищенні порогу. Застарілі
    записи автоматично чистяться через TTL."""

    def __init__(self, threshold_seconds: float = 5.0, ttl_seconds: float = 2.0) -> None:
        self._threshold = threshold_seconds
        self._ttl = ttl_seconds
        self._tracks: dict[tuple[int, str], _TrackInZone] = {}
        self._last_seen: dict[tuple[int, str], float] = {}

    def evaluate(self, result: ProcessingResult, ts: float) -> list[AlertEvent]:
        events: list[AlertEvent] = []
        for d in result.detections:
            if d.label != "person" or d.track_id is None or d.zone_name is None:
                continue
            key = (d.track_id, d.zone_name)
            if key not in self._tracks:
                self._tracks[key] = _TrackInZone(
                    track_id=d.track_id, zone_name=d.zone_name, enter_ts=ts,
                )
            self._last_seen[key] = ts
            entry = self._tracks[key]
            elapsed = ts - entry.enter_ts
            if not entry.fired and elapsed >= self._threshold:
                entry.fired = True
                events.append(
                    AlertEvent(
                        id=uuid.uuid4().hex[:12],
                        timestamp=ts,
                        kind=f"loitering:{d.zone_name}",
                        title="Тривале перебування в зоні",
                        detail=f"{d.zone_name} ({elapsed:.1f}с, трек #{d.track_id})",
                        detection_bbox=d.bbox,
                        zone_name=d.zone_name,
                    )
                )

        stale = [k for k, last in self._last_seen.items() if ts - last > self._ttl]
        for k in stale:
            self._tracks.pop(k, None)
            self._last_seen.pop(k, None)

        return events

    def reset(self) -> None:
        self._tracks.clear()
        self._last_seen.clear()


class AlertManager(QObject):
    alert_fired = Signal(object)

    def __init__(
        self,
        clip_manager: ClipManager,
        sound: SoundPlayer,
        tts: TTSPlayer,
        repository: EventsRepository,
        settings: Settings | None = None,
        cooldown_seconds: float = 10.0,
        rules: list[AlertRule] | None = None,
        unknown_faces_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self._clip = clip_manager
        self._sound = sound
        self._tts = tts
        self._repo = repository
        self._settings = settings or Settings()
        self._cooldown = cooldown_seconds
        self._rules: list[AlertRule] = rules or [
            UnknownFaceRule(),
            ZoneIntrusionRule(),
            LoiteringRule(threshold_seconds=5.0),
        ]
        self._last_fired: dict[str, float] = {}
        self._unknown_faces_dir = unknown_faces_dir

    def on_frame(self, result: ProcessingResult) -> list[AlertEvent]:
        wall = time.time()
        mono = time.monotonic()
        self._clip.push_frame(result.image, wall)

        candidates: list[AlertEvent] = []
        for rule in self._rules:
            try:
                candidates.extend(rule.evaluate(result, wall))
            except Exception:
                continue

        fired: list[AlertEvent] = []
        for ev in candidates:
            last = self._last_fired.get(ev.kind, float("-inf"))
            if mono - last < self._cooldown:
                continue
            self._last_fired[ev.kind] = mono
            self._dispatch(ev, result)
            fired.append(ev)
        return fired

    def _dispatch(self, ev: AlertEvent, result: ProcessingResult) -> None:
        h, w = result.image.shape[:2]
        path = self._clip.trigger(ev.id, ev.kind, ev.timestamp, (h, w))
        if path is not None:
            ev.clip_path = path
        if ev.kind == "unknown_face" and self._unknown_faces_dir is not None:
            self._save_unknown_snapshot(ev, result)
        if self._settings.beep_enabled:
            self._sound.beep()
        if self._settings.tts_enabled:
            self._tts.say(f"{ev.title}. {ev.detail}")
        try:
            self._repo.save(ev)
        except Exception:
            pass
        self.alert_fired.emit(ev)

    def _save_unknown_snapshot(self, ev: AlertEvent, result: ProcessingResult) -> None:
        if ev.detection_bbox is None or self._unknown_faces_dir is None:
            return
        try:
            x1, y1, x2, y2 = ev.detection_bbox
            img = result.frame.image
            h, w = img.shape[:2]
            # Розширюємо bbox на 20% для контексту (волосся, плечі).
            pad_x = int((x2 - x1) * 0.2)
            pad_y = int((y2 - y1) * 0.2)
            x1c = max(0, x1 - pad_x)
            y1c = max(0, y1 - pad_y)
            x2c = min(w, x2 + pad_x)
            y2c = min(h, y2 + pad_y)
            crop = img[y1c:y2c, x1c:x2c]
            if crop.size == 0:
                return
            self._unknown_faces_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            path = self._unknown_faces_dir / f"{stamp}_{ev.id[:8]}.jpg"
            if cv2.imwrite(str(path), crop):
                ev.snapshot_path = path
        except Exception:
            pass

    def set_cooldown(self, seconds: float) -> None:
        self._cooldown = float(seconds)

    def set_loitering_threshold(self, seconds: float) -> None:
        for rule in self._rules:
            if hasattr(rule, "_threshold"):
                rule._threshold = float(seconds)

    @property
    def repository(self) -> EventsRepository:
        return self._repo

    @property
    def history(self) -> list[AlertEvent]:
        return self._repo.query(limit=500)

    def reset(self) -> None:
        self._last_fired.clear()
        self._clip.reset()
        for rule in self._rules:
            reset_fn = getattr(rule, "reset", None)
            if callable(reset_fn):
                try:
                    reset_fn()
                except Exception:
                    pass

    def shutdown(self) -> None:
        self._clip.shutdown()
        self._tts.shutdown()
