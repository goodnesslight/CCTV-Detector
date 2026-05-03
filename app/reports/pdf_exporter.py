import time
from datetime import datetime
from html import escape
from pathlib import Path

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

from app.config import APP_NAME, APP_VERSION
from app.services import Services


def _format_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _build_report_html(services: Services, since_ts: float | None) -> str:
    repo = services.events_repo
    now = time.time()

    total = repo.count(since_ts=since_ts)
    by_kind = repo.count_by_kind(since_ts=since_ts)
    by_zone = repo.count_by_zone(since_ts=since_ts)
    events = repo.query(from_ts=since_ts, limit=1000)

    period_text = (
        f"с {_format_ts(since_ts)} по {_format_ts(now)}"
        if since_ts is not None
        else "за всё время"
    )

    rows_kind = "".join(
        f"<tr><td>{escape(kind)}</td><td style='text-align:right'>{count}</td></tr>"
        for kind, count in by_kind.items()
    ) or "<tr><td colspan='2'><i>нет данных</i></td></tr>"

    rows_zone = "".join(
        f"<tr><td>{escape(zone)}</td><td style='text-align:right'>{count}</td></tr>"
        for zone, count in by_zone.items()
    ) or "<tr><td colspan='2'><i>нет данных</i></td></tr>"

    events_rows = "".join(
        f"<tr>"
        f"<td>{_format_ts(ev.timestamp)}</td>"
        f"<td>{escape(ev.kind)}</td>"
        f"<td>{escape(ev.title)}{(': ' + escape(ev.detail)) if ev.detail else ''}</td>"
        f"<td>{escape(ev.zone_name or '—')}</td>"
        f"<td>{escape(ev.clip_path.name) if ev.clip_path else '—'}</td>"
        f"</tr>"
        for ev in events
    ) or "<tr><td colspan='5'><i>событий нет</i></td></tr>"

    return f"""
<html>
<head><meta charset='utf-8'></head>
<body style='font-family: sans-serif; font-size: 11pt;'>
  <h1 style='color:#222;'>Отчёт системы видеонаблюдения</h1>
  <p style='color:#666;'>
    Программа: <b>{escape(APP_NAME)}</b> v{escape(APP_VERSION)}<br/>
    Сформирован: <b>{_format_ts(now)}</b><br/>
    Период: <b>{escape(period_text)}</b>
  </p>

  <h2>Сводка</h2>
  <p>Всего событий за период: <b>{total}</b></p>

  <h3>По типу события</h3>
  <table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse; min-width:60%;'>
    <thead style='background:#eee;'>
      <tr><th align='left'>Тип</th><th align='right'>Количество</th></tr>
    </thead>
    <tbody>{rows_kind}</tbody>
  </table>

  <h3>По зоне</h3>
  <table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse; min-width:60%;'>
    <thead style='background:#eee;'>
      <tr><th align='left'>Зона</th><th align='right'>Количество</th></tr>
    </thead>
    <tbody>{rows_zone}</tbody>
  </table>

  <h2>Журнал событий <span style='color:#888; font-weight:normal;'>(до 1000 записей)</span></h2>
  <table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse; width:100%; font-size: 10pt;'>
    <thead style='background:#eee;'>
      <tr>
        <th align='left'>Время</th>
        <th align='left'>Тип</th>
        <th align='left'>Описание</th>
        <th align='left'>Зона</th>
        <th align='left'>Клип</th>
      </tr>
    </thead>
    <tbody>{events_rows}</tbody>
  </table>
</body>
</html>
"""


def render_pdf(services: Services, since_ts: float | None, output_path: Path) -> None:
    html = _build_report_html(services, since_ts)
    doc = QTextDocument()
    doc.setHtml(html)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(output_path))
    page_layout = QPageLayout(
        QPageSize(QPageSize.PageSizeId.A4),
        QPageLayout.Orientation.Portrait,
        QMarginsF(15, 15, 15, 15),
        QPageLayout.Unit.Millimeter,
    )
    printer.setPageLayout(page_layout)
    doc.print_(printer)


def export_events_report(
    parent: QWidget,
    services: Services,
    since_ts: float | None,
) -> Path | None:
    default_name = f"argus_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    path, _ = QFileDialog.getSaveFileName(
        parent, "Сохранить PDF-отчёт", default_name, "PDF (*.pdf)",
    )
    if not path:
        return None
    output = Path(path)
    if output.suffix.lower() != ".pdf":
        output = output.with_suffix(".pdf")
    render_pdf(services, since_ts, output)
    QMessageBox.information(
        parent, "Отчёт сохранён",
        f"PDF сохранён:\n{output}",
    )
    return output
