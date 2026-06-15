#!/usr/bin/env python3
import csv
import datetime as dt
import html
import json
import statistics
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
QUARTERLY = ROOT / "quarterly_metrics.csv"
MONTHLY = ROOT / "monthly_metrics.csv"
ISSUES = ROOT / "issues_inventory.csv"
OUT = ROOT / "index.html"
SAMPLES = ROOT / "samples"
REPORT_START = dt.datetime(2021, 6, 11, tzinfo=dt.timezone.utc)
REPORT_END = dt.datetime(2026, 6, 12, tzinfo=dt.timezone.utc)

PERIOD_ORDER = ["growth", "plateau", "decline"]
PERIOD_LABELS = {
    "growth": "Growth",
    "plateau": "Plateau",
    "decline": "Decline",
}
PERIOD_COLORS = {
    "growth": "#dbeafe",
    "plateau": "#fef3c7",
    "decline": "#fee2e2",
}
LINE_COLORS = {
    "open": "#0f766e",
    "created": "#2563eb",
    "closed": "#dc2626",
    "creator": "#7c3aed",
    "first": "#ea580c",
}
VIEW_CONFIGS = [
    {
        "key": "all",
        "button": "All issues",
        "title": "All Gutenberg issues",
        "subject": "issues",
        "note": "All WordPress/gutenberg issues in the five-year inventory, excluding pull requests.",
    },
    {
        "key": "bugs",
        "button": "Bugs",
        "title": "Bug-labeled Gutenberg issues",
        "subject": "bug reports",
        "note": 'Issues with the current GitHub label "[Type] Bug". Labels are current API fields, not historical labels at creation time.',
    },
    {
        "key": "feature_requests",
        "button": "Feature requests",
        "title": "Feature-request Gutenberg issues",
        "subject": "feature requests",
        "note": 'Issues with the current GitHub label "[Type] Enhancement", used here as Gutenberg\'s feature-request time-series view.',
    },
]
TIMELINE_EVENTS = [
    {"date": dt.datetime(2018, 12, 6, tzinfo=dt.timezone.utc), "label": "Gutenberg (5.0)"},
    {"date": dt.datetime(2022, 1, 25, tzinfo=dt.timezone.utc), "label": "FSE (5.9)"},
    {"date": dt.datetime(2024, 9, 17, tzinfo=dt.timezone.utc), "label": "WCUS 2024"},
    {"date": dt.datetime(2025, 1, 9, tzinfo=dt.timezone.utc), "label": "contribution reduction"},
    {"date": dt.datetime(2025, 5, 29, tzinfo=dt.timezone.utc), "label": "contribution resumption"},
]


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_datetime(value):
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_period_start(value):
    return dt.datetime.fromisoformat(value + "T00:00:00+00:00")


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month)


def i(row, key):
    return int(row[key])


def f1(value):
    return f"{value:.1f}"


def pct(value, total):
    return 100 * value / total if total else 0


def fmt_int(value):
    return f"{int(round(value)):,}"


def esc(value):
    return html.escape(str(value))


def labels(row):
    return {part.strip().lower() for part in (row.get("labels") or "").split("|") if part.strip()}


def matches_view(row, view_key):
    if view_key == "all":
        return True
    row_labels = labels(row)
    if view_key == "bugs":
        return "[type] bug" in row_labels
    if view_key == "feature_requests":
        return "[type] enhancement" in row_labels
    return False


def enrich_issues(rows):
    enriched = []
    for row in rows:
        copy = dict(row)
        copy["_created"] = parse_datetime(row["created_at"])
        copy["_closed"] = parse_datetime(row.get("closed_at") or "")
        enriched.append(copy)
    return enriched


def issue_metrics_for_period(issues, view_key, start, end):
    matched = [row for row in issues if matches_view(row, view_key)]
    created_rows = [row for row in matched if start <= row["_created"] < end]
    closed_rows = [row for row in matched if row["_closed"] and start <= row["_closed"] < end]
    open_at_end = [
        row
        for row in matched
        if row["_created"] < end and (not row["_closed"] or row["_closed"] >= end)
    ]
    first_seen = {}
    for row in matched:
        author = row.get("author_login") or ""
        if not author:
            continue
        if author not in first_seen or row["_created"] < first_seen[author]:
            first_seen[author] = row["_created"]
    creators = {row.get("author_login") or "" for row in created_rows if row.get("author_login")}
    first_time = {
        author
        for author in creators
        if start <= first_seen.get(author, REPORT_END) < end
    }
    old_closed = [
        row for row in closed_rows
        if row["_closed"] and (row["_closed"] - row["_created"]).days >= 365
    ]
    return {
        "open_at_end": len(open_at_end),
        "created": len(created_rows),
        "closed": len(closed_rows),
        "unique_creators": len(creators),
        "first_time_creators": len(first_time),
        "old_closed_365d": len(old_closed),
    }


def build_filtered_quarters(base_rows, issues, view_key):
    rows = []
    for base in base_rows:
        start = max(parse_period_start(base["quarter"]), REPORT_START)
        end = min(add_months(parse_period_start(base["quarter"]), 3), REPORT_END)
        metrics = issue_metrics_for_period(issues, view_key, start, end)
        rows.append({
            "quarter": base["quarter"],
            "period": base["period"],
            "open_at_end": str(metrics["open_at_end"]),
            "created": str(metrics["created"]),
            "closed": str(metrics["closed"]),
            "net_created_minus_closed": str(metrics["created"] - metrics["closed"]),
            "unique_creators": str(metrics["unique_creators"]),
            "first_time_creators": str(metrics["first_time_creators"]),
            "old_closed_365d": str(metrics["old_closed_365d"]),
        })
    return rows


def build_filtered_months(base_rows, issues, view_key):
    rows = []
    for base in base_rows:
        start = max(parse_period_start(base["month"]), REPORT_START)
        end = min(add_months(parse_period_start(base["month"]), 1), REPORT_END)
        metrics = issue_metrics_for_period(issues, view_key, start, end)
        rows.append({
            "month": base["month"],
            "period": base["period"],
            "open_at_end": str(metrics["open_at_end"]),
            "created": str(metrics["created"]),
            "closed": str(metrics["closed"]),
            "net": str(metrics["created"] - metrics["closed"]),
            "unique_creators": str(metrics["unique_creators"]),
        })
    return rows


def code_counts(path):
    counts = Counter()
    rows = read_csv(path)
    for row in rows:
        for code in (row.get("codes") or "").replace(";", "|").split("|"):
            code = code.strip()
            if code:
                counts[code] += 1
    return counts, len(rows)


def full_quarter_rows(rows):
    return [r for r in rows if r["quarter"] not in {"2021-04-01", "2026-04-01"}]


def summarize_periods(rows):
    full = full_quarter_rows(rows)
    summary = {}
    for period in PERIOD_ORDER:
        rs = [r for r in full if r["period"] == period]
        summary[period] = {
            "quarters": len(rs),
            "created": statistics.mean(i(r, "created") for r in rs),
            "closed": statistics.mean(i(r, "closed") for r in rs),
            "net": statistics.mean(i(r, "net_created_minus_closed") for r in rs),
            "unique": statistics.mean(i(r, "unique_creators") for r in rs),
            "first": statistics.mean(i(r, "first_time_creators") for r in rs),
            "old_closed": statistics.mean(i(r, "old_closed_365d") for r in rs),
            "start_open": i(rs[0], "open_at_end"),
            "end_open": i(rs[-1], "open_at_end"),
        }
    return summary


def scale(value, old_min, old_max, new_min, new_max):
    if old_max == old_min:
        return (new_min + new_max) / 2
    return new_min + (value - old_min) * (new_max - new_min) / (old_max - old_min)


def x_for_date(rows, event_date, left, plot_w, date_key):
    start = parse_period_start(rows[0][date_key])
    end = parse_period_start(rows[-1][date_key])
    if end <= start:
        return left + plot_w / 2
    clamped = min(max(event_date, start), end)
    ratio = (clamped - start).total_seconds() / (end - start).total_seconds()
    return left + ratio * plot_w


def timeline_event_markers(rows, left, top, plot_w, plot_h, label_ys, date_key="quarter", include_out_of_range=True):
    parts = []
    start = parse_period_start(rows[0][date_key])
    end = parse_period_start(rows[-1][date_key])
    items = []
    for idx, event in enumerate(TIMELINE_EVENTS):
        if not include_out_of_range and not (start <= event["date"] <= end):
            continue
        x = x_for_date(rows, event["date"], left, plot_w, date_key)
        label = event["label"]
        label_w = min(172, max(78, len(label) * 7 + 18))
        items.append(
            {
                "date": event["date"],
                "label": label,
                "x": x,
                "label_w": label_w,
                "label_left": min(max(x - label_w / 2, left), left + plot_w - label_w),
            }
        )

    gap = 6
    cursor = left
    for item in items:
        item["label_left"] = max(item["label_left"], cursor)
        cursor = item["label_left"] + item["label_w"] + gap
    cursor = left + plot_w
    for item in reversed(items):
        if item["label_left"] + item["label_w"] > cursor:
            item["label_left"] = cursor - item["label_w"]
        cursor = item["label_left"] - gap
    cursor = left
    for item in items:
        item["label_left"] = max(item["label_left"], cursor)
        cursor = item["label_left"] + item["label_w"] + gap

    label_y = label_ys[1] if len(label_ys) > 1 else label_ys[0]
    label_h = 22
    label_top = label_y - 15
    label_bottom = label_top + label_h
    for item in items:
        x = item["x"]
        label = item["label"]
        label_w = item["label_w"]
        label_left = item["label_left"]
        label_center = label_left + label_w / 2
        parts.append('<g class="event-marker">')
        parts.append(f'<title>{item["date"].date().isoformat()} {esc(label)}</title>')
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" class="event-line"/>')
        parts.append(f'<line x1="{label_center:.1f}" y1="{label_bottom:.1f}" x2="{x:.1f}" y2="{top:.1f}" class="event-connector"/>')
        parts.append(f'<circle cx="{x:.1f}" cy="{top:.1f}" r="3.2" class="event-dot"/>')
        parts.append(
            f'<rect x="{label_left:.1f}" y="{label_top:.1f}" '
            f'width="{label_w:.1f}" height="{label_h}" rx="4" class="event-label-bg"/>'
        )
        parts.append(f'<text x="{label_center:.1f}" y="{label_y:.1f}" text-anchor="middle" class="event-label">{esc(label)}</text>')
        parts.append("</g>")
    return parts


def axis_ticks(min_value, max_value, steps=5):
    span = max_value - min_value
    if span <= 0:
        return [min_value]
    raw = span / steps
    magnitude = 10 ** (len(str(int(raw))) - 1) if raw >= 1 else 1
    candidates = [1, 2, 5, 10]
    step = min((c * magnitude for c in candidates), key=lambda x: abs(x - raw))
    start = int(min_value // step * step)
    end = int(((max_value + step - 1) // step) * step)
    ticks = []
    current = start
    while current <= end:
        ticks.append(current)
        current += step
    return ticks


def open_timeline_svg(rows):
    width, height = 1120, 390
    left, right, top, bottom = 74, 34, 122, 58
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [i(r, "open_at_end") for r in rows]
    min_v = max(0, (min(values) // 500) * 500)
    max_v = ((max(values) + 499) // 500) * 500

    def x_for(idx):
        return left + idx * plot_w / (len(rows) - 1)

    def y_for(value):
        return scale(value, min_v, max_v, top + plot_h, top)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Open issue timeline">',
        f'<text x="{left}" y="24" class="chart-title">Open issues over time</text>',
        f'<text x="{left}" y="42" class="chart-note">Backlog grew through 2024, peaked, then declined after early 2025.</text>',
    ]

    # Phase bands.
    start_idx = 0
    for idx, row in enumerate(rows + [{"period": None}]):
        if idx == len(rows) or row["period"] != rows[start_idx]["period"]:
            period = rows[start_idx]["period"]
            x1 = x_for(start_idx) - (plot_w / (len(rows) - 1)) / 2
            x2 = x_for(idx - 1) + (plot_w / (len(rows) - 1)) / 2
            x1 = max(left, x1)
            x2 = min(left + plot_w, x2)
            parts.append(f'<rect x="{x1:.1f}" y="{top}" width="{x2 - x1:.1f}" height="{plot_h}" fill="{PERIOD_COLORS[period]}" opacity="0.55"/>')
            parts.append(f'<text x="{(x1 + x2) / 2:.1f}" y="{top + plot_h - 16}" text-anchor="middle" class="phase-label">{PERIOD_LABELS[period]}</text>')
            start_idx = idx

    for tick in axis_ticks(min_v, max_v, 4):
        y = y_for(tick)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" class="axis">{tick:,}</text>')

    parts.extend(timeline_event_markers(rows, left, top, plot_w, plot_h, [64, 84, 104]))

    points = " ".join(f'{x_for(idx):.1f},{y_for(value):.1f}' for idx, value in enumerate(values))
    parts.append(f'<polyline points="{points}" fill="none" stroke="{LINE_COLORS["open"]}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
    for idx, row in enumerate(rows):
        x = x_for(idx)
        y = y_for(i(row, "open_at_end"))
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{LINE_COLORS["open"]}"><title>{esc(row["quarter"])}: {i(row, "open_at_end"):,}</title></circle>')
        if idx == 0 or row["quarter"][5:10] == "01-01":
            parts.append(f'<text x="{x:.1f}" y="{height - 26}" text-anchor="middle" class="axis">{esc(row["quarter"][:4])}</text>')

    peak_idx = max(range(len(rows)), key=lambda idx: values[idx])
    peak_x = x_for(peak_idx)
    peak_y = y_for(values[peak_idx])
    latest_x = x_for(len(rows) - 1)
    latest_y = y_for(values[-1])
    parts.append(f'<text x="{peak_x:.1f}" y="{peak_y - 14:.1f}" text-anchor="middle" class="callout-text">Peak {values[peak_idx]:,}</text>')
    parts.append(f'<text x="{latest_x - 8:.1f}" y="{latest_y - 12:.1f}" text-anchor="end" class="callout-text">Latest {values[-1]:,}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def flow_svg(rows):
    width, height = 1120, 390
    left, right, top, bottom = 70, 34, 122, 56
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_v = max(max(i(r, "created"), i(r, "closed")) for r in rows) + 120

    def y_for(value):
        return scale(value, 0, max_v, top + plot_h, top)

    def x_for(idx):
        return left + idx * plot_w / (len(rows) - 1)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Created and closed issues per quarter">',
        f'<text x="{left}" y="24" class="chart-title">New and closed issues by quarter</text>',
        f'<text x="{left}" y="42" class="chart-note">Blue is newly opened issues. Red is closed issues. The gap narrows in 2024 and flips after early 2025.</text>',
    ]
    for tick in axis_ticks(0, max_v, 4):
        y = y_for(tick)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" class="axis">{tick:,}</text>')

    parts.extend(timeline_event_markers(rows, left, top, plot_w, plot_h, [64, 84, 104]))

    created_points = " ".join(
        f'{x_for(idx):.1f},{y_for(i(row, "created")):.1f}'
        for idx, row in enumerate(rows)
    )
    closed_points = " ".join(
        f'{x_for(idx):.1f},{y_for(i(row, "closed")):.1f}'
        for idx, row in enumerate(rows)
    )
    parts.append(f'<polyline points="{created_points}" fill="none" stroke="{LINE_COLORS["created"]}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
    parts.append(f'<polyline points="{closed_points}" fill="none" stroke="{LINE_COLORS["closed"]}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')

    for idx, row in enumerate(rows):
        x = x_for(idx)
        created = i(row, "created")
        closed = i(row, "closed")
        parts.append(f'<circle cx="{x:.1f}" cy="{y_for(created):.1f}" r="4" fill="{LINE_COLORS["created"]}"><title>{esc(row["quarter"])} new issues: {created:,}</title></circle>')
        parts.append(f'<circle cx="{x:.1f}" cy="{y_for(closed):.1f}" r="4" fill="{LINE_COLORS["closed"]}"><title>{esc(row["quarter"])} closed issues: {closed:,}</title></circle>')
        if idx == 0 or row["quarter"][5:10] == "01-01":
            parts.append(f'<text x="{x:.1f}" y="{height - 24}" text-anchor="middle" class="axis">{esc(row["quarter"][:4])}</text>')
    parts.append(f'<rect x="{left + plot_w - 230}" y="12" width="12" height="12" fill="{LINE_COLORS["created"]}"/><text x="{left + plot_w - 212}" y="23" class="legend-text">Created</text>')
    parts.append(f'<rect x="{left + plot_w - 140}" y="12" width="12" height="12" fill="{LINE_COLORS["closed"]}"/><text x="{left + plot_w - 122}" y="23" class="legend-text">Closed</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def net_monthly_svg(months):
    recent = [r for r in months if r["month"] >= "2024-09-01"]
    width, height = 1120, 310
    left, right, top, bottom = 68, 32, 122, 52
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [i(r, "net") for r in recent]
    max_abs = max(abs(v) for v in values) + 40
    group_w = plot_w / len(recent)
    bar_w = group_w * 0.62

    def y_for(value):
        return scale(value, -max_abs, max_abs, top + plot_h, top)

    zero = y_for(0)
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Monthly net issue flow">',
        f'<text x="{left}" y="24" class="chart-title">Monthly net flow around the turn</text>',
        f'<text x="{left}" y="42" class="chart-note">Bars below zero mean closures exceeded new issues. Late 2025 and June 2026 show cleanup pulses.</text>',
        f'<line x1="{left}" y1="{zero:.1f}" x2="{left + plot_w}" y2="{zero:.1f}" stroke="#334155" stroke-width="1.2"/>',
    ]
    parts.extend(timeline_event_markers(recent, left, top, plot_w, plot_h, [64, 84, 104], date_key="month", include_out_of_range=False))
    for idx, row in enumerate(recent):
        value = i(row, "net")
        x = left + idx * group_w + (group_w - bar_w) / 2
        y = y_for(max(value, 0))
        h = abs(y_for(value) - zero)
        color = "#2563eb" if value >= 0 else "#dc2626"
        parts.append(f'<rect x="{x:.1f}" y="{min(y_for(value), zero):.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{color}" rx="2"><title>{esc(row["month"])} net: {value:+,}</title></rect>')
        if idx == 0 or row["month"][5:7] == "01":
            parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{height - 24}" text-anchor="middle" class="axis">{esc(row["month"][:4])}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def period_metric_svg(summary):
    width, height = 1120, 330
    left, top = 42, 62
    card_w = 336
    gap = 24
    max_created = max(summary[p]["created"] for p in PERIOD_ORDER)
    max_closed = max(summary[p]["closed"] for p in PERIOD_ORDER)
    max_bar = max(max_created, max_closed)
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Period summary cards">',
        '<text x="42" y="28" class="chart-title">Three phases in one view</text>',
        '<text x="42" y="48" class="chart-note">Growth and plateau had more new issues than closures. Decline reverses that relationship.</text>',
    ]
    for idx, period in enumerate(PERIOD_ORDER):
        x = left + idx * (card_w + gap)
        data = summary[period]
        fill = PERIOD_COLORS[period]
        parts.append(f'<rect x="{x}" y="{top}" width="{card_w}" height="230" rx="8" fill="{fill}" stroke="#cbd5e1"/>')
        parts.append(f'<text x="{x + 18}" y="{top + 32}" class="phase-card-title">{PERIOD_LABELS[period]}</text>')
        parts.append(f'<text x="{x + 18}" y="{top + 58}" class="phase-card-note">{data["quarters"]} full quarters</text>')
        created_w = scale(data["created"], 0, max_bar, 0, 180)
        closed_w = scale(data["closed"], 0, max_bar, 0, 180)
        parts.append(f'<text x="{x + 18}" y="{top + 92}" class="metric-label">created / q</text>')
        parts.append(f'<rect x="{x + 122}" y="{top + 78}" width="{created_w:.1f}" height="18" fill="{LINE_COLORS["created"]}" rx="3"/>')
        parts.append(f'<text x="{x + 312}" y="{top + 92}" text-anchor="end" class="metric-num">{f1(data["created"])}</text>')
        parts.append(f'<text x="{x + 18}" y="{top + 122}" class="metric-label">closed / q</text>')
        parts.append(f'<rect x="{x + 122}" y="{top + 108}" width="{closed_w:.1f}" height="18" fill="{LINE_COLORS["closed"]}" rx="3"/>')
        parts.append(f'<text x="{x + 312}" y="{top + 122}" text-anchor="end" class="metric-num">{f1(data["closed"])}</text>')
        net = data["net"]
        net_color = "#16a34a" if net < 0 else "#dc2626"
        verb = "shrinks" if net < 0 else "adds"
        parts.append(f'<text x="{x + 18}" y="{top + 168}" class="phase-card-title" fill="{net_color}">{verb} {abs(net):.1f} / q</text>')
        parts.append(f'<text x="{x + 18}" y="{top + 197}" class="phase-card-note">avg unique creators: {f1(data["unique"])}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def creators_svg(summary):
    width, height = 760, 290
    left, right, top, bottom = 70, 24, 44, 54
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_v = max(summary[p]["unique"] for p in PERIOD_ORDER) + 35
    group_w = plot_w / len(PERIOD_ORDER)
    bar_w = 54

    def y_for(value):
        return scale(value, 0, max_v, top + plot_h, top)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Creator trend">',
        f'<text x="{left}" y="24" class="chart-title">Fewer people are opening issues on GitHub</text>',
    ]
    for tick in axis_ticks(0, max_v, 4):
        y = y_for(tick)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" class="axis">{tick:,}</text>')
    for idx, period in enumerate(PERIOD_ORDER):
        x = left + idx * group_w + group_w / 2
        unique = summary[period]["unique"]
        first = summary[period]["first"]
        uy = y_for(unique)
        fy = y_for(first)
        parts.append(f'<rect x="{x - bar_w - 5:.1f}" y="{uy:.1f}" width="{bar_w}" height="{top + plot_h - uy:.1f}" fill="{LINE_COLORS["creator"]}" rx="5"/>')
        parts.append(f'<rect x="{x + 5:.1f}" y="{fy:.1f}" width="{bar_w}" height="{top + plot_h - fy:.1f}" fill="{LINE_COLORS["first"]}" rx="5"/>')
        parts.append(f'<text x="{x - 32:.1f}" y="{uy - 8:.1f}" text-anchor="middle" class="metric-num">{f1(unique)}</text>')
        parts.append(f'<text x="{x + 32:.1f}" y="{fy - 8:.1f}" text-anchor="middle" class="metric-num">{f1(first)}</text>')
        parts.append(f'<text x="{x:.1f}" y="{height - 24}" text-anchor="middle" class="axis">{PERIOD_LABELS[period]}</text>')
    parts.append(f'<rect x="{left}" y="{height - 12}" width="11" height="11" fill="{LINE_COLORS["creator"]}"/><text x="{left + 17}" y="{height - 3}" class="legend-text">unique creators / q</text>')
    parts.append(f'<rect x="{left + 180}" y="{height - 12}" width="11" height="11" fill="{LINE_COLORS["first"]}"/><text x="{left + 197}" y="{height - 3}" class="legend-text">first-time creators / q</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def first_time_reporters_svg(rows):
    width, height = 1120, 300
    left, right, top, bottom = 70, 34, 46, 56
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [i(r, "first_time_creators") for r in rows]
    max_v = max(values) + 25
    group_w = plot_w / len(rows)
    bar_w = group_w * 0.58

    def y_for(value):
        return scale(value, 0, max_v, top + plot_h, top)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="First-time issue reporters per quarter">',
        f'<text x="{left}" y="24" class="chart-title">First-time issue reporters by quarter</text>',
        f'<text x="{left}" y="42" class="chart-note">The top of the reporting funnel got smaller after early 2025.</text>',
    ]
    for tick in axis_ticks(0, max_v, 4):
        y = y_for(tick)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" class="axis">{tick:,}</text>')
    for idx, row in enumerate(rows):
        value = i(row, "first_time_creators")
        x = left + idx * group_w + (group_w - bar_w) / 2
        y = y_for(value)
        fill = "#ea580c" if row["period"] == "decline" else "#7c3aed"
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{top + plot_h - y:.1f}" fill="{fill}" rx="3"><title>{esc(row["quarter"])} first-time reporters: {value:,}</title></rect>')
        if idx == 0 or row["quarter"][5:10] == "01-01":
            parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{height - 24}" text-anchor="middle" class="axis">{esc(row["quarter"][:4])}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def reporter_trend_svg(rows):
    width, height = 1120, 390
    left, right, top, bottom = 74, 34, 122, 58
    plot_w = width - left - right
    plot_h = height - top - bottom
    unique_values = [i(r, "unique_creators") for r in rows]
    first_values = [i(r, "first_time_creators") for r in rows]
    max_v = max(unique_values) + 40

    def x_for(idx):
        return left + idx * plot_w / (len(rows) - 1)

    def y_for(value):
        return scale(value, 0, max_v, top + plot_h, top)

    def points(values):
        return " ".join(
            f"{x_for(idx):.1f},{y_for(value):.1f}"
            for idx, value in enumerate(values)
        )

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="People opening issues on GitHub">',
        f'<text x="{left}" y="24" class="chart-title">Fewer people are opening issues on GitHub</text>',
        f'<text x="{left}" y="42" class="chart-note">Purple is unique issue creators. Orange is first-time issue creators. Both shrink after early 2025.</text>',
    ]

    start_idx = 0
    for idx, row in enumerate(rows + [{"period": None}]):
        if idx == len(rows) or row["period"] != rows[start_idx]["period"]:
            period = rows[start_idx]["period"]
            x1 = x_for(start_idx) - (plot_w / (len(rows) - 1)) / 2
            x2 = x_for(idx - 1) + (plot_w / (len(rows) - 1)) / 2
            x1 = max(left, x1)
            x2 = min(left + plot_w, x2)
            parts.append(f'<rect x="{x1:.1f}" y="{top}" width="{x2 - x1:.1f}" height="{plot_h}" fill="{PERIOD_COLORS[period]}" opacity="0.42"/>')
            start_idx = idx

    for tick in axis_ticks(0, max_v, 4):
        y = y_for(tick)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" class="axis">{tick:,}</text>')

    parts.extend(timeline_event_markers(rows, left, top, plot_w, plot_h, [64, 84, 104]))

    parts.append(f'<polyline points="{points(unique_values)}" fill="none" stroke="{LINE_COLORS["creator"]}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')
    parts.append(f'<polyline points="{points(first_values)}" fill="none" stroke="{LINE_COLORS["first"]}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>')

    for idx, row in enumerate(rows):
        x = x_for(idx)
        unique = i(row, "unique_creators")
        first = i(row, "first_time_creators")
        parts.append(f'<circle cx="{x:.1f}" cy="{y_for(unique):.1f}" r="4.2" fill="{LINE_COLORS["creator"]}"><title>{esc(row["quarter"])} unique creators: {unique:,}</title></circle>')
        parts.append(f'<circle cx="{x:.1f}" cy="{y_for(first):.1f}" r="4.2" fill="{LINE_COLORS["first"]}"><title>{esc(row["quarter"])} first-time creators: {first:,}</title></circle>')
        if idx == 0 or row["quarter"][5:10] == "01-01":
            parts.append(f'<text x="{x:.1f}" y="{height - 24}" text-anchor="middle" class="axis">{esc(row["quarter"][:4])}</text>')

    parts.append(f'<rect x="{left + plot_w - 310}" y="12" width="12" height="12" fill="{LINE_COLORS["creator"]}"/><text x="{left + plot_w - 292}" y="23" class="legend-text">Unique creators</text>')
    parts.append(f'<rect x="{left + plot_w - 170}" y="12" width="12" height="12" fill="{LINE_COLORS["first"]}"/><text x="{left + plot_w - 152}" y="23" class="legend-text">First-time creators</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def closure_codes_svg(old_counts, recent_counts):
    codes = [
        ("FIXED_BY_CHANGE", "Fixed by change"),
        ("CLOSED_WITHOUT_RESOLUTION", "Closed w/o resolution"),
        ("SCOPE_OR_OWNERSHIP_SHIFT", "Scope shift"),
        ("LOWER_PROBLEM_LOAD_SIGNAL", "Not active bug"),
        ("DUPLICATE_OR_CONSOLIDATED", "Duplicate/consolidated"),
    ]
    width, height = 760, 360
    left, right, top, bottom = 178, 28, 44, 34
    plot_w = width - left - right
    row_h = 48
    max_v = 45
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Decline closure sample composition">',
        f'<text x="{left}" y="24" class="chart-title">Decline closures: old backlog vs recent issues</text>',
    ]
    for idx, (code, label) in enumerate(codes):
        y = top + idx * row_h
        old = old_counts.get(code, 0)
        recent = recent_counts.get(code, 0)
        old_w = scale(old, 0, max_v, 0, plot_w - 110)
        recent_w = scale(recent, 0, max_v, 0, plot_w - 110)
        parts.append(f'<text x="{left - 12}" y="{y + 25}" text-anchor="end" class="axis strong">{esc(label)}</text>')
        parts.append(f'<rect x="{left}" y="{y + 6}" width="{old_w:.1f}" height="13" fill="#0f766e" rx="2"/>')
        parts.append(f'<text x="{left + old_w + 6:.1f}" y="{y + 17}" class="metric-num">{old}</text>')
        parts.append(f'<rect x="{left}" y="{y + 25}" width="{recent_w:.1f}" height="13" fill="#f97316" rx="2"/>')
        parts.append(f'<text x="{left + recent_w + 6:.1f}" y="{y + 36}" class="metric-num">{recent}</text>')
    parts.append(f'<rect x="{left}" y="{height - 20}" width="11" height="11" fill="#0f766e"/><text x="{left + 17}" y="{height - 11}" class="legend-text">old closures, n=45</text>')
    parts.append(f'<rect x="{left + 170}" y="{height - 20}" width="11" height="11" fill="#f97316"/><text x="{left + 187}" y="{height - 11}" class="legend-text">recent closures, n=30</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def discussion(summary, subject):
    return f"""
    <section class="discussion">
      <h2>Short Discussion</h2>
      <p><b>The strongest signal is fewer new {esc(subject)}.</b> In the full-quarter averages, new {esc(subject)} fell from {f1(summary["growth"]["created"])} per quarter during growth to {f1(summary["decline"]["created"])} during decline. That is a large inflow change, and it starts before the biggest cleanup pulse.</p>
      <p><b>Closures also matter.</b> The monthly net-flow chart shows several months where closures exceeded new {esc(subject)}, especially late 2025 and the partial June 2026 window. That means the falling open count is partly backlog cleanup, not only fewer reports.</p>
      <p><b>Fewer people are filing issues on GitHub.</b> Unique creators fell from {f1(summary["growth"]["unique"])} to {f1(summary["decline"]["unique"])} per quarter, and first-time creators fell from {f1(summary["growth"]["first"])} to {f1(summary["decline"]["first"])}. So the reporting funnel itself looks smaller.</p>
      <p><b>The cautious interpretation:</b> GitHub issue activity is lower, and old backlog is being cleaned up. That does not prove Gutenberg has fewer real-world problems; it means fewer problems are being reported or managed as open GitHub issues, while maintainers are also closing older threads.</p>
    </section>
    """


def view_panel(config, quarters, months, active=False):
    summary = summarize_periods(quarters)
    hidden = "" if active else " hidden"
    active_class = " is-active" if active else ""
    return f"""
  <section class="view-panel{active_class}" data-view-panel="{esc(config["key"])}"{hidden}>
    <section class="view-intro">
      <h2>{esc(config["title"])}</h2>
      <p>{esc(config["note"])}</p>
    </section>

    <h2>Timeline</h2>
    <section class="chart-card">{open_timeline_svg(quarters)}</section>

    <h2>New and Closed Issues</h2>
    <section class="chart-card">{flow_svg(quarters)}</section>

    <h2>Where The Decline Comes From</h2>
    <section class="chart-card">{net_monthly_svg(months)}</section>

    <h2>Reporting Trend</h2>
    <section class="chart-card">{reporter_trend_svg(quarters)}</section>

    {discussion(summary, config["subject"])}
  </section>
    """


def artifact_links():
    links = [
        ("final_report.md", "Narrative report"),
        ("quarterly_metrics.csv", "Quarterly data"),
        ("monthly_metrics.csv", "Monthly data"),
        ("issues_inventory.csv", "Full issue inventory"),
        ("samples/coded_growth_created.csv", "Growth sample coding"),
        ("samples/coded_plateau_created.csv", "Plateau sample coding"),
        ("samples/coded_decline_created.csv", "Decline sample coding"),
    ]
    return "\n".join(f'<a href="{esc(path)}">{esc(label)}</a>' for path, label in links)


def build_html():
    quarters = read_csv(QUARTERLY)
    months = read_csv(MONTHLY)
    issues = enrich_issues(read_csv(ISSUES))
    view_rows = {
        "all": {
            "quarters": quarters,
            "months": months,
        }
    }
    for config in VIEW_CONFIGS:
        if config["key"] == "all":
            continue
        view_rows[config["key"]] = {
            "quarters": build_filtered_quarters(quarters, issues, config["key"]),
            "months": build_filtered_months(months, issues, config["key"]),
        }
    buttons = "\n".join(
        f'    <button class="view-button{" is-active" if idx == 0 else ""}" type="button" data-view-button="{esc(config["key"])}" aria-pressed="{"true" if idx == 0 else "false"}">{esc(config["button"])}</button>'
        for idx, config in enumerate(VIEW_CONFIGS)
    )
    panels = "\n".join(
        view_panel(
            config,
            view_rows[config["key"]]["quarters"],
            view_rows[config["key"]]["months"],
            active=idx == 0,
        )
        for idx, config in enumerate(VIEW_CONFIGS)
    )

    old_counts, _ = code_counts(SAMPLES / "coded_decline_closed_old.csv")
    recent_counts, _ = code_counts(SAMPLES / "coded_decline_closed_recent.csv")

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Why WordPress/gutenberg Issues Grew, Stalled, Then Declined</title>
<style>
:root {{
  --ink: #111827;
  --muted: #4b5563;
  --line: #d7dee8;
  --soft: #f8fafc;
  --panel: #ffffff;
  --blue: #2563eb;
  --red: #dc2626;
  --green: #0f766e;
  --amber: #d97706;
  --purple: #7c3aed;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: #f5f7fb; line-height: 1.5; }}
main {{ max-width: 1240px; margin: 0 auto; padding: 32px 24px 64px; }}
.hero {{ background: #ffffff; border: 1px solid var(--line); border-radius: 8px; padding: 26px; }}
h1 {{ margin: 0; font-size: 38px; line-height: 1.12; max-width: 900px; }}
h2 {{ margin: 38px 0 14px; font-size: 24px; }}
h3 {{ margin: 0 0 8px; font-size: 18px; }}
p {{ margin: 8px 0 0; color: var(--muted); }}
.kicker {{ color: var(--green); font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; margin-bottom: 8px; }}
.view-switch {{ display: inline-flex; flex-wrap: wrap; gap: 6px; margin-top: 18px; padding: 5px; position: sticky; top: 10px; z-index: 20; max-width: 100%; border: 1px solid var(--line); border-radius: 8px; background: #ffffff; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.12); }}
.view-button {{ appearance: none; border: 0; border-radius: 6px; background: transparent; color: #475569; cursor: pointer; font: inherit; font-weight: 800; padding: 9px 12px; }}
.view-button.is-active {{ background: #172033; color: #ffffff; }}
.view-panel[hidden] {{ display: none; }}
.view-intro {{ background: #ffffff; border: 1px solid var(--line); border-radius: 8px; margin-top: 22px; padding: 18px 20px; }}
.view-intro h2 {{ margin: 0 0 8px; }}
.answer-card, .chart-card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; }}
.grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.answers {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }}
.question {{ color: var(--muted); font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: .02em; }}
.answer-card h3 {{ color: var(--ink); }}
.chart-card {{ overflow-x: auto; }}
.chart-card svg {{ width: 100%; height: auto; display: block; }}
.discussion {{ background: #ffffff; border: 1px solid var(--line); border-radius: 8px; padding: 20px 22px; margin-top: 24px; }}
.discussion h2 {{ margin-top: 0; }}
.discussion p {{ color: #263241; font-size: 16px; margin: 12px 0; max-width: 940px; }}
.chart-title {{ font: 700 20px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #111827; }}
.chart-note {{ font: 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #4b5563; }}
.axis {{ font: 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #4b5563; }}
.axis.strong {{ font-weight: 700; fill: #334155; }}
.grid {{ stroke: #dbe3ef; stroke-width: 1; }}
.phase-label {{ font: 700 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #334155; }}
.callout-text {{ font: 700 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #111827; }}
.legend-text {{ font: 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #4b5563; }}
.event-line {{ stroke: #475569; stroke-width: 1.3; stroke-dasharray: 4 4; opacity: .85; }}
.event-connector {{ stroke: #172033; stroke-width: 1.7; }}
.event-dot {{ fill: #334155; stroke: #ffffff; stroke-width: 1.5; }}
.event-label-bg {{ fill: #ffffff; stroke: #334155; stroke-width: 1.1; }}
.event-label {{ font: 800 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #111827; }}
.phase-card-title {{ font: 800 20px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #111827; }}
.phase-card-note {{ font: 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #4b5563; }}
.metric-label {{ font: 13px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #334155; font-weight: 700; }}
.metric-num {{ font: 700 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; fill: #111827; }}
.artifact-links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; }}
.artifact-links a {{ color: #0f5f85; background: #ffffff; border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; text-decoration: none; font-size: 13px; font-weight: 700; }}
details {{ margin-top: 18px; background: #ffffff; border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; }}
summary {{ cursor: pointer; font-weight: 800; }}
ul {{ color: var(--muted); }}
@media (max-width: 980px) {{
  .grid-2 {{ grid-template-columns: 1fr; }}
  .answers {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
}}
@media (max-width: 640px) {{
  main {{ padding: 18px 12px 44px; }}
  h1 {{ font-size: 30px; }}
  .answers {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<main>
  <section class="hero">
    <div class="kicker">WordPress/gutenberg issue analysis</div>
    <h1>Why open issues grew, stalled, then started declining</h1>
    <p>Switch between all issues, bugs, and feature requests at any point while scrolling.</p>
  </section>

  <nav class="view-switch" aria-label="Issue type view">
{buttons}
  </nav>

{panels}

  <details>
    <summary>Optional: what sampled closures looked like</summary>
    <section class="chart-card">{closure_codes_svg(old_counts, recent_counts)}</section>
    <section class="answer-card">
      <div class="question">Interpretation</div>
      <h3>The open count declined partly because old issues were cleaned up.</h3>
      <p>Recent closures more often looked like targeted fixes or active duplicate consolidation. Old closures had more stale, superseded, scope-shift, and "not evidence of an active bug" signals. So the decline is not the same thing as "all old problems were solved."</p>
      <p>That is why the decision answer is mixed: fewer GitHub reports are coming in, and real fixes exist, but backlog pruning is a major part of the visual drop.</p>
    </section>
  </details>

  <details>
    <summary>Methods, caveats, and source files</summary>
    <ul>
      <li>Fetched 32,135 public issue records from the GitHub REST API with authenticated access on 2026-06-11.</li>
      <li>Quarterly and monthly charts exclude pull requests. First and last quarters are partial.</li>
      <li>Labels and state reasons are current API fields, not historical labels at creation time.</li>
      <li>Qualitative coding used deterministic samples: 45 created issues per period, 45 old decline closures, and 30 recent decline closures.</li>
      <li>No off-GitHub channels such as Trac, support forums, Slack, or Make/Core were crawled.</li>
    </ul>
    <div class="artifact-links">{artifact_links()}</div>
</details>
</main>
<script>
  const buttons = [...document.querySelectorAll("[data-view-button]")];
  const panels = [...document.querySelectorAll("[data-view-panel]")];

  function setView(view) {{
    for (const button of buttons) {{
      const active = button.dataset.viewButton === view;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }}
    for (const panel of panels) {{
      const active = panel.dataset.viewPanel === view;
      panel.hidden = !active;
      panel.classList.toggle("is-active", active);
    }}
  }}

  for (const button of buttons) {{
    button.addEventListener("click", () => setView(button.dataset.viewButton));
  }}
</script>
</body>
</html>
"""
    html_doc = "\n".join(line.rstrip() for line in html_doc.splitlines()) + "\n"
    OUT.write_text(html_doc, encoding="utf-8")


if __name__ == "__main__":
    build_html()
    print(OUT)
