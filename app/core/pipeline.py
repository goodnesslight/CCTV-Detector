from typing import Protocol, runtime_checkable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

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

# cv2.putText не вміє в кирилицю — малюємо підписи через PIL.
_FONT_CACHE: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
_FONT_PATHS = [
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
]
_FONT_SIZE = 14


def _get_font():
    global _FONT_CACHE
    if _FONT_CACHE is not None:
        return _FONT_CACHE
    for path in _FONT_PATHS:
        try:
            _FONT_CACHE = ImageFont.truetype(path, _FONT_SIZE)
            return _FONT_CACHE
        except (OSError, IOError):
            continue
    _FONT_CACHE = ImageFont.load_default()
    return _FONT_CACHE


def _bgr_to_rgb(bgr: tuple[int, int, int]) -> tuple[int, int, int]:
    return (bgr[2], bgr[1], bgr[0])


def _draw_text_pil(
    image_bgr: np.ndarray,
    items: list[tuple[str, int, int, tuple[int, int, int], tuple[int, int, int]]],
) -> np.ndarray:
    """Один прохід PIL для всіх текстових підписів кадра.
    items: (text, x, y, fg_bgr, bg_bgr) — bg-прямокутник під текстом."""
    if not items:
        return image_bgr
    img_pil = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    font = _get_font()
    for text, x, y, fg_bgr, bg_bgr in items:
        try:
            bbox = draw.textbbox((x, y), text, font=font)
        except Exception:
            continue
        pad = 2
        rect = (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad)
        draw.rectangle(rect, fill=_bgr_to_rgb(bg_bgr))
        draw.text((x, y), text, font=font, fill=_bgr_to_rgb(fg_bgr))
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)


def _collect_zone_overlays(
    image: np.ndarray,
    zones: list[Zone],
    text_items: list,
) -> None:
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
        text_items.append(
            (zone.name, max(int(cx) - 30, 4), max(int(cy) - 10, 4),
             (255, 255, 255), (30, 30, 30))
        )


def _collect_detection_overlays(
    image: np.ndarray,
    detections: list[Detection],
    text_items: list,
) -> None:
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
        y = max(d.y1 - _FONT_SIZE - 4, 2)
        text_items.append((text, max(d.x1, 0), y, (0, 0, 0), color))


def draw_overlay(
    image: np.ndarray,
    detections: list[Detection],
    zones: list[Zone] | None = None,
) -> np.ndarray:
    out = image.copy()
    text_items: list = []
    if zones:
        _collect_zone_overlays(out, zones, text_items)
    if detections:
        _collect_detection_overlays(out, detections, text_items)
    if text_items:
        out = _draw_text_pil(out, text_items)
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
