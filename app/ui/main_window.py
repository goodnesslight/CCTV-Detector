from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import QLabel, QMainWindow, QStatusBar, QTabWidget

from app.config import APP_NAME, APP_VERSION
from app.services import Services
from app.ui.tabs.events_tab import EventsTab
from app.ui.tabs.live_tab import LiveTab
from app.ui.tabs.persons_tab import PersonsTab
from app.ui.tabs.settings_tab import SettingsTab
from app.ui.tabs.statistics_tab import StatisticsTab
from app.ui.tabs.video_analysis_tab import VideoAnalysisTab
from app.ui.tabs.zones_tab import ZonesTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1400, 900)

        self._services = Services()

        self._tabs = QTabWidget()
        self._tabs.addTab(LiveTab(self._services), "Live")
        self._tabs.addTab(VideoAnalysisTab(self._services), "Анализ видео")
        self._tabs.addTab(EventsTab(self._services), "События")
        self._tabs.addTab(PersonsTab(self._services), "Персоны")
        self._tabs.addTab(ZonesTab(self._services), "Зоны")
        self._tabs.addTab(StatisticsTab(self._services), "Статистика")
        self._tabs.addTab(SettingsTab(self._services), "Настройки")
        self.setCentralWidget(self._tabs)

        self._build_menu()

        status = QStatusBar()
        status.addPermanentWidget(QLabel("Готов"))
        self.setStatusBar(status)

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&Файл")
        quit_action = QAction("&Выход", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = menubar.addMenu("&Справка")
        about_action = QAction("О программе", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _show_about(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.about(
            self,
            "О программе",
            f"<h3>{APP_NAME}</h3>"
            f"<p>Версия {APP_VERSION}</p>"
            "<p>Дипломный проект: система безопасности помещений на базе "
            "видеонаблюдения и искусственного интеллекта.</p>",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        for i in range(self._tabs.count()):
            widget = self._tabs.widget(i)
            cleanup = getattr(widget, "cleanup", None)
            if callable(cleanup):
                cleanup()
        self._services.shutdown()
        super().closeEvent(event)
