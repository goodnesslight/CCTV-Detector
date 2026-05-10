from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.zones import Zone
from app.services import Services
from app.ui.widgets.zone_canvas import ZoneCanvas


class ZonesTab(QWidget):
    def __init__(self, services: Services) -> None:
        super().__init__()
        self._services = services

        self._snapshot_btn = QPushButton("Знімок з прямої трансляції")
        self._snapshot_btn.clicked.connect(self._on_snapshot_live)

        self._new_zone_btn = QPushButton("+ Нова зона")
        self._new_zone_btn.clicked.connect(self._on_new_zone)

        self._finish_btn = QPushButton("Закрити зону")
        self._finish_btn.clicked.connect(self._on_finish)
        self._finish_btn.setEnabled(False)

        self._cancel_btn = QPushButton("Скасувати")
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._cancel_btn.setEnabled(False)

        self._delete_btn = QPushButton("Видалити вибрану")
        self._delete_btn.clicked.connect(self._on_delete)

        self._list_widget = QListWidget()
        self._list_widget.setMaximumWidth(240)

        self._canvas = ZoneCanvas()
        self._canvas.zoneCompleted.connect(self._on_zone_completed)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888; padding: 4px;")
        self._status_label.setWordWrap(True)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._snapshot_btn)
        sep = QLabel(" │ ")
        sep.setStyleSheet("color: #444;")
        toolbar.addWidget(sep)
        toolbar.addWidget(self._new_zone_btn)
        toolbar.addWidget(self._finish_btn)
        toolbar.addWidget(self._cancel_btn)
        toolbar.addWidget(self._delete_btn)
        toolbar.addStretch(1)

        center = QHBoxLayout()
        center.addWidget(self._canvas, 1)
        center.addWidget(self._list_widget)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addLayout(center, 1)
        layout.addWidget(self._status_label)

        self._refresh()

    def _refresh(self) -> None:
        zones = self._services.zones()
        self._canvas.set_zones(zones)
        self._list_widget.clear()
        for z in zones:
            self._list_widget.addItem(f"{z.name}  ({len(z.points)} точок)")
        suffix = ""
        if zones:
            suffix = "  Щоб зміни застосувались у Live, перепідключіться до джерела."
        self._status_label.setText(f"Зон: {len(zones)} (зберігаються автоматично).{suffix}")

    @Slot()
    def _on_snapshot_live(self) -> None:
        frame = self._services.latest_frame
        if frame is None:
            QMessageBox.information(
                self,
                "Немає кадру",
                "Спочатку запусти джерело на вкладці 'Пряма трансляція', дочекайся "
                "пари кадрів і повернись сюди.",
            )
            return
        self._canvas.set_background(frame)
        self._status_label.setText(
            "Знімок отримано. Натисни '+ Нова зона' і клікай по точках полігону."
        )

    @Slot()
    def _on_new_zone(self) -> None:
        if not self._canvas.has_background:
            QMessageBox.information(
                self, "Немає знімка",
                "Спочатку запусти джерело на вкладці 'Пряма трансляція' "
                "та натисни 'Знімок з прямої трансляції'.",
            )
            return
        self._canvas.start_drawing()
        self._finish_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)
        self._new_zone_btn.setEnabled(False)
        self._status_label.setText(
            "Клікай по точках контуру. ПКМ або 'Закрити зону' — завершити (потрібно ≥3 точки)."
        )

    @Slot()
    def _on_finish(self) -> None:
        if not self._canvas.finish_drawing():
            QMessageBox.information(
                self, "Мало точок", "Зона має містити мінімум 3 точки.",
            )

    @Slot()
    def _on_cancel(self) -> None:
        self._canvas.cancel_drawing()
        self._reset_drawing_buttons()
        self._status_label.setText("Малювання скасовано.")

    @Slot(list)
    def _on_zone_completed(self, points: list[tuple[int, int]]) -> None:
        self._reset_drawing_buttons()
        name, ok = QInputDialog.getText(self, "Ім'я зони", "Введіть ім'я зони:")
        if not ok or not name.strip():
            self._status_label.setText("Зону не створено (немає імені).")
            return
        self._services.zones().append(Zone(name=name.strip(), points=points))
        self._services.save_zones()
        self._refresh()
        self._status_label.setText(f"Зону '{name.strip()}' додано та збережено.")

    def _reset_drawing_buttons(self) -> None:
        self._finish_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._new_zone_btn.setEnabled(True)

    @Slot()
    def _on_delete(self) -> None:
        row = self._list_widget.currentRow()
        if row < 0:
            return
        zones = self._services.zones()
        if not (0 <= row < len(zones)):
            return
        z = zones[row]
        reply = QMessageBox.question(
            self, "Видалити зону", f"Видалити зону '{z.name}'?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        del zones[row]
        self._services.save_zones()
        self._refresh()
        self._status_label.setText(f"Видалено: '{z.name}' (зміни збережено).")
