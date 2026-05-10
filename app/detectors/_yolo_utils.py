from pathlib import Path
from urllib.request import urlretrieve

from app.config import MODELS_DIR


def ensure_yolo_model(model_name: str) -> Path:
    """Завантажує ваги YOLO в data/models/, якщо їх там ще немає."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    target = MODELS_DIR / model_name
    if target.exists():
        return target
    url = f"https://github.com/ultralytics/assets/releases/latest/download/{model_name}"
    urlretrieve(url, target)
    return target
