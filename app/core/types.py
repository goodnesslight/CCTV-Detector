from dataclasses import dataclass, field
from typing import Any

import numpy as np

from app.core.frame import Frame


@dataclass
class Detection:
    x1: int
    y1: int
    x2: int
    y2: int
    label: str
    confidence: float
    class_id: int
    track_id: int | None = None
    annotation: str | None = None
    zone_name: str | None = None
    person_name: str | None = None

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x1, self.y1, self.x2, self.y2)

    @property
    def center(self) -> tuple[int, int]:
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)

    @property
    def bottom_center(self) -> tuple[int, int]:
        return ((self.x1 + self.x2) // 2, self.y2)

    @property
    def display_text(self) -> str:
        if self.annotation is not None:
            return self.annotation
        return f"{self.label} {self.confidence:.2f}"


@dataclass
class ProcessingResult:
    frame: Frame
    image: np.ndarray
    detections: list[Detection] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
