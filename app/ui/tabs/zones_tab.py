from pathlib import Path

import cv2
from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QFileDialog,
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

        self._snapshot_btn = QPushButton("Снимок из Live")
        self._snapshot_btn.clicked.connect(self._on_snapshot_live)

        self._open_image_btn = QPushButton("Открыть файл...")
        self._open_image_btn.clicked.connect(self._on_open_image)

        self._new_zone_btn = QPushButton("+ Новая зона")
        self._new_zone_btn.clicked.connect(self._on_new_zone)

        self._finish_btn = QPushButton("Закрыть зону")
        self._finish_btn.clicked.connect(self._on_finish)
        self._finish_btn.setEnabled(False)

        self._cancel_btn = QPushButton("Отмена")
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._cancel_btn.setEnabled(False)

        self._delete_btn = QPushButton("Удалить выбранную")
        self._delete_btn.clicked.connect(self._on_delete)

        self._save_btn = QPushButton("Сохранить")
        self._save_btn.clicked.connect(self._on_save)

        self._list_widget = QListWidget()
        self._list_widget.setMaximumWidth(240)

        self._canvas = ZoneCanvas()
        self._canvas.zoneCompleted.connect(self._on_zone_completed)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888; padding: 4px;")
        self._status_label.setWordWrap(True)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._snapshot_btn)
        toolbar.addWidget(self._open_image_btn)
        sep = QLabel(" │ ")
        sep.setStyleSheet("color: #444;")
        toolbar.addWidget(sep)
        toolbar.addWidget(self._new_zone_btn)
        toolbar.addWidget(self._finish_btn)
        toolbar.addWidget(self._cancel_btn)
        toolbar.addWidget(self._delete_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(self._save_btn)

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
            self._list_widget.addItem(f"{z.name}  ({len(z.points)} точек)")
        suffix = ""
        if zones:
            suffix = "  Чтобы изменения применились в Live, переподключитесь к источнику."
        self._status_label.setText(f"Зон: {len(zones)}.{suffix}")

    @Slot()
    def _on_snapshot_live(self) -> None:
        frame = self._services.latest_frame
        if frame is None:
            QMessageBox.information(
                self,
                "Нет кадра",
                "Сначала запусти источник на вкладке Live, дождись пары кадров и вернись сюда.",
            )
            return
        self._canvas.set_background(frame)
        self._status_label.setText(
            "Снимок получен. Нажми '+ Новая зона' и кликай по точкам полигона."
        )

    @Slot()
    def _on_open_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть изображение", "",
            "Изображения (*.jpg *.jpeg *.png *.bmp);;Все файлы (*.*)",
        )
        if not path:
            return
        img = cv2.imread(path)
        if img is None:
            QMessageBox.warning(self, "Ошибка", "Не удалось прочитать изображение.")
            return
        self._canvas.set_background(img)
        self._status_label.setText(f"Загружено: {Path(path).name}")

    @Slot()
    def _on_new_zone(self) -> None:
        if not self._canvas.has_background:
            QMessageBox.information(
                self, "Нет снимка", "Сначала загрузи снимок (кнопки слева).",
            )
            return
        self._canvas.start_drawing()
        self._finish_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)
        self._new_zone_btn.setEnabled(False)
        self._status_label.setText(
            "Кликай по точкам контура. ПКМ или 'Закрыть зону' — завершить (нужно ≥3 точки)."
        )

    @Slot()
    def _on_finish(self) -> None:
        if not self._canvas.finish_drawing():
            QMessageBox.information(
                self, "Мало точек", "Зона должна содержать минимум 3 точки.",
            )

    @Slot()
    def _on_cancel(self) -> None:
        self._canvas.cancel_drawing()
        self._reset_drawing_buttons()
        self._status_label.setText("Рисование отменено.")

    @Slot(list)
    def _on_zone_completed(self, points: list[tuple[int, int]]) -> None:
        self._reset_drawing_buttons()
        name, ok = QInputDialog.getText(self, "Имя зоны", "Введите имя зоны:")
        if not ok or not name.strip():
            self._status_label.setText("Зона не создана (нет имени).")
            return
        self._services.zones().append(Zone(name=name.strip(), points=points))
        self._refresh()
        self._status_label.setText(
            f"Зона '{name.strip()}' добавлена. Не забудь 'Сохранить'."
        )

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
            self, "Удалить зону", f"Удалить зону '{z.name}'?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        del zones[row]
        self._refresh()
        self._status_label.setText(f"Удалено: '{z.name}'. Не забудь 'Сохранить'.")

    @Slot()
    def _on_save(self) -> None:
        self._services.save_zones()
        zones = self._services.zones()
        self._status_label.setText(f"Сохранено зон: {len(zones)} → data/zones.json")
