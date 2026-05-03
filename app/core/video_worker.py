from PySide6.QtCore import QThread, Signal

from app.core.pipeline import FrameProcessor
from app.core.types import ProcessingResult
from app.core.video_source import VideoSource


class VideoWorker(QThread):
    result_ready = Signal(object)
    error = Signal(str)
    stream_ended = Signal()

    def __init__(
        self,
        source: VideoSource,
        processor: FrameProcessor | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._source = source
        self._processor = processor
        self._running = False

    def run(self) -> None:
        if not self._source.open():
            self.error.emit(f"Не удалось открыть источник: {self._source.descriptor}")
            return

        self._running = True
        try:
            while self._running:
                frame = self._source.read()
                if frame is None:
                    if not self._source.is_live:
                        self.stream_ended.emit()
                        break
                    self.msleep(20)
                    continue

                if self._processor is not None:
                    try:
                        result = self._processor.process(frame)
                    except Exception as exc:
                        self.error.emit(f"Ошибка обработки: {exc}")
                        break
                else:
                    result = ProcessingResult(frame=frame, image=frame.image)

                self.result_ready.emit(result)
        finally:
            self._source.close()

    def stop(self) -> None:
        self._running = False
        if self.isRunning():
            self.wait(2000)
