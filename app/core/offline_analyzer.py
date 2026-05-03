import time
from pathlib import Path

import cv2
from PySide6.QtCore import QThread, Signal

from app.alerts.alert_manager import LoiteringRule, UnknownFaceRule, ZoneIntrusionRule
from app.core.frame import Frame
from app.core.pipeline import DetectionPipeline, Detector
from app.core.zones import Zone


class OfflineAnalyzer(QThread):
    progress = Signal(int, int)
    event_found = Signal(object)
    finished_ok = Signal(int, float)
    error = Signal(str)

    def __init__(
        self,
        video_path: Path | str,
        detectors: list[Detector],
        zones: list[Zone] | None = None,
        tracker=None,
        cooldown_seconds: float = 5.0,
        loitering_threshold_seconds: float = 3.0,
        progress_every: int = 15,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._path = Path(video_path)
        self._detectors = detectors
        self._zones = list(zones) if zones else []
        self._tracker = tracker
        self._cooldown = cooldown_seconds
        self._loitering_threshold = loitering_threshold_seconds
        self._progress_every = progress_every
        self._running = False

    def stop(self) -> None:
        self._running = False
        if self.isRunning():
            self.wait(3000)

    def run(self) -> None:
        cap = cv2.VideoCapture(str(self._path))
        if not cap.isOpened():
            self.error.emit(f"Не удалось открыть файл: {self._path.name}")
            return

        try:
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            if fps <= 0:
                fps = 25.0

            pipeline = DetectionPipeline(
                self._detectors, zones=self._zones, tracker=self._tracker,
            )
            rules = [
                UnknownFaceRule(),
                ZoneIntrusionRule(),
                LoiteringRule(threshold_seconds=self._loitering_threshold),
            ]
            last_fired: dict[str, float] = {}

            self._running = True
            t0 = time.perf_counter()
            frame_idx = 0

            while self._running:
                ok, image = cap.read()
                if not ok or image is None:
                    break

                video_ts = frame_idx / fps
                frame = Frame(image=image, timestamp=video_ts, index=frame_idx)
                try:
                    result = pipeline.process(frame)
                except Exception as exc:
                    self.error.emit(f"Ошибка пайплайна на кадре {frame_idx}: {exc}")
                    break

                for rule in rules:
                    try:
                        candidates = rule.evaluate(result, video_ts)
                    except Exception:
                        continue
                    for ev in candidates:
                        last = last_fired.get(ev.kind, float("-inf"))
                        if video_ts - last < self._cooldown:
                            continue
                        last_fired[ev.kind] = video_ts
                        self.event_found.emit(ev)

                frame_idx += 1
                if frame_idx % self._progress_every == 0:
                    self.progress.emit(frame_idx, total)

            elapsed = time.perf_counter() - t0
            self.progress.emit(frame_idx, total)
            self.finished_ok.emit(frame_idx, elapsed)
        except Exception as exc:
            self.error.emit(f"Ошибка анализа: {exc}")
        finally:
            cap.release()
