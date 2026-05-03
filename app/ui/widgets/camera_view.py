import cv2
import numpy as np
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

_IDLE_STYLE = (
    "background-color: #111; color: #666; font-size: 16px; "
    "border: 1px solid #333;"
)
_ALERT_STYLE = (
    "background-color: #111; color: #666; font-size: 16px; "
    "border: 6px solid #ff2222;"
)


class CameraView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._image_label = QLabel("Нет сигнала", self)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet(_IDLE_STYLE)
        self._image_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._image_label.setMinimumSize(640, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._image_label)

        self._fps_label = QLabel("", self._image_label)
        self._fps_label.setStyleSheet(
            "color: #4ade80; background-color: rgba(0,0,0,160); "
            "padding: 2px 6px; font-family: monospace; font-size: 12px;"
        )
        self._fps_label.move(8, 8)
        self._fps_label.hide()

        self._last_pixmap: QPixmap | None = None
        self._frame_count = 0
        self._fps_timer = QTimer(self)
        self._fps_timer.setInterval(500)
        self._fps_timer.timeout.connect(self._update_fps)

        self._alert_timer = QTimer(self)
        self._alert_timer.setSingleShot(True)
        self._alert_timer.timeout.connect(self._clear_alert_border)

    @Slot(np.ndarray)
    def display_frame(self, bgr: np.ndarray) -> None:
        if not self._fps_timer.isActive():
            self._fps_timer.start()
            self._fps_label.show()

        h, w, _ = bgr.shape
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        self._last_pixmap = QPixmap.fromImage(qimg)
        self._frame_count += 1
        self._render()

    def clear(self) -> None:
        self._fps_timer.stop()
        self._fps_label.hide()
        self._last_pixmap = None
        self._frame_count = 0
        self._alert_timer.stop()
        self._image_label.setPixmap(QPixmap())
        self._image_label.setText("Нет сигнала")
        self._image_label.setStyleSheet(_IDLE_STYLE)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._render()

    def _render(self) -> None:
        if self._last_pixmap is None:
            return
        scaled = self._last_pixmap.scaled(
            self._image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_label.setPixmap(scaled)

    @Slot()
    def _update_fps(self) -> None:
        fps = self._frame_count * 2
        self._fps_label.setText(f"{fps} FPS")
        self._fps_label.adjustSize()
        self._frame_count = 0

    def trigger_alert(self, duration_ms: int = 2000) -> None:
        self._image_label.setStyleSheet(_ALERT_STYLE)
        self._alert_timer.start(duration_ms)

    @Slot()
    def _clear_alert_border(self) -> None:
        self._image_label.setStyleSheet(_IDLE_STYLE)
