import time
from datetime import datetime

import pyqtgraph as pg
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.services import Services

PERIOD_HOURS = {
    "Последние 24 часа": 24,
    "7 дней": 24 * 7,
    "30 дней": 24 * 30,
    "Всё время": None,
}


class StatCard(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { background: #1a1a1a; border-radius: 6px; padding: 8px; }"
        )
        self._title = QLabel(title)
        self._title.setStyleSheet("color: #888; font-size: 12px;")
        self._value = QLabel("—")
        self._value.setStyleSheet("color: #4ade80; font-size: 24px; font-weight: bold;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.addWidget(self._title)
        layout.addWidget(self._value)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, text: str) -> None:
        self._value.setText(text)


class StatisticsTab(QWidget):
    def __init__(self, services: Services) -> None:
        super().__init__()
        self._services = services

        pg.setConfigOptions(antialias=True, background="#111", foreground="#aaa")

        self._period_combo = QComboBox()
        for label in PERIOD_HOURS:
            self._period_combo.addItem(label, PERIOD_HOURS[label])
        self._period_combo.setCurrentIndex(0)
        self._period_combo.currentIndexChanged.connect(self._refresh)

        self._refresh_btn = QPushButton("Обновить")
        self._refresh_btn.clicked.connect(self._refresh)

        self._export_btn = QPushButton("📄 Экспорт в PDF")
        self._export_btn.clicked.connect(self._on_export_pdf)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Период:"))
        toolbar.addWidget(self._period_combo)
        toolbar.addWidget(self._refresh_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(self._export_btn)

        self._card_total = StatCard("Всего событий за период")
        self._card_today = StatCard("За последний час")
        self._card_top_kind = StatCard("Самый частый тип")
        self._card_top_zone = StatCard("Самая активная зона")

        cards = QGridLayout()
        cards.addWidget(self._card_total, 0, 0)
        cards.addWidget(self._card_today, 0, 1)
        cards.addWidget(self._card_top_kind, 0, 2)
        cards.addWidget(self._card_top_zone, 0, 3)

        self._timeline_plot = pg.PlotWidget(title="События по часам")
        self._timeline_plot.showGrid(x=True, y=True, alpha=0.2)
        self._timeline_plot.getAxis("bottom").setStyle(tickFont=pg.QtGui.QFont("monospace", 8))
        self._timeline_plot.setLabel("left", "Событий")
        self._timeline_plot.setMinimumHeight(180)

        self._kind_plot = pg.PlotWidget(title="По типу события")
        self._kind_plot.showGrid(y=True, alpha=0.2)
        self._kind_plot.setLabel("left", "Событий")

        self._zone_plot = pg.PlotWidget(title="По зоне")
        self._zone_plot.showGrid(y=True, alpha=0.2)
        self._zone_plot.setLabel("left", "Событий")

        bottom_charts = QHBoxLayout()
        bottom_charts.addWidget(self._kind_plot, 1)
        bottom_charts.addWidget(self._zone_plot, 1)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888; padding: 4px;")
        self._status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addLayout(cards)
        layout.addWidget(self._timeline_plot, 2)
        layout.addLayout(bottom_charts, 3)
        layout.addWidget(self._status_label)

        self._services.alerts.alert_fired.connect(self._on_new_event)
        self._refresh()

    def _period_from_ts(self) -> float | None:
        hours = self._period_combo.currentData()
        if hours is None:
            return None
        return time.time() - hours * 3600

    @Slot()
    def _refresh(self) -> None:
        repo = self._services.events_repo
        from_ts = self._period_from_ts()
        now = time.time()

        total = repo.count(since_ts=from_ts)
        last_hour = repo.count(since_ts=now - 3600)
        by_kind = repo.count_by_kind(since_ts=from_ts)
        by_zone = repo.count_by_zone(since_ts=from_ts)

        self._card_total.set_value(str(total))
        self._card_today.set_value(str(last_hour))
        if by_kind:
            top_kind = next(iter(by_kind))
            self._card_top_kind.set_value(f"{top_kind}\n({by_kind[top_kind]})")
        else:
            self._card_top_kind.set_value("—")
        if by_zone:
            top_zone = next(iter(by_zone))
            self._card_top_zone.set_value(f"{top_zone}\n({by_zone[top_zone]})")
        else:
            self._card_top_zone.set_value("—")

        self._draw_timeline(from_ts or (now - 24 * 3600), now)
        self._draw_bar(self._kind_plot, by_kind, color="#4ade80")
        self._draw_bar(self._zone_plot, by_zone, color="#60a5fa")

        period_label = self._period_combo.currentText()
        self._status_label.setText(
            f"Период: {period_label}. Всего: {total}. По типам: {len(by_kind)}. По зонам: {len(by_zone)}."
        )

    def _draw_timeline(self, from_ts: float, until_ts: float) -> None:
        repo = self._services.events_repo
        rows = repo.count_by_hour(from_ts, until_ts)
        plot = self._timeline_plot
        plot.clear()
        if not rows:
            return

        ts_arr = [t for t, _ in rows]
        cnt_arr = [c for _, c in rows]

        bar = pg.BarGraphItem(
            x=ts_arr, height=cnt_arr, width=2400, brush=QColor("#4ade80"),
        )
        plot.addItem(bar)

        ax = plot.getAxis("bottom")
        step = max(1, len(ts_arr) // 8)
        ticks = [
            (ts_arr[i], datetime.fromtimestamp(ts_arr[i]).strftime("%m-%d %H:%M"))
            for i in range(0, len(ts_arr), step)
        ]
        ax.setTicks([ticks])

    def _draw_bar(self, plot: pg.PlotWidget, data: dict[str, int], color: str) -> None:
        plot.clear()
        if not data:
            return
        items = list(data.items())
        x = list(range(len(items)))
        heights = [v for _, v in items]
        bar = pg.BarGraphItem(x=x, height=heights, width=0.7, brush=QColor(color))
        plot.addItem(bar)
        ax = plot.getAxis("bottom")
        ticks = [(i, name[:16]) for i, (name, _) in enumerate(items)]
        ax.setTicks([ticks])
        plot.setXRange(-0.5, len(items) - 0.5)

    @Slot(object)
    def _on_new_event(self, _ev) -> None:
        self._refresh()

    @Slot()
    def _on_export_pdf(self) -> None:
        from app.reports.pdf_exporter import export_events_report

        try:
            export_events_report(self, self._services, self._period_from_ts())
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Ошибка экспорта", str(exc))
