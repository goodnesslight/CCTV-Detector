import time

from app.core.types import ProcessingResult
from app.storage.persons_repo import PersonSightingsRepository


class SightingsTracker:
    """Підраховує появи відомих персон на камерах із дебаунсом.

    Якщо одну і ту саму персону не бачили довше cooldown_seconds — рахується
    нова поява. Без дебаунсу лічильник зростав би на ~30 за секунду на 30 FPS,
    що позбавляло б показник сенсу."""

    def __init__(
        self,
        repository: PersonSightingsRepository,
        cooldown_seconds: float = 30.0,
    ) -> None:
        self._repo = repository
        self._cooldown = float(cooldown_seconds)
        self._last_seen: dict[str, float] = {}

    def on_frame(self, result: ProcessingResult) -> None:
        names = {
            d.person_name for d in result.detections
            if d.label == "known_face" and d.person_name
        }
        if not names:
            return
        wall = time.time()
        mono = time.monotonic()
        for name in names:
            last = self._last_seen.get(name, float("-inf"))
            if mono - last < self._cooldown:
                continue
            self._last_seen[name] = mono
            try:
                self._repo.record_sighting(name, wall)
            except Exception:
                pass

    def set_cooldown(self, seconds: float) -> None:
        self._cooldown = float(seconds)

    def reset(self) -> None:
        self._last_seen.clear()
