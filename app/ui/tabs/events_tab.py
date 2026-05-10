from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.alert_event import AlertEvent
from app.services import Services
from app.ui.widgets.clip_player import ClipPlayer

_SEARCH_THRESHOLD = 0.4
_THUMB_HEIGHT = 200


class EventsTab(QWidget):
    def __init__(self, services: Services) -> None:
        super().__init__()
        self._services = services
        self._events: list[AlertEvent] = []
        # Список схожостей паралельно до self._events у режимі пошуку.
        # У звичайному режимі — пустий.
        self._similarities: list[float] = []
        self._search_mode = False

        self._kind_combo = QComboBox()
        self._kind_combo.addItem("Усі типи", "")
        self._kind_combo.currentIndexChanged.connect(self._refresh)

        self._refresh_btn = QPushButton("Оновити")
        self._refresh_btn.clicked.connect(self._refresh)

        self._search_btn = QPushButton("Пошук по обличчю...")
        self._search_btn.clicked.connect(self._on_search_by_face)
        self._search_btn.setToolTip(
            "Завантажити фото з обличчям → знайти всі події, де SFace-вектор "
            f"має cosine similarity ≥ {_SEARCH_THRESHOLD} до фото."
        )

        self._clear_search_btn = QPushButton("Очистити пошук")
        self._clear_search_btn.clicked.connect(self._on_clear_search)
        self._clear_search_btn.setVisible(False)

        self._clear_btn = QPushButton("Очистити журнал")
        self._clear_btn.clicked.connect(self._on_clear)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Час", "Тип", "Опис", "Зона", "Кліп"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        self._player = ClipPlayer()

        self._snapshot_label = QLabel("(знімок обличчя відсутній)")
        self._snapshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._snapshot_label.setMinimumHeight(_THUMB_HEIGHT)
        self._snapshot_label.setMaximumHeight(_THUMB_HEIGHT)
        self._snapshot_label.setStyleSheet(
            "background-color: #111; color: #555; border: 1px solid #333;"
        )

        self._add_to_persons_btn = QPushButton("Додати до персон")
        self._add_to_persons_btn.clicked.connect(self._on_add_to_persons)
        self._add_to_persons_btn.setEnabled(False)
        self._add_to_persons_btn.setToolTip(
            "Створює нову персону у whitelist на основі знімка цієї події. "
            "Доступно для подій 'unknown_face' зі збереженим знімком."
        )

        self._detail_label = QLabel("Виберіть подію в таблиці зліва.")
        self._detail_label.setWordWrap(True)
        self._detail_label.setStyleSheet("color: #aaa; padding: 4px;")

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888; padding: 4px;")

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Тип:"))
        toolbar.addWidget(self._kind_combo)
        toolbar.addWidget(self._refresh_btn)
        toolbar.addWidget(self._search_btn)
        toolbar.addWidget(self._clear_search_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(self._clear_btn)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self._snapshot_label)
        right_layout.addWidget(self._player, 1)
        right_layout.addWidget(self._add_to_persons_btn)
        right_layout.addWidget(self._detail_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._table)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(splitter, 1)
        layout.addWidget(self._status_label)

        self._services.alerts.alert_fired.connect(self._on_new_alert)
        self._refresh()

    @Slot()
    def _refresh(self) -> None:
        if self._search_mode:
            # У режимі пошуку звичайне refresh не перевантажує таблицю,
            # щоб не змішувати результати з повним журналом.
            self._refresh_kinds()
            return
        kind = self._kind_combo.currentData() or None
        self._events = self._services.events_repo.query(kind=kind, limit=500)
        self._similarities = []
        self._render_table()
        self._refresh_kinds()

        total = self._services.events_repo.count()
        shown = len(self._events)
        self._status_label.setText(f"Усього в БД: {total}  |  Показано: {shown}")

    def _render_table(self) -> None:
        if self._search_mode:
            self._table.setColumnCount(6)
            self._table.setHorizontalHeaderLabels(
                ["Час", "Тип", "Опис", "Зона", "Кліп", "Схожість"]
            )
            header = self._table.horizontalHeader()
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        else:
            self._table.setColumnCount(5)
            self._table.setHorizontalHeaderLabels(
                ["Час", "Тип", "Опис", "Зона", "Кліп"]
            )

        self._table.setRowCount(0)
        for i, ev in enumerate(self._events):
            row = self._table.rowCount()
            self._table.insertRow(row)
            time_str = datetime.fromtimestamp(ev.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            clip_str = ev.clip_path.name if ev.clip_path else "—"
            values = [
                time_str, ev.kind,
                ev.title + ((": " + ev.detail) if ev.detail else ""),
                ev.zone_name or "—", clip_str,
            ]
            if self._search_mode:
                sim = self._similarities[i] if i < len(self._similarities) else 0.0
                values.append(f"{sim * 100:.1f}%")
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(row, col, item)

    @Slot()
    def _on_search_by_face(self) -> None:
        if not self._services.is_face_recognizer_loaded:
            QMessageBox.information(
                self, "Базу не завантажено",
                "Відкрийте вкладку «Персони» і натисніть «Завантажити базу облич»,\n"
                "щоб ініціалізувати моделі YuNet+SFace для пошуку.",
            )
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Виберіть фото для пошуку", "",
            "Зображення (*.jpg *.jpeg *.png *.bmp *.webp);;Усі файли (*.*)",
        )
        if not path:
            return

        self._status_label.setText("Витягуємо embedding з фото...")
        QApplication.processEvents()
        try:
            emb = self._services.face_recognizer().embedding_for_image(Path(path))
        except Exception as exc:
            QMessageBox.warning(self, "Помилка", f"Не вдалося обробити фото: {exc}")
            self._status_label.setText("")
            return
        if emb is None:
            QMessageBox.warning(
                self, "Обличчя не знайдено",
                "На обраному фото не вдалося детектувати обличчя. "
                "Спробуйте чіткіший знімок з добре видимим обличчям.",
            )
            self._status_label.setText("")
            return

        self._status_label.setText("Шукаємо схожі обличчя в журналі...")
        QApplication.processEvents()
        matches = self._services.events_repo.find_by_embedding(
            emb, threshold=_SEARCH_THRESHOLD,
        )

        self._search_mode = True
        self._events = [ev for ev, _sim in matches]
        self._similarities = [sim for _ev, sim in matches]
        self._render_table()
        self._clear_search_btn.setVisible(True)
        self._status_label.setText(
            f"Пошук по обличчю: {Path(path).name} "
            f"| знайдено {len(matches)} подій з схожістю ≥ {_SEARCH_THRESHOLD}"
        )

    @Slot()
    def _on_clear_search(self) -> None:
        self._search_mode = False
        self._clear_search_btn.setVisible(False)
        self._refresh()

    def _refresh_kinds(self) -> None:
        current = self._kind_combo.currentData()
        kinds = self._services.events_repo.distinct_kinds()

        self._kind_combo.blockSignals(True)
        self._kind_combo.clear()
        self._kind_combo.addItem("Усі типи", "")
        for k in kinds:
            self._kind_combo.addItem(k, k)
        if current:
            idx = self._kind_combo.findData(current)
            if idx >= 0:
                self._kind_combo.setCurrentIndex(idx)
        self._kind_combo.blockSignals(False)

    @Slot()
    def _on_selection_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            self._player.load(None)
            self._detail_label.setText("Виберіть подію.")
            self._update_snapshot(None)
            self._add_to_persons_btn.setEnabled(False)
            return
        row = rows[0].row()
        if not (0 <= row < len(self._events)):
            return
        ev = self._events[row]
        self._player.load(ev.clip_path)
        self._detail_label.setText(self._format_event_detail(ev))
        self._update_snapshot(ev.snapshot_path)
        self._add_to_persons_btn.setEnabled(
            ev.snapshot_path is not None and ev.snapshot_path.exists()
        )

    def _update_snapshot(self, path: Path | None) -> None:
        if path is None or not path.exists():
            self._snapshot_label.clear()
            self._snapshot_label.setText("(знімок обличчя відсутній)")
            return
        pix = QPixmap(str(path))
        if pix.isNull():
            self._snapshot_label.clear()
            self._snapshot_label.setText("(знімок не вдалося завантажити)")
            return
        scaled = pix.scaledToHeight(
            _THUMB_HEIGHT - 8, Qt.TransformationMode.SmoothTransformation,
        )
        self._snapshot_label.setPixmap(scaled)

    @Slot()
    def _on_add_to_persons(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if not (0 <= row < len(self._events)):
            return
        ev = self._events[row]
        if ev.snapshot_path is None or not ev.snapshot_path.exists():
            return
        if not self._services.is_face_recognizer_loaded:
            QMessageBox.information(
                self, "Базу не завантажено",
                "Відкрийте вкладку «Персони» і натисніть «Завантажити базу облич».",
            )
            return
        name, ok = QInputDialog.getText(self, "Додати до персон", "Ім'я нової персони:")
        if not ok or not name.strip():
            return
        recognizer = self._services.face_recognizer()
        try:
            if ev.face_embedding is not None:
                # Якщо в події вже є SFace-вектор з real-time recognition —
                # використовуємо його напряму. YuNet погано працює на close-up
                # crop'ах (snapshot — це обличчя з 20% padding), тож повторна
                # детекція з фото часто падає з 'Обличчя не знайдено'.
                count = recognizer.add_person_with_embedding(
                    name.strip(), ev.snapshot_path, ev.face_embedding,
                )
            else:
                count = recognizer.add_person(name.strip(), ev.snapshot_path)
        except Exception as exc:
            QMessageBox.warning(self, "Не вдалося додати", str(exc))
            return
        self._status_label.setText(
            f"Додано до персон: {name.strip()} (фото: {count})"
        )

    @Slot(object)
    def _on_new_alert(self, ev: AlertEvent) -> None:
        self._refresh()

    @Slot()
    def _on_clear(self) -> None:
        reply = QMessageBox.question(
            self, "Очистити журнал",
            "Видалити всі записи з БД? Файли кліпів у data/clips/ залишаться.",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._services.events_repo.delete_all()
        self._refresh()

    def _format_event_detail(self, ev: AlertEvent) -> str:
        parts = [
            f"<b>{ev.title}</b>",
            f"Тип: <code>{ev.kind}</code>",
            f"Опис: {ev.detail or '—'}",
            f"Час: {datetime.fromtimestamp(ev.timestamp).strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        if ev.zone_name:
            parts.append(f"Зона: <b>{ev.zone_name}</b>")
        if ev.detection_bbox:
            parts.append(f"BBox: {ev.detection_bbox}")
        if ev.clip_path:
            parts.append(f"Кліп: <code>{ev.clip_path}</code>")
        else:
            parts.append("Кліп: відсутній")
        return "<br>".join(parts)

    def cleanup(self) -> None:
        self._player.stop()
