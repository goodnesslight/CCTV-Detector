import numpy as np

from app.alerts.alert_manager import (
    AlertManager,
    LoiteringRule,
    UnknownFaceRule,
    WeaponSightedRule,
    ZoneIntrusionRule,
)
from app.alerts.clip_manager import ClipManager
from app.alerts.sound import SoundPlayer, TTSPlayer
from app.config import CLIPS_DIR, DB_PATH, KNOWN_FACES_DIR, SETTINGS_PATH, ZONES_PATH
from app.core.settings import Settings
from app.core.zones import Zone
from app.detectors.face_recognizer import FaceRecognizer
from app.detectors.person_detector import PersonDetector
from app.detectors.weapon_detector import WeaponDetector
from app.storage.events_repo import EventsRepository
from app.storage.settings_repo import SettingsRepository
from app.storage.zones_repo import ZonesRepository


class Services:
    def __init__(self) -> None:
        self.settings_repo = SettingsRepository(SETTINGS_PATH)
        self.settings: Settings = self.settings_repo.load()

        self._person_detector: PersonDetector | None = None
        self._face_recognizer: FaceRecognizer | None = None
        self._weapon_detector: WeaponDetector | None = None
        self._zones_repo = ZonesRepository(ZONES_PATH)
        self._zones: list[Zone] | None = None
        self.latest_frame: np.ndarray | None = None

        self._sound = SoundPlayer()
        self._tts = TTSPlayer(language_hint=self.settings.tts_language)
        self._clip_manager = ClipManager(
            output_dir=CLIPS_DIR,
            pre_seconds=self.settings.clip_pre_seconds,
            post_seconds=self.settings.clip_post_seconds,
        )
        self.events_repo = EventsRepository(DB_PATH)
        self.alerts = AlertManager(
            clip_manager=self._clip_manager,
            sound=self._sound,
            tts=self._tts,
            repository=self.events_repo,
            settings=self.settings,
            cooldown_seconds=self.settings.alert_cooldown_seconds,
            rules=[
                UnknownFaceRule(),
                ZoneIntrusionRule(),
                LoiteringRule(threshold_seconds=self.settings.loitering_threshold_seconds),
                WeaponSightedRule(),
            ],
        )

    def person_detector(self) -> PersonDetector:
        if self._person_detector is None:
            self._person_detector = PersonDetector(
                conf_threshold=self.settings.yolo_conf_threshold,
            )
        return self._person_detector

    def face_recognizer(self) -> FaceRecognizer:
        if self._face_recognizer is None:
            self._face_recognizer = FaceRecognizer(
                known_faces_dir=KNOWN_FACES_DIR,
                match_threshold=self.settings.face_match_threshold,
                det_score_threshold=self.settings.face_det_threshold,
            )
        return self._face_recognizer

    def weapon_detector(self) -> WeaponDetector:
        if self._weapon_detector is None:
            self._weapon_detector = WeaponDetector()
        return self._weapon_detector

    def create_tracker(self):
        from app.detectors.tracker import ByteTrackPersonTracker
        return ByteTrackPersonTracker()

    @property
    def is_face_recognizer_loaded(self) -> bool:
        return self._face_recognizer is not None

    def zones(self) -> list[Zone]:
        if self._zones is None:
            self._zones = self._zones_repo.load()
        return self._zones

    def save_zones(self) -> None:
        if self._zones is not None:
            self._zones_repo.save(self._zones)

    def apply_settings(self) -> None:
        s = self.settings
        self.settings_repo.save(s)

        self._clip_manager.configure(s.clip_pre_seconds, s.clip_post_seconds)
        self.alerts.set_cooldown(s.alert_cooldown_seconds)
        self.alerts.set_loitering_threshold(s.loitering_threshold_seconds)

        if self._person_detector is not None:
            self._person_detector.set_conf_threshold(s.yolo_conf_threshold)
        if self._face_recognizer is not None:
            self._face_recognizer.set_match_threshold(s.face_match_threshold)
            self._face_recognizer.set_det_threshold(s.face_det_threshold)

    def shutdown(self) -> None:
        self.alerts.shutdown()
