import json
from dataclasses import asdict, fields
from pathlib import Path

from app.core.settings import Settings


class SettingsRepository:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Settings:
        if not self._path.exists():
            return Settings()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return Settings()
        valid_keys = {f.name for f in fields(Settings)}
        kwargs = {k: v for k, v in raw.items() if k in valid_keys}
        try:
            return Settings(**kwargs)
        except (TypeError, ValueError):
            return Settings()

    def save(self, settings: Settings) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(asdict(settings), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
