from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)


def _format_ms(ms: int) -> str:
    if ms < 0:
        ms = 0
    s = ms / 1000.0
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60
    if h:
        return f"{h}:{m:02d}:{sec:05.2f}"
    return f"{m:02d}:{sec:05.2f}"


class ClipPlayer(QWidget):
    def __init__(self, parent: QWidget | None = None, default_loop: bool = True) -> None:
        super().__init__(parent)

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)

        self._video = QVideoWidget(self)
        self._video.setMinimumSize(360, 240)
        self._video.setStyleSheet("background-color: #111;")
        self._video.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._player.setVideoOutput(self._video)

        self._info_label = QLabel("Файл не выбран")
        self._info_label.setStyleSheet("color: #888; padding: 4px;")
        self._info_label.setWordWrap(True)

        self._play_btn = QPushButton("▶ Играть")
        self._play_btn.clicked.connect(self._toggle_play)
        self._play_btn.setEnabled(False)

        self._loop_check = QCheckBox("Повтор")
        self._loop_check.setChecked(default_loop)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.sliderMoved.connect(self._on_slider_moved)
        self._slider.sliderReleased.connect(self._on_slider_released)
        self._user_seeking = False

        self._time_label = QLabel("0:00.00 / 0:00.00")
        self._time_label.setStyleSheet("color: #888; font-family: monospace; padding: 0 6px;")

        self._player.mediaStatusChanged.connect(self._on_status_changed)
        self._player.errorOccurred.connect(self._on_error)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)

        controls = QHBoxLayout()
        controls.addWidget(self._play_btn)
        controls.addWidget(self._slider, 1)
        controls.addWidget(self._time_label)
        controls.addWidget(self._loop_check)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._video, 1)
        layout.addWidget(self._info_label)
        layout.addLayout(controls)

    def load(self, path: Path | None, autoplay: bool = True) -> None:
        if path is None:
            self._player.stop()
            self._player.setSource(QUrl())
            self._info_label.setText("Файл не выбран")
            self._play_btn.setEnabled(False)
            self._play_btn.setText("▶ Играть")
            self._slider.setRange(0, 0)
            self._time_label.setText("0:00.00 / 0:00.00")
            return
        if not path.exists():
            self._player.stop()
            self._info_label.setText(f"Файл не найден: {path}")
            self._play_btn.setEnabled(False)
            return
        self._info_label.setText(f"Файл: {path.name}")
        self._player.setSource(QUrl.fromLocalFile(str(path.resolve())))
        if autoplay:
            self._player.play()
            self._play_btn.setText("⏸ Пауза")
        else:
            self._play_btn.setText("▶ Играть")
        self._play_btn.setEnabled(True)

    def seek_to(self, seconds: float, autoplay: bool = True) -> None:
        ms = max(0, int(seconds * 1000))
        self._player.setPosition(ms)
        if autoplay:
            self._player.play()
            self._play_btn.setText("⏸ Пауза")

    def stop(self) -> None:
        self._player.stop()

    @Slot()
    def _toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self._play_btn.setText("▶ Играть")
        else:
            self._player.play()
            self._play_btn.setText("⏸ Пауза")

    @Slot(int)
    def _on_slider_moved(self, value: int) -> None:
        self._user_seeking = True
        self._time_label.setText(
            f"{_format_ms(value)} / {_format_ms(self._player.duration())}"
        )

    @Slot()
    def _on_slider_released(self) -> None:
        self._player.setPosition(self._slider.value())
        self._user_seeking = False

    @Slot(int)
    def _on_position_changed(self, position: int) -> None:
        if not self._user_seeking:
            self._slider.setValue(position)
        self._time_label.setText(
            f"{_format_ms(position)} / {_format_ms(self._player.duration())}"
        )

    @Slot(int)
    def _on_duration_changed(self, duration: int) -> None:
        self._slider.setRange(0, max(0, duration))
        self._time_label.setText(
            f"{_format_ms(self._player.position())} / {_format_ms(duration)}"
        )

    @Slot(QMediaPlayer.MediaStatus)
    def _on_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self._loop_check.isChecked():
                self._player.setPosition(0)
                self._player.play()
            else:
                self._play_btn.setText("▶ Играть")

    @Slot(QMediaPlayer.Error, str)
    def _on_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        self._info_label.setText(f"Ошибка плеера: {error_string}")
