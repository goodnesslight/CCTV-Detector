from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class AlertEvent:
    id: str
    timestamp: float
    kind: str
    title: str
    detail: str
    detection_bbox: tuple[int, int, int, int] | None = None
    zone_name: str | None = None
    clip_path: Path | None = None
    snapshot_path: Path | None = None
    face_embedding: np.ndarray | None = None
