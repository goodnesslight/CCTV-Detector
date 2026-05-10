from datetime import datetime

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
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


class EventsTab(QWidget):
    def __init__(self, services: Services) -> None:
        super().__init__()
        self._services = services
        self._events: list[AlertEvent] = []

        self._kind_combo = QComboBox()
        self._kind_combo.addItem("Усі типи", "")
        self._kind_combo.currentIndexChanged.connect(self._refresh)

        self._refresh_btn = QPushButton("Оновити")
        self._refresh_btn.clicked.connect(self._refresh)

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

        self._detail_label = QLabel("Виберіть подію в таблиці зліва.")
        self._detail_label.setWordWrap(True)
        self._detail_label.setStyleSheet("color: #aaa; padding: 4px;")

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888; padding: 4px;")

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Тип:"))
        toolbar.addWidget(self._kind_combo)
        toolbar.addWidget(self._refresh_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(self._clear_btn)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self._player, 1)
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
        kind = self._kind_combo.currentData() or None
        self._events = self._services.events_repo.query(kind=kind, limit=500)

        self._table.setRowCount(0)
        for ev in self._events:
            row = self._table.rowCount()
            self._table.insertRow(row)
            time_str = datetime.fromtimestamp(ev.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            clip_str = ev.clip_path.name if ev.clip_path else "—"
            for col, value in enumerate([
                time_str, ev.kind, ev.title + ((": " + ev.detail) if ev.detail else ""),
                ev.zone_name or "—", clip_str,
            ]):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(row, col, item)

        self._refresh_kinds()

        total = self._services.events_repo.count()
        shown = len(self._events)
        self._status_label.setText(f"Усього в БД: {total}  |  Показано: {shown}")

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
            return
        row = rows[0].row()
        if not (0 <= row < len(self._events)):
            return
        ev = self._events[row]
        self._player.load(ev.clip_path)
        self._detail_label.setText(self._format_event_detail(ev))

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
