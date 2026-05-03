from pathlib import Path

from PySide6.QtCore import Qt, Slot
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
    QVBoxLayout,
    QWidget,
)

from app.services import Services

NAME_ROLE = Qt.ItemDataRole.UserRole


class PersonsTab(QWidget):
    def __init__(self, services: Services) -> None:
        super().__init__()
        self._services = services
        self._loaded = False

        self._list_widget = QListWidget()
        self._list_widget.setStyleSheet("font-size: 14px;")

        self._load_btn = QPushButton("Загрузить базу лиц")
        self._load_btn.clicked.connect(self._on_load)

        self._add_btn = QPushButton("Добавить персону...")
        self._add_btn.clicked.connect(self._on_add)
        self._add_btn.setEnabled(False)

        self._add_photo_btn = QPushButton("Добавить фото к выбранной")
        self._add_photo_btn.clicked.connect(self._on_add_photo)
        self._add_photo_btn.setEnabled(False)

        self._remove_btn = QPushButton("Удалить персону")
        self._remove_btn.clicked.connect(self._on_remove)
        self._remove_btn.setEnabled(False)

        self._status_label = QLabel(
            "База не загружена. Нажмите 'Загрузить базу лиц' "
            "(первый запуск качает ~38 МБ моделей YuNet + SFace в data/models/)."
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
        layout.addWidget(self._list_widget, 1)

    @Slot()
    def _on_load(self) -> None:
        self._status_label.setText("Загрузка моделей распознавания лиц...")
        self._load_btn.setEnabled(False)
        QApplication.processEvents()
        try:
            self._services.face_recognizer()
        except Exception as exc:
            self._status_label.setText(f"Ошибка загрузки модели: {exc}")
            self._load_btn.setEnabled(True)
            return
        self._loaded = True
        self._add_btn.setEnabled(True)
        self._add_photo_btn.setEnabled(True)
        self._remove_btn.setEnabled(True)
        self._refresh_list()

    @Slot()
    def _on_add(self) -> None:
        name, ok = QInputDialog.getText(self, "Новая персона", "Имя:")
        if not ok or not name.strip():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите фото с лицом",
            "",
            "Изображения (*.jpg *.jpeg *.png *.bmp *.webp);;Все файлы (*.*)",
        )
        if not path:
            return
        try:
            count = self._services.face_recognizer().add_person(name, Path(path))
            self._status_label.setText(f"Добавлен(о): {name} (фото: {count})")
        except Exception as exc:
            QMessageBox.warning(self, "Не удалось добавить", str(exc))
            return
        self._refresh_list()

    @Slot()
    def _on_add_photo(self) -> None:
        item = self._list_widget.currentItem()
        if item is None:
            QMessageBox.information(self, "Выберите персону", "Сначала выберите персону в списке.")
            return
        name = item.data(NAME_ROLE)
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Доп. фото для {name}",
            "",
            "Изображения (*.jpg *.jpeg *.png *.bmp *.webp);;Все файлы (*.*)",
        )
        if not path:
            return
        try:
            count = self._services.face_recognizer().add_person(name, Path(path))
            self._status_label.setText(f"Фото добавлено: {name} (всего: {count})")
        except Exception as exc:
            QMessageBox.warning(self, "Не удалось добавить", str(exc))
            return
        self._refresh_list()

    @Slot()
    def _on_remove(self) -> None:
        item = self._list_widget.currentItem()
        if item is None:
            return
        name = item.data(NAME_ROLE)
        reply = QMessageBox.question(
            self, "Удалить персону",
            f"Удалить «{name}» из whitelist? Файлы фото также будут удалены.",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._services.face_recognizer().remove_person(name)
        self._status_label.setText(f"Удалено: {name}")
        self._refresh_list()

    def _refresh_list(self) -> None:
        if not self._loaded:
            return
        persons = self._services.face_recognizer().list_persons()
        self._list_widget.clear()
        for name, count in persons:
            item = QListWidgetItem(f"{name}  —  {count} фото")
            item.setData(NAME_ROLE, name)
            self._list_widget.addItem(item)
        total = sum(c for _, c in persons)
        self._status_label.setText(
            f"Персон: {len(persons)}  |  фото: {total}"
        )
