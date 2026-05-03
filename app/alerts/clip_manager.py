import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class _ActiveClip:
    writer: cv2.VideoWriter
    path: Path
    end_time: float
    frame_size: tuple[int, int]


class ClipManager:
    def __init__(
        self,
        output_dir: Path,
        pre_seconds: float = 2.0,
        post_seconds: float = 5.0,
        fps: float = 25.0,
    ) -> None:
        self._output_dir = output_dir
        self._pre_s = pre_seconds
        self._post_s = post_seconds
        self._fps = fps
        max_pre = max(1, int(pre_seconds * fps))
        self._pre_buffer: deque[np.ndarray] = deque(maxlen=max_pre)
        self._active: list[_ActiveClip] = []

    def push_frame(self, image: np.ndarray, ts: float) -> None:
        self._pre_buffer.append(image)
        finished: list[_ActiveClip] = []
        for clip in self._active:
            h, w = image.shape[:2]
            if (h, w) != clip.frame_size:
                continue
            try:
                clip.writer.write(image)
            except Exception:
                pass
            if ts >= clip.end_time:
                try:
                    clip.writer.release()
                except Exception:
                    pass
                finished.append(clip)
        for clip in finished:
            self._active.remove(clip)

    def trigger(
        self,
        alert_id: str,
        kind: str,
        ts: float,
        frame_size: tuple[int, int],
    ) -> Path | None:
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            h, w = frame_size
            stamp = time.strftime("%Y%m%d-%H%M%S")
            safe_kind = "".join(c if c.isalnum() else "_" for c in kind)[:40]
            path = self._output_dir / f"{stamp}_{safe_kind}_{alert_id[:8]}.mp4"
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(path), fourcc, self._fps, (w, h))
            if not writer.isOpened():
                return None
            for f in self._pre_buffer:
                if f.shape[:2] == (h, w):
                    writer.write(f)
            self._active.append(
                _ActiveClip(writer=writer, path=path, end_time=ts + self._post_s, frame_size=(h, w))
            )
            return path
        except Exception:
            return None

    def configure(self, pre_seconds: float, post_seconds: float) -> None:
        self._pre_s = float(pre_seconds)
        self._post_s = float(post_seconds)
        new_max = max(1, int(self._pre_s * self._fps))
        if self._pre_buffer.maxlen != new_max:
            old = list(self._pre_buffer)
            self._pre_buffer = deque(old[-new_max:], maxlen=new_max)

    def reset(self) -> None:
        self._pre_buffer.clear()
        for clip in self._active:
            try:
                clip.writer.release()
            except Exception:
                pass
        self._active.clear()

    def shutdown(self) -> None:
        self.reset()
