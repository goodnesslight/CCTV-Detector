from pathlib import Path

APP_NAME = "Video Security System"
APP_VERSION = "0.1.0"

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
CLIPS_DIR = DATA_DIR / "clips"
KNOWN_FACES_DIR = DATA_DIR / "known_faces"
MODELS_DIR = DATA_DIR / "models"
DB_PATH = DATA_DIR / "events.db"
ZONES_PATH = DATA_DIR / "zones.json"
SETTINGS_PATH = DATA_DIR / "settings.json"

ASSETS_DIR = ROOT_DIR / "assets"
SOUNDS_DIR = ASSETS_DIR / "sounds"
