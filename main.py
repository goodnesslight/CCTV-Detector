import sys

# Pre-import: цепочка supervision → matplotlib → dateutil → six.moves
# использует ленивый загрузчик `_SixMetaPathImporter`, у которого нет атрибута
# `_path`. Если в этот момент уже загружены PySide6 (хук shibokensupport)
# и torch (monkey-patch на inspect.getfile), они дёргают `inspect.getsource`
# на лениво подгружаемом модуле `_thread` и падают с AttributeError.
# Резолвим цепочку заранее, в "чистом" импорт-контексте.
try:
    import supervision  # noqa: F401
except ImportError:
    pass

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.config import APP_NAME  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
