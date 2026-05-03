from typing import Protocol, runtime_checkable

import numpy as np

from app.core.types import Detection


@runtime_checkable
class Tracker(Protocol):
    def update(self, detections: list[Detection], frame_shape: tuple[int, int]) -> None: ...

    def reset(self) -> None: ...


def _iou(b1: tuple[float, float, float, float], b2: tuple[float, float, float, float]) -> float:
    x1 = max(b1[0], b2[0])
    y1 = max(b1[1], b2[1])
    x2 = min(b1[2], b2[2])
    y2 = min(b1[3], b2[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    union = a1 + a2 - inter
    return inter / union if union > 0 else 0.0


class ByteTrackPersonTracker:
    """Wraps supervision.ByteTrack. Tracks only `label == "person"` detections,
    sets Detection.track_id by IoU matching against tracker output."""

    def __init__(self, iou_match_threshold: float = 0.5) -> None:
        import supervision as sv

        self._sv = sv
        self._tracker = sv.ByteTrack()
        self._iou_threshold = iou_match_threshold

    def update(self, detections: list[Detection], frame_shape: tuple[int, int]) -> None:
        person_indices = [i for i, d in enumerate(detections) if d.label == "person"]
        if not person_indices:
            try:
                self._tracker.update_with_detections(self._sv.Detections.empty())
            except Exception:
                pass
            return

        person_dets = [detections[i] for i in person_indices]
        xyxy = np.array(
            [[d.x1, d.y1, d.x2, d.y2] for d in person_dets], dtype=float
        )
        conf = np.array([d.confidence for d in person_dets], dtype=float)
        cls = np.array([d.class_id for d in person_dets], dtype=int)
        sv_dets = self._sv.Detections(xyxy=xyxy, confidence=conf, class_id=cls)

        try:
            tracked = self._tracker.update_with_detections(sv_dets)
        except Exception:
            return

        if len(tracked) == 0 or tracked.tracker_id is None:
            return

        for src_idx, src_det in zip(person_indices, person_dets):
            best_iou = 0.0
            best_tid: int | None = None
            for j in range(len(tracked)):
                tx1, ty1, tx2, ty2 = tracked.xyxy[j]
                iou = _iou(
                    (src_det.x1, src_det.y1, src_det.x2, src_det.y2),
                    (float(tx1), float(ty1), float(tx2), float(ty2)),
                )
                if iou > best_iou:
                    best_iou = iou
                    tid = tracked.tracker_id[j]
                    best_tid = int(tid) if tid is not None else None
            if best_iou >= self._iou_threshold and best_tid is not None:
                detections[src_idx].track_id = best_tid

    def reset(self) -> None:
        try:
            self._tracker.reset()
        except Exception:
            try:
                self._tracker = self._sv.ByteTrack()
            except Exception:
                pass
