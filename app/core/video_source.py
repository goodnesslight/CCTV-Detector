import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union

import cv2

from app.core.frame import Frame


class VideoSource(ABC):
    @abstractmethod
    def open(self) -> bool: ...

    @abstractmethod
    def read(self) -> Frame | None: ...

    @abstractmethod
    def close(self) -> None: ...

    @property
    @abstractmethod
    def is_open(self) -> bool: ...

    @property
    @abstractmethod
    def is_live(self) -> bool: ...

    @property
    @abstractmethod
    def descriptor(self) -> str: ...


class OpenCVVideoSource(VideoSource):
    def __init__(self, spec: Union[int, str], descriptor: str, is_live: bool) -> None:
        self._spec = spec
        self._descriptor = descriptor
        self._is_live = is_live
        self._cap: cv2.VideoCapture | None = None
        self._frame_index = 0
        self._start_time: float | None = None

    def open(self) -> bool:
        cap = cv2.VideoCapture(self._spec)
        if not cap.isOpened():
            cap.release()
            return False
        self._cap = cap
        self._frame_index = 0
        self._start_time = time.monotonic()
        return True

    def read(self) -> Frame | None:
        if self._cap is None:
            return None
        ok, image = self._cap.read()
        if not ok or image is None:
            return None
        ts = time.monotonic() - (self._start_time or 0.0)
        idx = self._frame_index
        self._frame_index += 1
        return Frame(image=image, timestamp=ts, index=idx)

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    @property
    def is_live(self) -> bool:
        return self._is_live

    @property
    def descriptor(self) -> str:
        return self._descriptor


def usb_camera(index: int = 0) -> OpenCVVideoSource:
    return OpenCVVideoSource(spec=index, descriptor=f"USB camera {index}", is_live=True)


def rtsp_stream(url: str) -> OpenCVVideoSource:
    return OpenCVVideoSource(spec=url, descriptor=f"RTSP {url}", is_live=True)


def video_file(path: Path | str) -> OpenCVVideoSource:
    p = Path(path)
    return OpenCVVideoSource(spec=str(p), descriptor=f"File {p.name}", is_live=False)
