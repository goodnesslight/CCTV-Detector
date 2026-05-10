from pathlib import Path

APP_NAME = "Video Security System"
APP_TITLE = (
    "Система безпеки приміщення на базі "
    "відеоспостереження та штучного інтелекту"
)
APP_VERSION = "1.0.0"

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
CLIPS_DIR = DATA_DIR / "clips"
KNOWN_FACES_DIR = DATA_DIR / "known_faces"
UNKNOWN_FACES_DIR = DATA_DIR / "unknown_faces"
MODELS_DIR = DATA_DIR / "models"
DB_PATH = DATA_DIR / "events.db"
ZONES_PATH = DATA_DIR / "zones.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
HEATMAP_PATH = DATA_DIR / "activity_heatmap.npy"

ASSETS_DIR = ROOT_DIR / "assets"
SOUNDS_DIR = ASSETS_DIR / "sounds"
