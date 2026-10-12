"""Daily exposure & P&L deliverables (CSV + PDF), all numbers computed in SQL."""
from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .db import load_queries

R = load_queries("queries/reports.sql")
NAVY, LIGHT, RED = colors.HexColor("#1F2A44"), colors.HexColor("#F2F4F8"), colors.HexColor("#B3261E")


def _fetch(conn, name: str, **params):
    with conn.cursor() as cur:
        cur.execute(R[name], params)
        cols = [d[0] for d in cur.description]
        return cols, cur.fetchall()


def default_report_date(conn) -> date | None:
    return _fetch(conn, "default_report_date")[1][0][0]


def _write_csv(path: Path, cols, rows) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)


def _num(v, dp=0):
    if v is None:
        return "-"
    v = float(v)
    s = f"{abs(v):,.{dp}f}"
    return f"({s})" if v < 0 else s


def _table(header, rows, widths, right_from=1, pnl_cols=(), bold_last=False):
    data = [header] + rows
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (right_from, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if bold_last and rows:
        style += [("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.5, NAVY)]
    for r, row in enumerate(rows, start=1):
        for c in pnl_cols:
            if isinstance(row[c], str) and row[c].startswith("("):
                style.append(("TEXTCOLOR", (c, r), (c, r), RED))
    t.setStyle(TableStyle(style))
    return t


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.grey)
    canvas.drawString(0.5 * inch, 0.35 * inch, f"Generated {datetime.now():%Y-%m-%d %H:%M}")
    canvas.drawRightString(landscape(letter)[0] - 0.5 * inch, 0.35 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build_reports(conn, report_date: date, out_root: str | Path = "output") -> dict[str, Path]:
    out = Path(out_root) / report_date.isoformat()
    out.mkdir(parents=True, exist_ok=True)

    d_cols, d_rows = _fetch(conn, "exposure_detail", report_date=report_date)
    c_cols, c_rows = _fetch(conn, "exposure_by_commodity", report_date=report_date)
    b_cols, b_rows = _fetch(conn, "exposure_by_book", report_date=report_date)
    s_cols, s_rows = _fetch(conn, "open_defects_summary")
    f_cols, f_rows = _fetch(conn, "open_defects_detail")

    paths = {
        "detail_csv": out / "exposure_pnl_detail.csv",
        "commodity_csv": out / "exposure_by_commodity.csv",
        "book_csv": out / "exposure_by_book.csv",
        "defects_csv": out / "open_defects.csv",
        "pdf": out / "daily_exposure_pnl.pdf",
    }
    _write_csv(paths["detail_csv"], d_cols, d_rows)
    _write_csv(paths["commodity_csv"], c_cols, c_rows)
    _write_csv(paths["book_csv"], b_cols, b_rows)
    _write_csv(paths["defects_csv"], f_cols, f_rows)

    # ---- PDF ----
    styles = getSampleStyleSheet()
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=NAVY, spaceBefore=10, spaceAfter=4, keepWithNext=1)
    doc = SimpleDocTemplate(str(paths["pdf"]), pagesize=landscape(letter), leftMargin=0.5 * inch,
                            rightMargin=0.5 * inch, topMargin=0.5 * inch, bottomMargin=0.6 * inch,
                            title=f"Daily Exposure & P&L {report_date}")
    story = [Paragraph("Daily Commodity Exposure &amp; P&amp;L", styles["Title"]),
             Paragraph(f"Report date: <b>{report_date:%d %b %Y}</b> &nbsp;|&nbsp; Reporting currency: USD "
                       "&nbsp;|&nbsp; Prices: API preferred over CSV", styles["Normal"]), Spacer(1, 8)]

    total = next((r for r in c_rows if r[0] == "TOTAL"), None)
    stale = sum(1 for r in d_rows if r[-1])
    if total:
        kpi = [["Positions", "Net exposure", "Gross exposure", "Daily P&L", "Unrealized P&L", "Stale prices"],
               [str(total[1]), _num(total[3]), _num(total[4]), _num(total[5]), _num(total[6]), str(stale)]]
        t = Table(kpi, colWidths=[1.6 * inch] * 6)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("FONTSIZE", (0, 1), (-1, 1), 13), ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("BACKGROUND", (0, 1), (-1, 1), LIGHT),
            ("TOPPADDING", (0, 1), (-1, 1), 8), ("BOTTOMPADDING", (0, 1), (-1, 1), 8)]))
        story += [t]

    story += [Paragraph("Exposure &amp; P&amp;L by commodity", h2)]
    rows = [[r[0], r[1], _num(r[2], 2), _num(r[3]), _num(r[4]), _num(r[5]), _num(r[6])] for r in c_rows]
    story.append(_table(["Commodity", "Positions", "Net qty", "Net exposure", "Gross exposure", "Daily P&L",
                         "Unrealized P&L"], rows, [1.5 * inch, 0.9 * inch, 1.3 * inch, 1.6 * inch, 1.6 * inch,
                                                  1.5 * inch, 1.6 * inch], pnl_cols=(5, 6), bold_last=True))

    story += [Paragraph("Exposure &amp; P&amp;L by book", h2)]
    rows = [[r[0], r[1], _num(r[2]), _num(r[3]), _num(r[4]), _num(r[5])] for r in b_rows]
    story.append(_table(["Book", "Positions", "Net exposure", "Gross exposure", "Daily P&L", "Unrealized P&L"],
                        rows, [1.8 * inch, 0.9 * inch, 1.7 * inch, 1.7 * inch, 1.6 * inch, 1.7 * inch],
                        pnl_cols=(4, 5), bold_last=True))

    story += [Paragraph("Position detail", h2)]
    rows = [[r[0], r[1], _num(r[4], 2), _num(r[5], 4), str(r[6]) if r[6] else "-", _num(r[7], 4),
             _num(r[9]), _num(r[10]), _num(r[11]) + (" *" if r[12] else "")] for r in d_rows]
    story.append(_table(["Book", "Commodity", "Quantity", "Avg cost", "Price date", "Mkt price", "Exposure",
                         "Unrealized P&L", "Daily P&L"], rows,
                        [1.3 * inch, 1.0 * inch, 1.0 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch, 1.2 * inch,
                         1.3 * inch, 1.2 * inch], right_from=2, pnl_cols=(7, 8)))
    story.append(Paragraph("* price is older than the report date: daily P&amp;L not computed", styles["Italic"]))

    story += [Paragraph("Data quality: open defects", h2)]
    if s_rows:
        rows = [[r[0], r[1], r[2], str(r[3]), str(r[4])] for r in s_rows]
        story.append(_table(["Target", "Source", "Error code", "Records", "Occurrences"], rows,
                            [1.2 * inch, 1.0 * inch, 2.4 * inch, 1.0 * inch, 1.2 * inch], right_from=3))
        story.append(Paragraph("Row-level detail with suggested resolution: open_defects.csv", styles["Italic"]))
    else:
        story.append(Paragraph("No open defects.", styles["Normal"]))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return paths
