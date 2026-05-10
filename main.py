import sys

# Pre-import: ланцюг supervision → matplotlib → dateutil → six.moves
# використовує ледачий завантажувач `_SixMetaPathImporter`, у якого немає
# атрибута `_path`. Якщо в цей момент уже завантажені PySide6 (хук
# shibokensupport) і torch (monkey-patch на inspect.getfile), вони
# смикають `inspect.getsource` на ліниво підвантажуваному модулі `_thread`
# і падають з AttributeError. Резолвимо ланцюг заздалегідь, у "чистому"
# імпорт-контексті.
try:
    import supervision  # noqa: F401
except ImportError:
    pass

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import APP_NAME  # noqa: E402
from app.ui.icon import create_app_icon  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402


def _set_windows_app_user_model_id(app_id: str) -> None:
    """Без цього Windows групує вікно під python.exe у тасктрей
    і показує його іконку, а не нашу."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError):
        pass


def main() -> int:
    _set_windows_app_user_model_id("VideoSecuritySystem.Diploma.0.1")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(create_app_icon())

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
