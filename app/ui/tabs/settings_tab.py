from dataclasses import asdict

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.settings import Settings
from app.services import Services


class SettingsTab(QWidget):
    def __init__(self, services: Services) -> None:
        super().__init__()
        self._services = services

        self._yolo_conf = self._make_spin(0.05, 0.95, 0.05, 2)
        self._face_match = self._make_spin(0.10, 0.95, 0.05, 2)
        self._face_det = self._make_spin(0.10, 0.95, 0.05, 2)

        self._cooldown = self._make_spin(0.0, 600.0, 1.0, 1, suffix=" с")
        self._loitering = self._make_spin(1.0, 600.0, 1.0, 1, suffix=" с")

        self._beep = QCheckBox("Звуковой сигнал (Beep)")
        self._tts = QCheckBox("Голосовое оповещение (TTS)")

        self._clip_pre = self._make_spin(0.0, 30.0, 0.5, 1, suffix=" с")
        self._clip_post = self._make_spin(0.5, 60.0, 0.5, 1, suffix=" с")

        detection_box = QGroupBox("Детекция")
        det_form = QFormLayout(detection_box)
        det_form.addRow("YOLO confidence:", self._yolo_conf)
        det_form.addRow("Face match (cosine):", self._face_match)
        det_form.addRow("Face detection score:", self._face_det)

        alerts_box = QGroupBox("Алерты")
        a_form = QFormLayout(alerts_box)
        a_form.addRow("Cooldown:", self._cooldown)
        a_form.addRow("Loitering порог:", self._loitering)
        a_form.addRow(self._beep)
        a_form.addRow(self._tts)

        clips_box = QGroupBox("Запись клипов")
        c_form = QFormLayout(clips_box)
        c_form.addRow("До события:", self._clip_pre)
        c_form.addRow("После события:", self._clip_post)

        self._apply_btn = QPushButton("Применить")
        self._apply_btn.clicked.connect(self._on_apply)
        self._reset_btn = QPushButton("Сбросить к значениям по умолчанию")
        self._reset_btn.clicked.connect(self._on_reset_defaults)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888; padding: 4px;")
        self._status_label.setWordWrap(True)

        bottom = QHBoxLayout()
        bottom.addWidget(self._apply_btn)
        bottom.addWidget(self._reset_btn)
        bottom.addStretch(1)

        content = QWidget()
        v = QVBoxLayout(content)
        v.addWidget(detection_box)
        v.addWidget(alerts_box)
        v.addWidget(clips_box)
        v.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addLayout(bottom)
        layout.addWidget(self._status_label)

        self._populate_from(self._services.settings)

    def _make_spin(
        self, lo: float, hi: float, step: float, decimals: int, suffix: str = "",
    ) -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setSingleStep(step)
        sb.setDecimals(decimals)
        if suffix:
            sb.setSuffix(suffix)
        return sb

    def _populate_from(self, s: Settings) -> None:
        self._yolo_conf.setValue(s.yolo_conf_threshold)
        self._face_match.setValue(s.face_match_threshold)
        self._face_det.setValue(s.face_det_threshold)
        self._cooldown.setValue(s.alert_cooldown_seconds)
        self._loitering.setValue(s.loitering_threshold_seconds)
        self._beep.setChecked(s.beep_enabled)
        self._tts.setChecked(s.tts_enabled)
        self._clip_pre.setValue(s.clip_pre_seconds)
        self._clip_post.setValue(s.clip_post_seconds)

    def _gather_into(self, s: Settings) -> None:
        s.yolo_conf_threshold = self._yolo_conf.value()
        s.face_match_threshold = self._face_match.value()
        s.face_det_threshold = self._face_det.value()
        s.alert_cooldown_seconds = self._cooldown.value()
        s.loitering_threshold_seconds = self._loitering.value()
        s.beep_enabled = self._beep.isChecked()
        s.tts_enabled = self._tts.isChecked()
        s.clip_pre_seconds = self._clip_pre.value()
        s.clip_post_seconds = self._clip_post.value()

    @Slot()
    def _on_apply(self) -> None:
        self._gather_into(self._services.settings)
        try:
            self._services.apply_settings()
        except Exception as exc:
            QMessageBox.warning(self, "Не удалось применить", str(exc))
            return
        self._status_label.setText(
            "Сохранено в data/settings.json. Часть параметров применилась мгновенно "
            "(cooldown, loitering, клипы, звук). Пороги детекторов применятся после "
            "переподключения источника."
        )

    @Slot()
    def _on_reset_defaults(self) -> None:
        reply = QMessageBox.question(
            self, "Сброс настроек",
            "Сбросить все параметры к значениям по умолчанию?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        defaults = Settings()
        self._populate_from(defaults)
        self._services.settings = defaults
        self._services.apply_settings()
        self._status_label.setText("Настройки сброшены к значениям по умолчанию и сохранены.")
