import time
import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

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
    def evaluate(self, result: ProcessingResult, ts: float) -> list[AlertEvent]:
        unknown = [d for d in result.detections if d.label == "unknown_face"]
        if not unknown:
            return []
        d = unknown[0]
        return [
            AlertEvent(
                id=uuid.uuid4().hex[:12],
                timestamp=ts,
                kind="unknown_face",
                title="Незнакомое лицо",
                detail=f"в кадре: {len(unknown)}",
                detection_bbox=d.bbox,
            )
        ]


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
                    title="Вторжение в зону",
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
    """Stateful rule. Tracks how long each (track_id, zone) pair stays in a zone.
    Fires once per pair when threshold exceeded. Stale entries cleaned up by TTL."""

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
                        title="Долгое нахождение в зоне",
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
    ) -> None:
        super().__init__()
        self._clip = clip_manager
        self._sound = sound
        self._tts = tts
        self._repo = repository
        self._settings = settings or Settings()
        self._cooldown = cooldown_seconds
        self._rules: list[AlertRule] = rules or [
            UnknownFaceRule(), ZoneIntrusionRule(), LoiteringRule(threshold_seconds=5.0),
        ]
        self._last_fired: dict[str, float] = {}

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
        if self._settings.beep_enabled:
            self._sound.beep()
        if self._settings.tts_enabled:
            self._tts.say(f"{ev.title}. {ev.detail}")
        try:
            self._repo.save(ev)
        except Exception:
            pass
        self.alert_fired.emit(ev)

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
