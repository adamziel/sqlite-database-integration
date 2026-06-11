#!/usr/bin/env python3
import csv
import html
import json
import statistics
from pathlib import Path


ROOT = Path("/Users/admin/sqlite-database-integration-pages")
MARIA = "mariadb-innodb-baseline"
SQLITE = "sqlite-driver-3.0.0-rc.3"


def f(value):
    if value in ("", None):
        return None
    return float(value)


def pct(sqlite_value, maria_value):
    if sqlite_value is None or maria_value in (None, 0):
        return None
    return (sqlite_value - maria_value) / maria_value * 100


def fmt_pct(value):
    if value is None:
        return "n/a"
    return f"{value:+.1f}%"


def load_request_cells(dir_name):
    path = ROOT / dir_name / "aggregate.csv"
    rows = list(csv.DictReader(path.open()))
    by_key = {
        (row["variant"], row["workload"], int(row["concurrency"])): row
        for row in rows
    }
    cells = []
    for workload in ["read-heavy", "balanced", "write-heavy"]:
        for concurrency in [4, 16, 32, 64]:
            maria = by_key[(MARIA, workload, concurrency)]
            sqlite = by_key[(SQLITE, workload, concurrency)]
            p95_delta = pct(f(sqlite["median_p95_ms"]), f(maria["median_p95_ms"]))
            throughput_delta = pct(
                f(sqlite["median_flows_per_second"]),
                f(maria["median_flows_per_second"]),
            )
            avg_delta = pct(f(sqlite["median_avg_ms"]), f(maria["median_avg_ms"]))
            write_p95_delta = pct(
                f(sqlite["median_write_p95_ms"]),
                f(maria["median_write_p95_ms"]),
            )
            cells.append(
                {
                    "fixture": dir_name,
                    "workload": workload,
                    "concurrency": concurrency,
                    "p95_delta": p95_delta,
                    "throughput_delta": throughput_delta,
                    "avg_delta": avg_delta,
                    "write_p95_delta": write_p95_delta,
                    "sqlite_failures": int(sqlite["total_failed_flows"]),
                    "sqlite_write_failures": int(sqlite["total_write_verification_failures"]),
                    "sqlite_busy": int(sqlite["sqlite_busy_or_locked_errors"]),
                    "sqlite_wal": int(sqlite["max_sqlite_wal_bytes"]),
                }
            )
    return cells


def load_chrome(dir_name):
    path = ROOT / dir_name / "aggregate.json"
    data = json.loads(path.read_text())
    return data["comparisons"]


def classify_cell(cell):
    p95 = cell["p95_delta"]
    throughput = cell["throughput_delta"]
    if p95 is None or throughput is None:
        return "neutral"
    p95_bad = p95 > 5
    p95_good = p95 < -5
    throughput_bad = throughput < -5
    throughput_good = throughput > 5
    if p95_bad and throughput_bad:
        return "slower"
    if p95_good and throughput_good:
        return "good"
    if p95_bad or throughput_bad:
        return "mixed"
    if p95_good or throughput_good:
        return "mixed"
    return "neutral"


def classify_browser(delta):
    if delta is None:
        return "neutral"
    if delta > 10:
        return "slower"
    if delta > 3:
        return "mixed"
    if delta < -3:
        return "good"
    return "neutral"


def summarize_request(cells):
    p95_values = [c["p95_delta"] for c in cells if c["p95_delta"] is not None]
    throughput_values = [
        c["throughput_delta"] for c in cells if c["throughput_delta"] is not None
    ]
    avg_values = [c["avg_delta"] for c in cells if c["avg_delta"] is not None]
    write_values = [
        c["write_p95_delta"] for c in cells if c["write_p95_delta"] is not None
    ]
    return {
        "p95_median": statistics.median(p95_values),
        "p95_better": sum(v < 0 for v in p95_values),
        "p95_total": len(p95_values),
        "throughput_median": statistics.median(throughput_values),
        "throughput_better": sum(v > 0 for v in throughput_values),
        "throughput_total": len(throughput_values),
        "avg_median": statistics.median(avg_values),
        "avg_better": sum(v < 0 for v in avg_values),
        "avg_total": len(avg_values),
        "write_p95_median": statistics.median(write_values) if write_values else None,
        "write_p95_better": sum(v < 0 for v in write_values),
        "write_p95_total": len(write_values),
        "failures": sum(c["sqlite_failures"] for c in cells),
        "write_failures": sum(c["sqlite_write_failures"] for c in cells),
        "busy": sum(c["sqlite_busy"] for c in cells),
    }


def summarize_browser(rows):
    ready = [r["ready_delta_pct"] for r in rows if r.get("ready_delta_pct") is not None]
    p95 = [r["p95_delta_pct"] for r in rows if r.get("p95_delta_pct") is not None]
    ttfb = [r["ttfb_delta_pct"] for r in rows if r.get("ttfb_delta_pct") is not None]
    xhr = [r["xhr_p95_delta_pct"] for r in rows if r.get("xhr_p95_delta_pct") is not None]
    return {
        "ready_median": statistics.median(ready),
        "ready_best": min(ready),
        "ready_worst": max(ready),
        "ready_better": sum(v < 0 for v in ready),
        "ready_total": len(ready),
        "p95_median": statistics.median(p95),
        "ttfb_median": statistics.median(ttfb),
        "xhr_median": statistics.median(xhr) if xhr else None,
        "failures": sum(r["sqlite_failures"] for r in rows),
        "http_failure_rate": max(r["sqlite_http_failure_rate"] for r in rows),
    }


def status_label(status):
    return {
        "good": "Good",
        "neutral": "Tie",
        "mixed": "Mixed",
        "slower": "Slower",
    }[status]


def cell_html(cell):
    status = classify_cell(cell)
    return (
        f'<td class="{status}">'
        f'<div class="badge">{status_label(status)}</div>'
        f'<div><b>p95</b> {fmt_pct(cell["p95_delta"])}</div>'
        f'<div><b>throughput</b> {fmt_pct(cell["throughput_delta"])}</div>'
        "</td>"
    )


def request_grid_html(title, cells):
    by = {(c["workload"], c["concurrency"]): c for c in cells}
    rows = []
    rows.append(f"<h3>{html.escape(title)}</h3>")
    rows.append('<table class="grid"><thead><tr><th>Workload</th><th>c4</th><th>c16</th><th>c32</th><th>c64</th></tr></thead><tbody>')
    for workload in ["read-heavy", "balanced", "write-heavy"]:
        rows.append("<tr>")
        rows.append(f"<th>{html.escape(workload)}</th>")
        for c in [4, 16, 32, 64]:
            rows.append(cell_html(by[(workload, c)]))
        rows.append("</tr>")
    rows.append("</tbody></table>")
    return "\n".join(rows)


def request_grid_svg(title, cells, output):
    by = {(c["workload"], c["concurrency"]): c for c in cells}
    widths = [150, 170, 170, 170, 170]
    row_h = 72
    header_h = 66
    w = sum(widths) + 40
    h = header_h + row_h * 3 + 62
    colors = {
        "good": "#bbf7d0",
        "neutral": "#e5e7eb",
        "mixed": "#fef3c7",
        "slower": "#fecaca",
    }
    x0 = 20
    y0 = 20
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{x0}" y="28" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" font-size="21" font-weight="700" fill="#111827">{html.escape(title)}</text>',
        f'<text x="{x0}" y="50" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" font-size="13" fill="#4b5563">SQLite rc3 vs MariaDB. Green is better, red is worse, yellow is a tradeoff.</text>',
    ]
    y = y0 + 56
    x = x0
    headers = ["Workload", "c4", "c16", "c32", "c64"]
    for idx, header in enumerate(headers):
        parts.append(f'<text x="{x + widths[idx] / 2}" y="{y + 22}" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" font-size="13" font-weight="700" fill="#374151">{html.escape(header)}</text>')
        x += widths[idx]
    y += 34
    for workload in ["read-heavy", "balanced", "write-heavy"]:
        x = x0
        parts.append(f'<text x="{x + 8}" y="{y + 41}" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" font-size="14" font-weight="700" fill="#111827">{html.escape(workload)}</text>')
        x += widths[0]
        for c in [4, 16, 32, 64]:
            cell = by[(workload, c)]
            status = classify_cell(cell)
            parts.append(f'<rect x="{x + 4}" y="{y + 4}" width="{widths[1] - 8}" height="{row_h - 8}" rx="6" fill="{colors[status]}" stroke="#d1d5db"/>')
            parts.append(f'<text x="{x + widths[1] / 2}" y="{y + 24}" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" font-size="13" font-weight="700" fill="#111827">{status_label(status)}</text>')
            parts.append(f'<text x="{x + widths[1] / 2}" y="{y + 43}" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" font-size="12" fill="#111827">p95 {fmt_pct(cell["p95_delta"])}</text>')
            parts.append(f'<text x="{x + widths[1] / 2}" y="{y + 60}" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" font-size="12" fill="#111827">thru {fmt_pct(cell["throughput_delta"])}</text>')
            x += widths[1]
        y += row_h
    parts.append("</svg>")
    output.write_text("\n".join(parts) + "\n")


def browser_rows_html(title, rows):
    out = [f"<h3>{html.escape(title)}</h3>"]
    out.append('<table><thead><tr><th>Flow</th><th>Ready impact</th><th>p95 ready</th><th>TTFB</th><th>XHR p95</th></tr></thead><tbody>')
    for row in rows:
        status = classify_browser(row["ready_delta_pct"])
        out.append(
            f'<tr><td>{html.escape(row["label"])}</td>'
            f'<td class="{status}"><b>{status_label(status)}</b> {fmt_pct(row["ready_delta_pct"])}</td>'
            f'<td>{fmt_pct(row["p95_delta_pct"])}</td>'
            f'<td>{fmt_pct(row["ttfb_delta_pct"])}</td>'
            f'<td>{fmt_pct(row.get("xhr_p95_delta_pct"))}</td></tr>'
        )
    out.append("</tbody></table>")
    return "\n".join(out)


def worst_label(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return "n/a"
    return fmt_pct(max(vals, key=abs))


def compact_surface_table(restaurant, woo, restaurant_chrome, woo_chrome):
    restaurant_s = summarize_request(restaurant)
    woo_s = summarize_request(woo)
    restaurant_b = summarize_browser(restaurant_chrome)
    woo_b = summarize_browser(woo_chrome)
    rows = [
        (
            "Small restaurant load",
            f"p95 faster in {restaurant_s['p95_better']}/{restaurant_s['p95_total']} cells",
            f"throughput higher in {restaurant_s['throughput_better']}/{restaurant_s['throughput_total']} cells",
            "Latency often improved, but throughput was usually lower.",
            "mixed",
        ),
        (
            "5GB WooCommerce load",
            f"p95 faster in {woo_s['p95_better']}/{woo_s['p95_total']} cells",
            f"throughput higher in {woo_s['throughput_better']}/{woo_s['throughput_total']} cells",
            "High-concurrency write-heavy traffic was slower.",
            "slower",
        ),
        (
            "Restaurant Chrome",
            f"median ready {fmt_pct(restaurant_b['ready_median'])}",
            f"median TTFB {fmt_pct(restaurant_b['ttfb_median'])}",
            "Browser-visible result was essentially tied.",
            "neutral",
        ),
        (
            "WooCommerce Chrome",
            f"median ready {fmt_pct(woo_b['ready_median'])}",
            "Woo admin orders +13.9% ready",
            "Most flows were near parity; admin orders was slower.",
            "mixed",
        ),
    ]
    out = ['<table class="compact"><thead><tr><th>Surface</th><th>Latency</th><th>Capacity / server</th><th>Readout</th></tr></thead><tbody>']
    for surface, latency, capacity, readout, cls in rows:
        out.append(
            f'<tr><td><b>{html.escape(surface)}</b></td>'
            f'<td>{html.escape(latency)}</td>'
            f'<td>{html.escape(capacity)}</td>'
            f'<td class="{cls}">{html.escape(readout)}</td></tr>'
        )
    out.append("</tbody></table>")
    return "\n".join(out)


def workload_summary_table(restaurant, woo):
    rows = []
    for fixture_label, cells in [
        ("Small restaurant", restaurant),
        ("5GB WooCommerce", woo),
    ]:
        for workload in ["read-heavy", "balanced", "write-heavy"]:
            subset = [c for c in cells if c["workload"] == workload]
            p95_better = sum(c["p95_delta"] is not None and c["p95_delta"] < 0 for c in subset)
            throughput_higher = sum(
                c["throughput_delta"] is not None and c["throughput_delta"] > 0
                for c in subset
            )
            p95_values = [c["p95_delta"] for c in subset if c["p95_delta"] is not None]
            throughput_values = [
                c["throughput_delta"]
                for c in subset
                if c["throughput_delta"] is not None
            ]
            if throughput_higher == 0 and p95_better <= 1:
                readout = "slower overall"
                cls = "slower"
            elif throughput_higher <= 1:
                readout = "latency/capacity tradeoff"
                cls = "mixed"
            elif p95_better >= 3 and throughput_higher >= 2:
                readout = "best fit in this set"
                cls = "good"
            else:
                readout = "mixed"
                cls = "mixed"
            rows.append(
                (
                    fixture_label,
                    workload,
                    f"{p95_better}/4 faster; worst {fmt_pct(max(p95_values))}",
                    f"{throughput_higher}/4 higher; median {fmt_pct(statistics.median(throughput_values))}",
                    readout,
                    cls,
                )
            )
    out = ['<table class="compact"><thead><tr><th>Fixture</th><th>Workload</th><th>p95 latency</th><th>Throughput</th><th>Summary</th></tr></thead><tbody>']
    for fixture, workload, p95, throughput, readout, cls in rows:
        out.append(
            f"<tr><td>{html.escape(fixture)}</td><td><b>{html.escape(workload)}</b></td>"
            f"<td>{html.escape(p95)}</td><td>{html.escape(throughput)}</td>"
            f'<td class="{cls}">{html.escape(readout)}</td></tr>'
        )
    out.append("</tbody></table>")
    return "\n".join(out)


def metric_card(title, verdict, value, note, cls):
    return (
        f'<section class="card {cls}">'
        f"<h3>{html.escape(title)}</h3>"
        f'<div class="verdict">{html.escape(verdict)}</div>'
        f'<div class="big">{html.escape(value)}</div>'
        f"<p>{html.escape(note)}</p>"
        "</section>"
    )


def make_markdown(restaurant, woo, restaurant_chrome, woo_chrome):
    lines = [
        "# SQLite rc3 vs MariaDB: Decision Summary",
        "",
        "Decision: SQLite Database Integration v3.0.0-rc.3 looks viable for small or low-concurrency sites after environment-specific validation, but the current measurements do not support making it the default replacement for MariaDB on write-heavy or high-concurrency WooCommerce production sites.",
        "",
        "## Simple Dimensions",
        "",
        "| Dimension | Impact of SQLite rc3 vs MariaDB | Decision meaning |",
        "| --- | --- | --- |",
        "| Browser-visible page readiness | Mostly tied; median ready delta was +0.2% on restaurant flows and +0.4% on WooCommerce flows. | Most users probably would not notice on ordinary page/editor flows. |",
        "| Server request capacity | Slower under load; SQLite throughput was lower in 20 of 24 request-load cells. | Capacity headroom is the main reason not to make it the default everywhere. |",
        "| Tail latency | Mixed; p95 improved in 15 of 24 request-load cells, but WooCommerce write-heavy c32/c64 regressed +33.9%/+40.0%. | p95 alone is not enough; pair it with throughput. |",
        "| Writes and correctness | rc3 had 0 flow failures, 0 write verification failures, and 0 SQLite busy/locked errors in these local runs. | rc3 is much healthier than the old stable control, but write-heavy capacity still needs caution. |",
        "| Operational fit | SQLite removes the MariaDB service but uses WAL files and has different concurrency behavior. | Simpler stack, but not automatically faster at scale. |",
        "",
        "## Recommendation",
        "",
        "- Use rc3 as a serious candidate for small sites, development, demos, local-first deployments, and low-write sites.",
        "- Do not treat rc3 as a blanket MariaDB replacement for WooCommerce or high-write production traffic based on these measurements.",
        "- If adopting, gate it by workload: browser journeys, checkout/admin writes, request throughput at expected concurrency, write verification, and lock/busy logs.",
    ]
    return "\n".join(lines) + "\n"


def make_html(restaurant, woo, restaurant_chrome, woo_chrome):
    restaurant_s = summarize_request(restaurant)
    woo_s = summarize_request(woo)
    restaurant_browser = summarize_browser(restaurant_chrome)
    woo_browser = summarize_browser(woo_chrome)
    html_parts = []
    html_parts.append("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">")
    html_parts.append("<title>SQLite rc3 vs MariaDB Decision Summary</title>")
    html_parts.append(
        """
<style>
:root { --ink:#111827; --muted:#4b5563; --line:#d6dde8; --soft:#f8fafc; --good:#bbf7d0; --neutral:#e5e7eb; --mixed:#fef3c7; --slower:#fecaca; --blue:#0f6b8f; }
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: #ffffff; line-height: 1.48; }
main { max-width: 1160px; margin: 0 auto; padding: 36px 24px 60px; }
h1 { margin: 0 0 8px; font-size: 34px; line-height: 1.15; }
h2 { margin: 36px 0 14px; padding-top: 18px; border-top: 1px solid var(--line); font-size: 24px; }
h3 { margin: 0 0 10px; font-size: 17px; }
p { color: var(--muted); margin: 8px 0 12px; }
.lede { font-size: 18px; color: #263241; max-width: 920px; }
.cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 22px 0; }
.card { border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: var(--soft); min-height: 180px; }
.card.good { border-color: #86efac; background: #f0fdf4; }
.card.neutral { border-color: #cbd5e1; background: #f8fafc; }
.card.mixed { border-color: #fde68a; background: #fffbeb; }
.card.slower { border-color: #fca5a5; background: #fff1f2; }
.verdict { display: inline-block; font-weight: 700; font-size: 13px; padding: 3px 8px; border-radius: 999px; background: #fff; border: 1px solid var(--line); margin-bottom: 10px; }
.big { font-size: 25px; font-weight: 800; margin: 2px 0 8px; }
.callout { border-left: 5px solid var(--blue); background: #eef8fb; padding: 14px 16px; margin: 18px 0 24px; }
.table-scroll { overflow-x: auto; margin: 14px 0 24px; }
table { border-collapse: collapse; width: 100%; min-width: 760px; border: 1px solid var(--line); }
th, td { border-bottom: 1px solid var(--line); padding: 10px 11px; text-align: left; vertical-align: top; }
th { background: var(--soft); font-weight: 700; }
td.good, .good-cell { background: var(--good); }
td.neutral, .neutral-cell { background: var(--neutral); }
td.mixed, .mixed-cell { background: var(--mixed); }
td.slower, .slower-cell { background: var(--slower); }
.grid td { min-width: 150px; }
.badge { font-weight: 800; margin-bottom: 4px; }
.legend { display: flex; gap: 12px; flex-wrap: wrap; margin: 8px 0 16px; color: var(--muted); font-size: 13px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.swatch { width: 18px; height: 14px; border: 1px solid #9ca3af; border-radius: 3px; }
.dim-table td:first-child { font-weight: 700; width: 23%; }
ul { padding-left: 22px; }
li { margin: 6px 0; color: #263241; }
.small { font-size: 13px; color: var(--muted); }
@media (max-width: 900px) { .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) { main { padding: 24px 14px 44px; } .cards { grid-template-columns: 1fr; } h1 { font-size: 28px; } }
</style>
"""
    )
    html_parts.append("</head><body><main>")
    html_parts.append("<h1>SQLite rc3 vs MariaDB: decision summary</h1>")
    html_parts.append('<p class="lede">SQLite Database Integration <code>v3.0.0-rc.3</code> is much more stable than the old SQLite control in these local diagnostics, but it is not a blanket MariaDB replacement yet. It is closest to parity in browser-visible flows and slowest under high-concurrency WooCommerce writes.</p>')
    html_parts.append('<div class="callout"><b>Decision read:</b> good candidate for small/low-write sites after validation; keep MariaDB for high-write or high-concurrency WooCommerce until more hosted production-like evidence closes the throughput gap.</div>')
    html_parts.append('<div class="cards">')
    html_parts.append(metric_card("Browser-visible UX", "Mostly tied", f"median ready {fmt_pct(restaurant_browser['ready_median'])} restaurant, {fmt_pct(woo_browser['ready_median'])} Woo", "Most page/editor journeys were visually near parity. Woo admin orders was the notable regression at +13.9% median ready.", "neutral"))
    html_parts.append(metric_card("Request throughput", "Slower under load", f"{restaurant_s['throughput_better'] + woo_s['throughput_better']} / 24 cells higher", "SQLite completed fewer flows/sec in most request-load cells, especially under WooCommerce c16-c64.", "slower"))
    html_parts.append(metric_card("Tail latency", "Mixed", f"{restaurant_s['p95_better'] + woo_s['p95_better']} / 24 p95 cells faster", "Several p95 wins come with lower throughput. Woo write-heavy c32/c64 was clearly worse.", "mixed"))
    html_parts.append(metric_card("Correctness / locks", "Clean in rc3 runs", "0 failures, 0 busy locks", "Across these rc3 request-load and Chrome runs: no flow failures, write verification failures, or SQLite busy/locked log events.", "good"))
    html_parts.append("</div>")
    html_parts.append("<h2>Simple dimensions</h2>")
    html_parts.append('<div class="table-scroll"><table class="dim-table"><thead><tr><th>Dimension</th><th>Impact of SQLite rc3 vs MariaDB</th><th>Decision meaning</th></tr></thead><tbody>')
    dimensions = [
        ("Browser-visible page readiness", "Mostly tied: median ready delta was +0.2% on restaurant flows and +0.4% on WooCommerce flows.", "Most ordinary users probably would not notice on page/editor flows."),
        ("Server request capacity", "Slower under load: SQLite throughput was higher in only 4 of 24 request-load cells.", "Capacity headroom is the main reason not to make it the default everywhere."),
        ("Tail latency", "Mixed: p95 improved in 15 of 24 request-load cells, but WooCommerce write-heavy c32/c64 regressed +33.9%/+40.0%.", "Do not use p95 alone; pair it with throughput."),
        ("Writes and correctness", "rc3 had 0 flow failures, 0 write verification failures, and 0 SQLite busy/locked errors in these local runs.", "Much healthier than the old stable control, but write-heavy capacity still needs caution."),
        ("Operational fit", "SQLite removes the MariaDB service, but adds WAL behavior and different concurrency limits.", "Simpler stack, not automatically faster at scale."),
    ]
    for dim, impact, meaning in dimensions:
        html_parts.append(f"<tr><td>{html.escape(dim)}</td><td>{html.escape(impact)}</td><td>{html.escape(meaning)}</td></tr>")
    html_parts.append("</tbody></table></div>")
    html_parts.append("<h2>Why the old scatterplot was hard to read</h2>")
    html_parts.append("<p>The scatterplot put two different questions on one chart: throughput on the x-axis and p95 latency on the y-axis. Right is more capacity. Down is lower tail latency. The best possible movement is down and right.</p>")
    html_parts.append("<p>The confusing cases are where SQLite moves down and left: lower p95 latency, but less throughput. That is not a clean win. The compressed tables below call that a tradeoff.</p>")
    html_parts.append("<h2>Compressed readout</h2>")
    html_parts.append('<div class="table-scroll">' + compact_surface_table(restaurant, woo, restaurant_chrome, woo_chrome) + "</div>")
    html_parts.append("<h2>Workload summary</h2>")
    html_parts.append('<div class="table-scroll">' + workload_summary_table(restaurant, woo) + "</div>")
    html_parts.append('<p class="small">Detailed per-concurrency grids are still available as separate SVGs: <code>restaurant-request-load-benchmark/easy-impact-grid.svg</code> and <code>woocommerce-c4-16-32-64-benchmark/easy-impact-grid.svg</code>.</p>')
    html_parts.append("<h2>Recommendation</h2>")
    html_parts.append("<ul>")
    html_parts.append("<li><b>Use rc3 as a serious candidate</b> for small sites, local-first deployments, demos, dev/test, and low-write sites.</li>")
    html_parts.append("<li><b>Do not make it the default MariaDB replacement</b> for high-write or high-concurrency WooCommerce production traffic based on these measurements.</li>")
    html_parts.append("<li><b>If adopting, gate by workload:</b> browser journeys, checkout/admin writes, request throughput at expected concurrency, write verification, WAL growth, and lock/busy logs.</li>")
    html_parts.append("</ul>")
    html_parts.append('<p class="small">Scope caveat: these are local macOS diagnostics, not final hosted Linux production measurements. They are useful for directional decision-making and deciding what to validate next.</p>')
    html_parts.append("</main></body></html>")
    return "\n".join(html_parts)


def main():
    restaurant = load_request_cells("restaurant-request-load-benchmark")
    woo = load_request_cells("woocommerce-c4-16-32-64-benchmark")
    restaurant_chrome = load_chrome("restaurant-chrome-browser-benchmark")
    woo_chrome = load_chrome("woocommerce-chrome-browser-benchmark")

    (ROOT / "sqlite-rc3-decision-summary.md").write_text(
        make_markdown(restaurant, woo, restaurant_chrome, woo_chrome),
        encoding="utf-8",
    )
    (ROOT / "sqlite-rc3-decision-summary.html").write_text(
        make_html(restaurant, woo, restaurant_chrome, woo_chrome),
        encoding="utf-8",
    )
    request_grid_svg(
        "Small restaurant request-load impact grid",
        restaurant,
        ROOT / "restaurant-request-load-benchmark" / "easy-impact-grid.svg",
    )
    request_grid_svg(
        "WooCommerce request-load impact grid",
        woo,
        ROOT / "woocommerce-c4-16-32-64-benchmark" / "easy-impact-grid.svg",
    )
    print(ROOT / "sqlite-rc3-decision-summary.html")
    print(ROOT / "sqlite-rc3-decision-summary.md")
    print(ROOT / "restaurant-request-load-benchmark" / "easy-impact-grid.svg")
    print(ROOT / "woocommerce-c4-16-32-64-benchmark" / "easy-impact-grid.svg")


if __name__ == "__main__":
    main()
