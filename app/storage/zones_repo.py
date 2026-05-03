import json
from pathlib import Path

from app.core.zones import Zone


class ZonesRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> list[Zone]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        zones: list[Zone] = []
        for item in data:
            try:
                pts = [(int(x), int(y)) for x, y in item["points"]]
                zones.append(Zone(name=str(item["name"]), points=pts))
            except (KeyError, TypeError, ValueError):
                continue
        return zones

    def save(self, zones: list[Zone]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {"name": z.name, "points": [[x, y] for x, y in z.points]}
            for z in zones
        ]
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
