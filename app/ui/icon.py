from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
)


def create_app_icon(size: int = 256) -> QIcon:
    """Програмно генерує іконку застосунку — пильне око зі смарагдовою
    райдужкою на темно-синьому заокругленому квадраті. Передає сенс
    'безпека + комп'ютерний зір'."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    bg = QLinearGradient(0, 0, 0, size)
    bg.setColorAt(0, QColor("#1e3a5f"))
    bg.setColorAt(1, QColor("#0a1428"))
    p.setBrush(QBrush(bg))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.20, size * 0.20)

    cx, cy = size / 2, size / 2
    eye_w = size * 0.72
    eye_h = size * 0.40

    eye = QPainterPath()
    eye.moveTo(cx - eye_w / 2, cy)
    eye.cubicTo(
        cx - eye_w / 2, cy - eye_h,
        cx + eye_w / 2, cy - eye_h,
        cx + eye_w / 2, cy,
    )
    eye.cubicTo(
        cx + eye_w / 2, cy + eye_h,
        cx - eye_w / 2, cy + eye_h,
        cx - eye_w / 2, cy,
    )
    eye.closeSubpath()
    p.fillPath(eye, QColor("#f8fafc"))

    iris_r = size * 0.18
    iris_grad = QLinearGradient(cx, cy - iris_r, cx, cy + iris_r)
    iris_grad.setColorAt(0.0, QColor("#34d399"))
    iris_grad.setColorAt(1.0, QColor("#047857"))
    p.setBrush(QBrush(iris_grad))
    p.drawEllipse(QPointF(cx, cy), iris_r, iris_r)

    p.setBrush(QColor("#0a1428"))
    p.drawEllipse(QPointF(cx, cy), iris_r * 0.42, iris_r * 0.42)

    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(
        QPointF(cx - iris_r * 0.28, cy - iris_r * 0.28),
        iris_r * 0.18, iris_r * 0.18,
    )

    p.end()
    return QIcon(pix)
