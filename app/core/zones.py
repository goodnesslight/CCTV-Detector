from dataclasses import dataclass, field

import cv2
import numpy as np


@dataclass
class Zone:
    name: str
    points: list[tuple[int, int]] = field(default_factory=list)

    def contains(self, point: tuple[int, int]) -> bool:
        if len(self.points) < 3:
            return False
        contour = np.asarray(self.points, dtype=np.int32)
        return cv2.pointPolygonTest(contour, (float(point[0]), float(point[1])), False) >= 0
