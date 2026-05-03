from typing import Protocol, runtime_checkable

import cv2
import numpy as np

from app.core.frame import Frame
from app.core.types import Detection, ProcessingResult
from app.core.zones import Zone


@runtime_checkable
class Detector(Protocol):
    def detect(self, frame: Frame) -> list[Detection]: ...


@runtime_checkable
class FrameProcessor(Protocol):
    def process(self, frame: Frame) -> ProcessingResult: ...


_LABEL_COLORS_BGR: dict[str, tuple[int, int, int]] = {
    "person": (76, 175, 80),
    "known_face": (76, 175, 80),
    "unknown_face": (52, 67, 244),
}
_DEFAULT_COLOR = (200, 200, 200)
_IN_ZONE_COLOR_BGR = (0, 0, 255)
_ZONE_FILL_BGR = (255, 200, 0)
_ZONE_OUTLINE_BGR = (255, 220, 80)


def _draw_zones(image: np.ndarray, zones: list[Zone]) -> None:
    if not zones:
        return
    overlay = image.copy()
    for zone in zones:
        if len(zone.points) < 3:
            continue
        pts = np.asarray(zone.points, dtype=np.int32)
        cv2.fillPoly(overlay, [pts], _ZONE_FILL_BGR)
    cv2.addWeighted(overlay, 0.25, image, 0.75, 0, image)
    for zone in zones:
        if len(zone.points) < 3:
            continue
        pts = np.asarray(zone.points, dtype=np.int32)
        cv2.polylines(image, [pts], True, _ZONE_OUTLINE_BGR, 2)
        cx, cy = pts.mean(axis=0).astype(int)
        cv2.putText(
            image, zone.name, (int(cx) - 30, int(cy)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4,
        )
        cv2.putText(
            image, zone.name, (int(cx) - 30, int(cy)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2,
        )


def _draw_detections(image: np.ndarray, detections: list[Detection]) -> None:
    for d in detections:
        if d.zone_name is not None:
            color = _IN_ZONE_COLOR_BGR
        else:
            color = _LABEL_COLORS_BGR.get(d.label, _DEFAULT_COLOR)
        cv2.rectangle(image, (d.x1, d.y1), (d.x2, d.y2), color, 2)
        text = d.display_text
        if d.track_id is not None:
            text = f"#{d.track_id} {text}"
        if d.zone_name is not None:
            text = f"{text}  →  {d.zone_name}"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        y_top = max(d.y1 - th - 6, 0)
        cv2.rectangle(
            image, (d.x1, y_top), (d.x1 + tw + 6, y_top + th + 6), color, -1
        )
        cv2.putText(
            image, text, (d.x1 + 3, y_top + th + 2),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1,
        )


def draw_overlay(
    image: np.ndarray,
    detections: list[Detection],
    zones: list[Zone] | None = None,
) -> np.ndarray:
    out = image.copy()
    if zones:
        _draw_zones(out, zones)
    if detections:
        _draw_detections(out, detections)
    return out


class DetectionPipeline:
    def __init__(
        self,
        detectors: list[Detector],
        zones: list[Zone] | None = None,
        tracker=None,
    ) -> None:
        self._detectors = detectors
        self._zones = list(zones) if zones else []
        self._tracker = tracker

    def process(self, frame: Frame) -> ProcessingResult:
        detections: list[Detection] = []
        for d in self._detectors:
            detections.extend(d.detect(frame))

        if self._tracker is not None:
            try:
                self._tracker.update(detections, frame.image.shape[:2])
            except Exception:
                pass

        if self._zones:
            for det in detections:
                for zone in self._zones:
                    if zone.contains(det.bottom_center):
                        det.zone_name = zone.name
                        break

        if detections or self._zones:
            image = draw_overlay(frame.image, detections, self._zones)
        else:
            image = frame.image
        return ProcessingResult(frame=frame, image=image, detections=detections)
