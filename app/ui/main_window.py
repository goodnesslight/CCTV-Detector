from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import QMainWindow, QTabWidget

from app.config import APP_NAME, APP_TITLE, APP_VERSION
from app.services import Services
from app.ui.icon import create_app_icon
from app.ui.tabs.events_tab import EventsTab
from app.ui.tabs.live_tab import LiveTab
from app.ui.tabs.persons_tab import PersonsTab
from app.ui.tabs.settings_tab import SettingsTab
from app.ui.tabs.statistics_tab import StatisticsTab
from app.ui.tabs.zones_tab import ZonesTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(create_app_icon())
        self.resize(1400, 900)

        self._services = Services()

        self._tabs = QTabWidget()
        self._tabs.addTab(LiveTab(self._services), "Пряма трансляція")
        self._tabs.addTab(PersonsTab(self._services), "Персони")
        self._tabs.addTab(ZonesTab(self._services), "Зони")
        self._tabs.addTab(EventsTab(self._services), "Події")
        self._tabs.addTab(StatisticsTab(self._services), "Статистика")
        self._tabs.addTab(SettingsTab(self._services), "Налаштування")
        self.setCentralWidget(self._tabs)

        self._build_menu()

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&Файл")
        quit_action = QAction("&Вихід", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = menubar.addMenu("&Довідка")
        about_action = QAction("Про програму", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _show_about(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.about(
            self,
            "Про програму",
            f"<h3>{APP_TITLE}</h3>"
            f"<p>Версія {APP_VERSION}</p>"
            "<p>Дипломний проект від Майбороди Євгєнія Олександровича з ІК-22</p>",
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        for i in range(self._tabs.count()):
            widget = self._tabs.widget(i)
            cleanup = getattr(widget, "cleanup", None)
            if callable(cleanup):
                cleanup()
        self._services.shutdown()
        super().closeEvent(event)
