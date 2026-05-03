from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.core.alert_event import AlertEvent
from app.core.offline_analyzer import OfflineAnalyzer
from app.core.pipeline import Detector
from app.services import Services
from app.ui.widgets.clip_player import ClipPlayer

VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".webm", ".m4v"}
EVENT_DATA_ROLE = Qt.ItemDataRole.UserRole


def _format_video_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:05.2f}"
    return f"{m:02d}:{s:05.2f}"


class VideoAnalysisTab(QWidget):
    def __init__(self, services: Services) -> None:
        super().__init__()
        self._services = services
        self._worker: OfflineAnalyzer | None = None
        self._events: list[AlertEvent] = []
        self._video_path: Path | None = None

        self.setAcceptDrops(True)

        self._path_label = QLabel("Перетащите видеофайл сюда или выберите кнопкой 'Открыть...'")
        self._path_label.setStyleSheet(
            "padding: 6px 10px; border: 2px dashed #444; color: #888;"
        )

        self._open_btn = QPushButton("Открыть...")
        self._open_btn.clicked.connect(self._on_open_file)

        self._person_check = QCheckBox("Люди")
        self._person_check.setChecked(True)
        self._face_check = QCheckBox("Лица")
        self._face_check.setChecked(True)
        self._tracking_check = QCheckBox("Трекинг + loitering")
        self._tracking_check.setChecked(False)
        self._tracking_check.setToolTip(
            "ByteTrack: track_id для каждого человека, плюс правило loitering "
            "(>3 сек видео-времени в зоне)."
        )

        self._start_btn = QPushButton("▶ Анализировать")
        self._start_btn.clicked.connect(self._on_start)
        self._start_btn.setEnabled(False)

        self._stop_btn = QPushButton("⏹ Стоп")
        self._stop_btn.clicked.connect(self._on_stop)
        self._stop_btn.setEnabled(False)

        self._clear_btn = QPushButton("Очистить отчёт")
        self._clear_btn.clicked.connect(self._clear_events)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)

        self._player = ClipPlayer(default_loop=False)

        self._events_list = QListWidget()
        self._events_list.itemActivated.connect(self._on_event_activated)
        self._events_list.itemSelectionChanged.connect(self._on_event_activated_via_selection)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888; padding: 4px;")
        self._status_label.setWordWrap(True)

        file_row = QHBoxLayout()
        file_row.addWidget(self._path_label, 1)
        file_row.addWidget(self._open_btn)

        controls_row = QHBoxLayout()
        controls_row.addWidget(QLabel("Детекторы:"))
        controls_row.addWidget(self._person_check)
        controls_row.addWidget(self._face_check)
        controls_row.addWidget(self._tracking_check)
        controls_row.addStretch(1)
        controls_row.addWidget(self._start_btn)
        controls_row.addWidget(self._stop_btn)
        controls_row.addWidget(self._clear_btn)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("События (двойной клик — перейти к моменту):"))
        right_layout.addWidget(self._events_list, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._player)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addLayout(file_row)
        layout.addLayout(controls_row)
        layout.addWidget(self._progress)
        layout.addWidget(splitter, 1)
        layout.addWidget(self._status_label)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        md = event.mimeData()
        if not md.hasUrls():
            return
        for url in md.urls():
            local = url.toLocalFile()
            if local and Path(local).suffix.lower() in VIDEO_EXTS:
                event.acceptProposedAction()
                return

    def dropEvent(self, event: QDropEvent) -> None:
        md = event.mimeData()
        for url in md.urls():
            local = url.toLocalFile()
            if local and Path(local).suffix.lower() in VIDEO_EXTS:
                self._set_video_path(Path(local))
                event.acceptProposedAction()
                return

    @Slot()
    def _on_open_file(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(VIDEO_EXTS))
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите видеофайл", "",
            f"Видео ({exts});;Все файлы (*.*)",
        )
        if path:
            self._set_video_path(Path(path))

    def _set_video_path(self, path: Path) -> None:
        if not path.exists():
            QMessageBox.warning(self, "Файл не найден", str(path))
            return
        self._video_path = path
        self._path_label.setText(f"Файл: {path}")
        self._path_label.setStyleSheet(
            "padding: 6px 10px; border: 1px solid #2c5; color: #ccc;"
        )
        self._player.load(path, autoplay=False)
        self._start_btn.setEnabled(True)
        self._status_label.setText("Готов к анализу.")

    @Slot()
    def _on_start(self) -> None:
        if self._video_path is None or self._worker is not None:
            return

        detectors: list[Detector] = []
        if self._person_check.isChecked():
            self._status_label.setText("Загрузка модели YOLO...")
            QApplication.processEvents()
            try:
                detectors.append(self._services.person_detector())
            except Exception as exc:
                self._status_label.setText(f"Ошибка YOLO: {exc}")
                return
        if self._face_check.isChecked():
            self._status_label.setText("Загрузка моделей распознавания лиц...")
            QApplication.processEvents()
            try:
                detectors.append(self._services.face_recognizer())
            except Exception as exc:
                self._status_label.setText(f"Ошибка детекции лиц: {exc}")
                return

        if not detectors:
            QMessageBox.information(self, "Ничего не выбрано", "Включите хотя бы один детектор.")
            return

        zones = list(self._services.zones())
        tracker = None
        if self._tracking_check.isChecked() and self._person_check.isChecked():
            try:
                tracker = self._services.create_tracker()
            except Exception as exc:
                self._status_label.setText(f"Ошибка трекера: {exc}")
                return

        worker = OfflineAnalyzer(
            video_path=self._video_path,
            detectors=detectors,
            zones=zones,
            tracker=tracker,
        )
        worker.progress.connect(self._on_progress)
        worker.event_found.connect(self._on_event_found)
        worker.finished_ok.connect(self._on_finished_ok)
        worker.error.connect(self._on_error)
        worker.start()

        self._worker = worker
        self._clear_events()
        self._set_running(True)
        self._status_label.setText(f"Анализ: {self._video_path.name} ...")

    @Slot()
    def _on_stop(self) -> None:
        if self._worker is None:
            return
        self._worker.stop()
        self._worker = None
        self._set_running(False)
        self._status_label.setText("Анализ остановлен пользователем.")

    @Slot(int, int)
    def _on_progress(self, frame_idx: int, total: int) -> None:
        if total > 0:
            pct = int(frame_idx * 100 / total)
            self._progress.setValue(pct)
            self._progress.setFormat(f"{pct}%  ({frame_idx} / {total})")
        else:
            self._progress.setFormat(f"{frame_idx} кадров")

    @Slot(object)
    def _on_event_found(self, ev: AlertEvent) -> None:
        self._events.append(ev)
        time_str = _format_video_time(ev.timestamp)
        text = f"{time_str}   {ev.kind:18}   {ev.title}"
        if ev.detail:
            text += f": {ev.detail}"
        item = QListWidgetItem(text)
        item.setData(EVENT_DATA_ROLE, len(self._events) - 1)
        self._events_list.addItem(item)

    @Slot(int, float)
    def _on_finished_ok(self, frames: int, elapsed: float) -> None:
        self._worker = None
        self._set_running(False)
        speed = frames / elapsed if elapsed > 0 else 0
        self._progress.setValue(100)
        self._status_label.setText(
            f"Готово. Кадров: {frames}, время: {elapsed:.1f}s, "
            f"скорость: {speed:.1f} fps. Событий найдено: {len(self._events)}"
        )

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._worker = None
        self._set_running(False)
        self._status_label.setText(f"Ошибка: {msg}")

    @Slot(QListWidgetItem)
    def _on_event_activated(self, item: QListWidgetItem) -> None:
        idx = item.data(EVENT_DATA_ROLE)
        if not isinstance(idx, int) or not (0 <= idx < len(self._events)):
            return
        ev = self._events[idx]
        self._player.seek_to(ev.timestamp, autoplay=True)

    @Slot()
    def _on_event_activated_via_selection(self) -> None:
        items = self._events_list.selectedItems()
        if not items:
            return
        self._on_event_activated(items[0])

    def _clear_events(self) -> None:
        self._events.clear()
        self._events_list.clear()
        self._progress.setValue(0)
        self._progress.setFormat("")

    def _set_running(self, running: bool) -> None:
        self._start_btn.setEnabled(not running and self._video_path is not None)
        self._stop_btn.setEnabled(running)
        self._open_btn.setEnabled(not running)
        self._person_check.setEnabled(not running)
        self._face_check.setEnabled(not running)
        self._tracking_check.setEnabled(not running)
        self._clear_btn.setEnabled(not running)

    def cleanup(self) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._worker = None
        self._player.stop()
