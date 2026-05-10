import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.services import Services

NAME_ROLE = Qt.ItemDataRole.UserRole
_REFRESH_INTERVAL_MS = 3000


def _format_last_seen(ts: float | None) -> str:
    if ts is None:
        return "ніколи"
    delta = time.time() - ts
    if delta < 60:
        return "щойно"
    if delta < 3600:
        return f"{int(delta // 60)} хв тому"
    if delta < 86400:
        return f"{int(delta // 3600)} год тому"
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")


class PersonsTab(QWidget):
    def __init__(self, services: Services) -> None:
        super().__init__()
        self._services = services
        self._loaded = False

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(_REFRESH_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._refresh_list)

        self._list_widget = QListWidget()
        self._list_widget.setStyleSheet("font-size: 14px;")

        self._empty_label = QLabel("Немає персон")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #666; font-size: 14px;")

        self._list_stack = QStackedWidget()
        self._list_stack.addWidget(self._empty_label)
        self._list_stack.addWidget(self._list_widget)
        self._list_stack.setCurrentIndex(0)

        self._load_btn = QPushButton("Завантажити базу облич")
        self._load_btn.clicked.connect(self._on_load)

        self._add_btn = QPushButton("Додати персону...")
        self._add_btn.clicked.connect(self._on_add)
        self._add_btn.setEnabled(False)

        self._add_photo_btn = QPushButton("Додати фото до вибраної")
        self._add_photo_btn.clicked.connect(self._on_add_photo)
        self._add_photo_btn.setEnabled(False)

        self._remove_btn = QPushButton("Видалити персону")
        self._remove_btn.clicked.connect(self._on_remove)
        self._remove_btn.setEnabled(False)

        self._status_label = QLabel(
            "Базу не завантажено. Натисніть 'Завантажити базу облич' "
            "(перший запуск завантажує ~38 МБ моделей YuNet + SFace у data/models/)."
        )
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #888; padding: 4px;")

        buttons = QHBoxLayout()
        buttons.addWidget(self._load_btn)
        buttons.addWidget(self._add_btn)
        buttons.addWidget(self._add_photo_btn)
        buttons.addWidget(self._remove_btn)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(self._status_label)
        layout.addWidget(self._list_stack, 1)

    @Slot()
    def _on_load(self) -> None:
        self._status_label.setText("Завантаження моделей розпізнавання облич...")
        self._load_btn.setEnabled(False)
        QApplication.processEvents()
        try:
            self._services.face_recognizer()
        except Exception as exc:
            self._status_label.setText(f"Помилка завантаження моделі: {exc}")
            self._load_btn.setEnabled(True)
            return
        self._loaded = True
        self._add_btn.setEnabled(True)
        self._add_photo_btn.setEnabled(True)
        self._remove_btn.setEnabled(True)
        self._refresh_list()
        if self.isVisible():
            self._refresh_timer.start()

    @Slot()
    def _on_add(self) -> None:
        name, ok = QInputDialog.getText(self, "Нова персона", "Ім'я:")
        if not ok or not name.strip():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Виберіть фото з обличчям",
            "",
            "Зображення (*.jpg *.jpeg *.png *.bmp *.webp);;Усі файли (*.*)",
        )
        if not path:
            return
        try:
            count = self._services.face_recognizer().add_person(name, Path(path))
            self._status_label.setText(f"Додано: {name} (фото: {count})")
        except Exception as exc:
            QMessageBox.warning(self, "Не вдалося додати", str(exc))
            return
        self._refresh_list()

    @Slot()
    def _on_add_photo(self) -> None:
        item = self._list_widget.currentItem()
        if item is None:
            QMessageBox.information(
                self, "Виберіть персону",
                "Спочатку виберіть персону у списку.",
            )
            return
        name = item.data(NAME_ROLE)
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Дод. фото для {name}",
            "",
            "Зображення (*.jpg *.jpeg *.png *.bmp *.webp);;Усі файли (*.*)",
        )
        if not path:
            return
        try:
            count = self._services.face_recognizer().add_person(name, Path(path))
            self._status_label.setText(f"Фото додано: {name} (всього: {count})")
        except Exception as exc:
            QMessageBox.warning(self, "Не вдалося додати", str(exc))
            return
        self._refresh_list()

    @Slot()
    def _on_remove(self) -> None:
        item = self._list_widget.currentItem()
        if item is None:
            return
        name = item.data(NAME_ROLE)
        reply = QMessageBox.question(
            self, "Видалити персону",
            f"Видалити «{name}» з whitelist? Файли фото та статистика появ також будуть видалені.",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._services.face_recognizer().remove_person(name)
        try:
            self._services.sightings_repo.delete(name)
        except Exception:
            pass
        self._status_label.setText(f"Видалено: {name}")
        self._refresh_list()

    def _refresh_list(self) -> None:
        if not self._loaded:
            return
        persons = self._services.face_recognizer().list_persons()
        try:
            stats = self._services.sightings_repo.stats()
        except Exception:
            stats = {}
        selected_name = None
        current = self._list_widget.currentItem()
        if current is not None:
            selected_name = current.data(NAME_ROLE)
        self._list_widget.clear()
        for name, count in persons:
            sightings, last_seen = stats.get(name, (0, None))
            text = (
                f"{name}  —  {count} фото  |  появи: {sightings}  "
                f"|  останній раз: {_format_last_seen(last_seen)}"
            )
            item = QListWidgetItem(text)
            item.setData(NAME_ROLE, name)
            self._list_widget.addItem(item)
            if name == selected_name:
                self._list_widget.setCurrentItem(item)
        self._list_stack.setCurrentIndex(1 if persons else 0)
        total = sum(c for _, c in persons)
        self._status_label.setText(
            f"Персон: {len(persons)}  |  фото: {total}"
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._loaded:
            self._refresh_list()
            self._refresh_timer.start()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._refresh_timer.stop()
