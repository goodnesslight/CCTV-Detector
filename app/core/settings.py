from dataclasses import dataclass


@dataclass
class Settings:
    yolo_conf_threshold: float = 0.4
    face_match_threshold: float = 0.4
    face_det_threshold: float = 0.7

    live_person_enabled: bool = True
    live_face_enabled: bool = True
    live_tracking_enabled: bool = False

    alert_cooldown_seconds: float = 10.0
    loitering_threshold_seconds: float = 5.0
    sighting_cooldown_seconds: float = 30.0

    beep_enabled: bool = True
    tts_enabled: bool = False
    tts_language: str = "uk"

    clip_pre_seconds: float = 2.0
    clip_post_seconds: float = 5.0

    privacy_blur_unknown: bool = False
    activity_heatmap_enabled: bool = False
