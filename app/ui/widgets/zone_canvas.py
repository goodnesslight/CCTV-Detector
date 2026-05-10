import cv2
import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
    QResizeEvent,
)
from PySide6.QtWidgets import QWidget

from app.core.zones import Zone


class ZoneCanvas(QWidget):
    zoneCompleted = Signal(list)  # list[tuple[int, int]] in image coords

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(640, 360)
        self.setStyleSheet("background-color: #111;")

        self._background: QPixmap | None = None
        self._zones: list[Zone] = []
        self._drawing = False
        self._current_pts: list[tuple[int, int]] = []
        self._mouse_widget: tuple[int, int] | None = None
        self._scale = 1.0
        self._offset = (0, 0)

    @property
    def has_background(self) -> bool:
        return self._background is not None

    @property
    def is_drawing(self) -> bool:
        return self._drawing

    def set_background(self, image: np.ndarray | None) -> None:
        if image is None:
            self._background = None
        else:
            h, w = image.shape[:2]
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            qimg = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
            self._background = QPixmap.fromImage(qimg)
        self._update_layout()
        self.update()

    def set_zones(self, zones: list[Zone]) -> None:
        self._zones = list(zones)
        self.update()

    def start_drawing(self) -> None:
        self._drawing = True
        self._current_pts = []
        self._mouse_widget = None
        self.update()

    def cancel_drawing(self) -> None:
        self._drawing = False
        self._current_pts = []
        self._mouse_widget = None
        self.update()

    def finish_drawing(self) -> bool:
        if not self._drawing or len(self._current_pts) < 3:
            return False
        pts = list(self._current_pts)
        self._drawing = False
        self._current_pts = []
        self._mouse_widget = None
        self.zoneCompleted.emit(pts)
        self.update()
        return True

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._update_layout()
        super().resizeEvent(event)

    def _update_layout(self) -> None:
        if self._background is None or self._background.isNull():
            self._scale = 1.0
            self._offset = (0, 0)
            return
        iw, ih = self._background.width(), self._background.height()
        ww, wh = self.width(), self.height()
        if iw == 0 or ih == 0:
            return
        scale = min(ww / iw, wh / ih)
        sw = int(iw * scale)
        sh = int(ih * scale)
        self._scale = scale
        self._offset = ((ww - sw) // 2, (wh - sh) // 2)

    def _widget_to_image(self, wx: float, wy: float) -> tuple[int, int] | None:
        if self._background is None or self._scale <= 0:
            return None
        ox, oy = self._offset
        x = wx - ox
        y = wy - oy
        if x < 0 or y < 0:
            return None
        ix = x / self._scale
        iy = y / self._scale
        if ix >= self._background.width() or iy >= self._background.height():
            return None
        return int(ix), int(iy)

    def _image_to_widget(self, ix: float, iy: float) -> tuple[int, int]:
        ox, oy = self._offset
        return int(ix * self._scale + ox), int(iy * self._scale + oy)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._drawing or self._background is None:
            return
        pos = event.position()
        if event.button() == Qt.MouseButton.LeftButton:
            pt = self._widget_to_image(pos.x(), pos.y())
            if pt is not None:
                self._current_pts.append(pt)
                self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self.finish_drawing()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._drawing:
            return
        pos = event.position()
        self._mouse_widget = (int(pos.x()), int(pos.y()))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#111"))

        if self._background is None:
            p.setPen(QColor("#666"))
            p.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter,
                "Знімок не завантажено.\n"
                "Натисніть 'Знімок з Live' (після старту камери) або 'Відкрити файл...'",
            )
            return

        ox, oy = self._offset
        sw = int(self._background.width() * self._scale)
        sh = int(self._background.height() * self._scale)
        p.drawPixmap(QRect(ox, oy, sw, sh), self._background)

        for zone in self._zones:
            if len(zone.points) < 3:
                continue
            self._draw_polygon(
                p, zone.points,
                fill=QColor(0, 200, 255, 90),
                stroke=QColor(60, 220, 255, 230),
                name=zone.name,
            )

        if self._drawing and self._current_pts:
            stroke = QColor(255, 200, 0, 240)
            p.setPen(QPen(stroke, 2))
            wp = [self._image_to_widget(x, y) for x, y in self._current_pts]
            for i in range(1, len(wp)):
                p.drawLine(wp[i - 1][0], wp[i - 1][1], wp[i][0], wp[i][1])
            if self._mouse_widget is not None:
                p.setPen(QPen(stroke, 1, Qt.PenStyle.DashLine))
                p.drawLine(
                    wp[-1][0], wp[-1][1],
                    self._mouse_widget[0], self._mouse_widget[1],
                )
            p.setBrush(stroke)
            p.setPen(Qt.PenStyle.NoPen)
            for x, y in wp:
                p.drawEllipse(QPoint(x, y), 4, 4)

    def _draw_polygon(
        self,
        p: QPainter,
        image_points: list[tuple[int, int]],
        fill: QColor,
        stroke: QColor,
        name: str = "",
    ) -> None:
        widget_pts = [QPointF(*self._image_to_widget(x, y)) for x, y in image_points]
        polygon = QPolygonF(widget_pts)
        p.setBrush(fill)
        p.setPen(QPen(stroke, 2))
        p.drawPolygon(polygon)
        if name and widget_pts:
            cx = sum(pt.x() for pt in widget_pts) / len(widget_pts)
            cy = sum(pt.y() for pt in widget_pts) / len(widget_pts)
            text_w = max(60, len(name) * 8 + 12)
            text_rect = QRect(int(cx - text_w / 2), int(cy - 12), text_w, 22)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 180))
            p.drawRect(text_rect)
            p.setPen(QColor(255, 255, 255))
            p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, name)
