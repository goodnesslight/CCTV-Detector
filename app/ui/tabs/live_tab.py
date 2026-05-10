from PySide6.QtCore import QTimer, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.alert_event import AlertEvent
from app.core.pipeline import DetectionPipeline, Detector
from app.core.types import ProcessingResult
from app.core.video_source import rtsp_stream, usb_camera
from app.core.video_worker import VideoWorker
from app.services import Services
from app.ui.widgets.camera_view import CameraView

SOURCE_USB = 0
SOURCE_RTSP = 1


class LiveTab(QWidget):
    def __init__(self, services: Services) -> None:
        super().__init__()
        self._services = services
        self._worker: VideoWorker | None = None

        self._type_combo = QComboBox()
        self._type_combo.addItems(["USB-камера", "RTSP-потік"])
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)

        self._spec_input = QLineEdit("0")
        self._spec_input.setPlaceholderText("Індекс камери (0, 1, ...)")

        self._person_check = QCheckBox("Люди (YOLO)")
        self._person_check.setChecked(True)
        self._face_check = QCheckBox("Обличчя (YuNet + SFace)")
        self._face_check.setChecked(True)
        self._weapon_check = QCheckBox("Холодна зброя")
        self._weapon_check.setChecked(True)
        self._weapon_check.setToolTip(
            "Детекція ножів через YOLO11n. Точність обмежена — публічний "
            "датасет містить ножі переважно в кухонних контекстах."
        )
        self._tracking_check = QCheckBox("Трекінг + loitering")
        self._tracking_check.setChecked(False)
        self._tracking_check.setToolTip(
            "ByteTrack: присвоює постійний ID кожній людині та фіксує тривале "
            "перебування в зоні (>5 сек)."
        )

        self._toggle_btn = QPushButton("Підключитися")
        self._toggle_btn.clicked.connect(self._toggle_source)

        self._status_label = QLabel("Джерело не підключене")
        self._status_label.setStyleSheet("color: #888; padding: 4px;")
        self._counts_label = QLabel("")
        self._counts_label.setStyleSheet("color: #4ade80; padding: 4px; font-weight: bold;")

        self._alert_banner = QLabel("")
        self._alert_banner.setStyleSheet(
            "background-color: #c62828; color: white; "
            "font-size: 14px; font-weight: bold; padding: 8px 12px; border-radius: 4px;"
        )
        self._alert_banner.hide()
        self._alert_banner_timer = QTimer(self)
        self._alert_banner_timer.setSingleShot(True)
        self._alert_banner_timer.timeout.connect(self._alert_banner.hide)

        self._camera_view = CameraView()
        self._services.alerts.alert_fired.connect(self._on_alert)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Джерело:"))
        controls.addWidget(self._type_combo)
        controls.addWidget(self._spec_input, 1)
        controls.addWidget(self._person_check)
        controls.addWidget(self._face_check)
        controls.addWidget(self._weapon_check)
        controls.addWidget(self._tracking_check)
        controls.addWidget(self._toggle_btn)

        status_row = QHBoxLayout()
        status_row.addWidget(self._status_label, 1)
        status_row.addWidget(self._counts_label)

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addLayout(status_row)
        layout.addWidget(self._alert_banner)
        layout.addWidget(self._camera_view, 1)

    @Slot(int)
    def _on_type_changed(self, idx: int) -> None:
        if idx == SOURCE_USB:
            self._spec_input.setText("0")
            self._spec_input.setPlaceholderText("Індекс камери (0, 1, ...)")
        else:
            self._spec_input.clear()
            self._spec_input.setPlaceholderText("rtsp://user:pass@host:port/stream")

    @Slot()
    def _toggle_source(self) -> None:
        if self._worker is not None:
            self._stop_source()
        else:
            self._start_source()

    def _start_source(self) -> None:
        spec = self._spec_input.text().strip()
        if not spec:
            self._status_label.setText("Вкажіть джерело")
            return

        idx = self._type_combo.currentIndex()
        if idx == SOURCE_USB:
            try:
                source = usb_camera(int(spec))
            except ValueError:
                self._status_label.setText("Індекс камери має бути числом")
                return
        else:
            source = rtsp_stream(spec)

        detectors: list[Detector] = []
        if self._person_check.isChecked():
            self._status_label.setText("Завантаження моделі детекції людей...")
            QApplication.processEvents()
            try:
                detectors.append(self._services.person_detector())
            except Exception as exc:
                self._status_label.setText(f"Помилка YOLO: {exc}")
                return

        if self._face_check.isChecked():
            self._status_label.setText("Завантаження моделей розпізнавання облич...")
            QApplication.processEvents()
            try:
                detectors.append(self._services.face_recognizer())
            except Exception as exc:
                self._status_label.setText(f"Помилка моделі облич: {exc}")
                return

        if self._weapon_check.isChecked():
            self._status_label.setText("Завантаження детектора зброї...")
            QApplication.processEvents()
            try:
                detectors.append(self._services.weapon_detector())
            except Exception as exc:
                self._status_label.setText(f"Помилка детектора зброї: {exc}")
                return

        zones = list(self._services.zones())
        tracker = None
        if self._tracking_check.isChecked() and self._person_check.isChecked():
            try:
                tracker = self._services.create_tracker()
            except Exception as exc:
                self._status_label.setText(f"Помилка трекера: {exc}")
                return
        if detectors or zones:
            processor = DetectionPipeline(detectors, zones=zones, tracker=tracker)
        else:
            processor = None

        worker = VideoWorker(source, processor=processor)
        worker.result_ready.connect(self._on_result)
        worker.error.connect(self._on_worker_error)
        worker.stream_ended.connect(self._on_stream_ended)
        worker.start()

        self._worker = worker
        active = []
        if self._person_check.isChecked():
            active.append("YOLO")
        if self._face_check.isChecked():
            active.append("YuNet+SFace")
        if self._weapon_check.isChecked():
            active.append("Weapon")
        if tracker is not None:
            active.append("ByteTrack")
        suffix = f" | детектори: {' + '.join(active)}" if active else ""
        self._status_label.setText(f"Підключено: {source.descriptor}{suffix}")
        self._toggle_btn.setText("Відключитися")
        self._set_controls_enabled(False)

    def _stop_source(self) -> None:
        if self._worker is None:
            return
        self._worker.stop()
        self._worker = None
        self._camera_view.clear()
        self._status_label.setText("Джерело не підключене")
        self._counts_label.setText("")
        self._alert_banner.hide()
        self._services.alerts.reset()
        self._toggle_btn.setText("Підключитися")
        self._set_controls_enabled(True)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self._type_combo.setEnabled(enabled)
        self._spec_input.setEnabled(enabled)
        self._person_check.setEnabled(enabled)
        self._face_check.setEnabled(enabled)
        self._weapon_check.setEnabled(enabled)
        self._tracking_check.setEnabled(enabled)

    @Slot(object)
    def _on_result(self, result: ProcessingResult) -> None:
        self._services.latest_frame = result.frame.image
        self._camera_view.display_frame(result.image)
        persons = sum(1 for d in result.detections if d.label == "person")
        known = sum(1 for d in result.detections if d.label == "known_face")
        unknown = sum(1 for d in result.detections if d.label == "unknown_face")
        weapons = sum(1 for d in result.detections if d.label == "weapon")
        in_zone = sum(1 for d in result.detections if d.zone_name is not None)
        parts = []
        if persons:
            parts.append(f"людей: {persons}")
        if known:
            parts.append(f"знайомих: {known}")
        if unknown:
            parts.append(f"чужих: {unknown}")
        if weapons:
            parts.append(f"зброя: {weapons}")
        if in_zone:
            parts.append(f"у зоні: {in_zone}")
        self._counts_label.setText(" | ".join(parts))

        self._services.alerts.on_frame(result)

    @Slot(object)
    def _on_alert(self, ev: AlertEvent) -> None:
        text = f"⚠ {ev.title}: {ev.detail}"
        if ev.clip_path is not None:
            text += f"   →   кліп: {ev.clip_path.name}"
        self._alert_banner.setText(text)
        self._alert_banner.show()
        self._alert_banner_timer.start(5000)
        self._camera_view.trigger_alert()

    @Slot(str)
    def _on_worker_error(self, message: str) -> None:
        self._status_label.setText(f"Помилка: {message}")
        self._stop_source()

    @Slot()
    def _on_stream_ended(self) -> None:
        self._status_label.setText("Відтворення завершене")
        self._stop_source()

    def cleanup(self) -> None:
        self._stop_source()
