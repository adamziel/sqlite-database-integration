#!/usr/bin/env python3
"""Build the WooCommerce HPOS MySQL profiling report for GitHub Pages."""

from __future__ import annotations

import csv
import html
import json
import math
import os
import shutil
import statistics
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PAGES_ROOT = Path(__file__).resolve().parent
DEFAULT_RUN = Path(
    "/Users/admin/wordpress-sqlite-benchmark-runner/artifacts/woocommerce-hpos-mysql-profile/runs/20260613T010902Z"
)
RUN_DIR = Path(os.environ.get("WOO_HPOS_PROFILE_RUN", str(DEFAULT_RUN)))
OUT_DIR = PAGES_ROOT / "woocommerce-hpos-mysql-profile"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fmt_ms(value: Any) -> str:
    if value is None or value == "":
        return ""
    value = float(value)
    if value >= 1000:
        return f"{value / 1000:.2f}s"
    return f"{value:.0f}ms"


def fmt_num(value: Any, digits: int = 2) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, int):
        return f"{value:,}"
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def fmt_pct(value: Any, digits: int = 1) -> str:
    if value is None or value == "":
        return ""
    return f"{float(value) * 100:.{digits}f}%"


def pct(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def cell_class(value: Any, good_max: float, warn_max: float) -> str:
    if value is None or value == "":
        return ""
    numeric = float(value)
    if numeric <= good_max:
        return "good"
    if numeric <= warn_max:
        return "warn"
    return "bad"


def route_label(uri: str) -> tuple[str, str]:
    parsed = urllib.parse.urlsplit(uri)
    query = urllib.parse.parse_qs(parsed.query)
    path = parsed.path or "/"
    if path.startswith("/wp-admin/admin.php") and query.get("page", [""])[0] == "wc-orders":
        if "s" in query:
            return "admin", "Admin: HPOS order search"
        if query.get("action", [""])[0] == "edit":
            return "admin", "Admin: edit order"
        if "status" in query:
            return "admin", "Admin: orders list, filtered"
        return "admin", "Admin: orders list"
    if query.get("wc-ajax", [""])[0] == "checkout":
        return "customer", "Customer: checkout AJAX order submit"
    if "add-to-cart" in query:
        return "customer", "Customer: add to cart"
    if "s" in query and query.get("post_type", [""])[0] == "product":
        return "customer", "Customer: product search"
    if query.get("post_type", [""])[0] == "product":
        return "customer", "Customer: shop archive"
    if query.get("page_id", [""])[0] == "10":
        return "customer", "Customer: shop page"
    if query.get("page_id", [""])[0] == "11":
        return "customer", "Customer: cart page"
    if query.get("page_id", [""])[0] == "12":
        return "customer", "Customer: checkout page"
    if path == "/":
        return "customer", "Customer: home/product page"
    if path.startswith("/wp-admin/"):
        return "admin", "Admin: other"
    return "customer", "Customer: other"


def load_request_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((RUN_DIR / "raw").glob("*-wp-request-log.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line:
                continue
            row = json.loads(line)
            if row.get("phase") == "measure":
                rows.append(row)
    return rows


def summarize_routes(request_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in request_rows:
        audience, label = route_label(str(row.get("uri") or ""))
        grouped[(audience, label)].append(row)
    summaries = []
    for (audience, route), rows in grouped.items():
        wall = [float(row.get("wall_ms") or 0) for row in rows]
        db = [float(row.get("db_time_ms") or 0) for row in rows]
        queries = [float(row.get("query_count") or 0) for row in rows]
        summaries.append(
            {
                "audience": audience,
                "route": route,
                "requests": len(rows),
                "avg_wall_ms": statistics.mean(wall),
                "p50_wall_ms": pct(wall, 0.50),
                "p95_wall_ms": pct(wall, 0.95),
                "p99_wall_ms": pct(wall, 0.99),
                "max_wall_ms": max(wall),
                "avg_db_ms": statistics.mean(db),
                "p95_db_ms": pct(db, 0.95),
                "avg_queries": statistics.mean(queries),
                "max_queries": max(queries),
            }
        )
    return sorted(summaries, key=lambda row: (row["audience"], -(row["p95_wall_ms"] or 0)))


def digest_label(digest: str) -> str:
    if "wp_wc_orders" in digest and "search_query_meta" in digest and "ORDER BY" in digest:
        return "HPOS order search ids"
    if "wp_wc_orders" in digest and "search_query_meta" in digest and "COUNT" in digest:
        return "HPOS order search count"
    if "SELECT `status`" in digest and "wp_wc_orders" in digest:
        return "Order status counts"
    if "wp_options" in digest and "option_name" in digest and "LIMIT" in digest:
        return "Options point lookup"
    if "SQL_CALC_FOUND_ROWS" in digest and "wp_posts" in digest:
        return "Product search query"
    if "wp_wc_orders_meta" in digest and "WHERE `order_id` IN" in digest:
        return "Load HPOS order meta"
    if "wp_woocommerce_sessions" in digest:
        return "Woo session write/read"
    if "wp_postmeta" in digest:
        return "Load post meta"
    if "wp_wc_orders" in digest and "wp_wc_order_addresses" in digest:
        return "Load HPOS order records"
    return digest[:80]


def bar_chart(
    rows: list[dict[str, Any]],
    label_key: str,
    value_key: str,
    title: str,
    subtitle: str = "",
    *,
    unit: str = "ms",
    width: int = 1160,
    scale: str = "linear",
    color: str = "#2563eb",
) -> str:
    if not rows:
        return ""
    left = 310
    right = 116
    top = 66
    row_h = 34
    height = top + row_h * len(rows) + 34
    values = [float(row.get(value_key) or 0) for row in rows]
    if scale == "log":
        scaled = [math.log10(value + 1) for value in values]
    else:
        scaled = values
    max_scaled = max(scaled) or 1
    plot_w = width - left - right
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">',
        f'<text x="0" y="28" class="chart-title">{html.escape(title)}</text>',
    ]
    if subtitle:
        parts.append(f'<text x="0" y="50" class="chart-subtitle">{html.escape(subtitle)}</text>')
    for index, row in enumerate(rows):
        y = top + index * row_h
        label = str(row.get(label_key) or "")
        value = float(row.get(value_key) or 0)
        scaled_value = math.log10(value + 1) if scale == "log" else value
        bar_w = max(2, scaled_value / max_scaled * plot_w)
        parts.append(f'<text x="0" y="{y + 18}" class="bar-label">{html.escape(label[:44])}</text>')
        parts.append(f'<rect x="{left}" y="{y}" width="{bar_w:.1f}" height="22" rx="4" fill="{color}" />')
        if unit == "ms":
            value_text = fmt_ms(value)
        elif unit == "s":
            value_text = f"{fmt_num(value)}s"
        else:
            value_text = fmt_num(value)
        parts.append(f'<text x="{left + bar_w + 9:.1f}" y="{y + 16}" class="bar-value">{html.escape(value_text)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def scatter_chart(routes: list[dict[str, Any]], width: int = 940, height: int = 520) -> str:
    rows = [row for row in routes if row.get("p95_wall_ms") and row.get("avg_db_ms")]
    if not rows:
        return ""
    pad_l = 82
    pad_r = 30
    pad_t = 64
    pad_b = 70
    max_x = max(float(row["p95_wall_ms"]) for row in rows)
    max_y = max(float(row["avg_db_ms"]) for row in rows)

    def scale_x(value: float) -> float:
        return pad_l + math.log10(value + 1) / math.log10(max_x + 1) * (width - pad_l - pad_r)

    def scale_y(value: float) -> float:
        return height - pad_b - math.log10(value + 1) / math.log10(max_y + 1) * (height - pad_t - pad_b)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Route latency versus DB time">',
        '<text x="0" y="28" class="chart-title">Route p95 Wall Time vs Average DB Time</text>',
        '<text x="0" y="50" class="chart-subtitle">Log scales. Admin route points are red; customer route points are blue.</text>',
        f'<line x1="{pad_l}" y1="{height - pad_b}" x2="{width - pad_r}" y2="{height - pad_b}" class="axis" />',
        f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height - pad_b}" class="axis" />',
        f'<text x="{width / 2 - 60:.1f}" y="{height - 18}" class="axis-label">p95 wall time</text>',
        f'<text x="8" y="{height / 2:.1f}" class="axis-label" transform="rotate(-90 8,{height / 2:.1f})">average DB time</text>',
    ]
    for row in rows:
        x = scale_x(float(row["p95_wall_ms"]))
        y = scale_y(float(row["avg_db_ms"]))
        color = "#dc2626" if row["audience"] == "admin" else "#2563eb"
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{color}" opacity="0.82"><title>{html.escape(row["route"])}: p95 {fmt_ms(row["p95_wall_ms"])}, avg DB {fmt_ms(row["avg_db_ms"])}</title></circle>')
        if row["route"] in {"Admin: HPOS order search", "Customer: checkout AJAX order submit", "Customer: product search"}:
            parts.append(f'<text x="{x + 10:.1f}" y="{y - 8:.1f}" class="point-label">{html.escape(row["route"].replace("Customer: ", "").replace("Admin: ", ""))}</text>')
    for tick in [100, 1000, 10000, 60000]:
        if tick <= max_x:
            x = scale_x(tick)
            parts.append(f'<line x1="{x:.1f}" y1="{height - pad_b}" x2="{x:.1f}" y2="{height - pad_b + 6}" class="axis" />')
            parts.append(f'<text x="{x - 14:.1f}" y="{height - pad_b + 24}" class="tick">{fmt_ms(tick)}</text>')
    for tick in [10, 100, 1000, 10000, 30000]:
        if tick <= max_y:
            y = scale_y(tick)
            parts.append(f'<line x1="{pad_l - 6}" y1="{y:.1f}" x2="{pad_l}" y2="{y:.1f}" class="axis" />')
            parts.append(f'<text x="{pad_l - 68}" y="{y + 4:.1f}" class="tick">{fmt_ms(tick)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def route_table(rows: list[dict[str, Any]]) -> str:
    body = []
    for row in rows:
        body.append(
            f"""<tr>
<td>{html.escape(row['route'])}</td>
<td>{fmt_num(row['requests'], 0)}</td>
<td class="{cell_class(row['avg_wall_ms'], 250, 900)}">{fmt_ms(row['avg_wall_ms'])}</td>
<td class="{cell_class(row['p95_wall_ms'], 800, 2000)}">{fmt_ms(row['p95_wall_ms'])}</td>
<td class="{cell_class(row['max_wall_ms'], 2000, 10000)}">{fmt_ms(row['max_wall_ms'])}</td>
<td>{fmt_ms(row['avg_db_ms'])}</td>
<td>{fmt_num(row['avg_queries'])}</td>
</tr>"""
        )
    return "\n".join(body)


def digest_table(rows: list[dict[str, Any]]) -> str:
    body = []
    for row in rows:
        body.append(
            f"""<tr>
<td>{html.escape(row['label'])}</td>
<td>{fmt_num(row['count'], 0)}</td>
<td class="{cell_class(row['total_s'], 10, 60)}">{fmt_num(row['total_s'])}s</td>
<td>{fmt_ms(row['max_ms'])}</td>
<td>{fmt_num(row['rows_examined'], 0)}</td>
<td><code>{html.escape(row['digest'][:520])}</code></td>
</tr>"""
        )
    return "\n".join(body)


def main() -> int:
    if not RUN_DIR.exists():
        raise SystemExit(f"Missing run directory: {RUN_DIR}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest = read_json(RUN_DIR / "manifest.json")
    aggregate = read_json(RUN_DIR / "aggregate.json")
    findings = read_json(RUN_DIR / "findings.json")
    results = read_json(RUN_DIR / "results.json")
    request_rows = load_request_rows()
    routes = summarize_routes(request_rows)
    customer_routes = [row for row in routes if row["audience"] == "customer"]
    admin_routes = [row for row in routes if row["audience"] == "admin"]

    digests = []
    for row in findings["mysql_digests"]:
        digests.append({**row, "label": digest_label(row["digest"])})
    table_io = findings["table_io"]

    write_csv(OUT_DIR / "route-summary.csv", routes)
    write_csv(OUT_DIR / "query-digests.csv", digests)
    write_csv(OUT_DIR / "table-io.csv", table_io)
    for name in ["aggregate.csv", "results.csv", "manifest.json", "aggregate.json", "findings.json", "results.json"]:
        source = RUN_DIR / name
        if source.exists():
            shutil.copy2(source, OUT_DIR / name)

    fixture = manifest.get("fixture", {})
    versions = manifest.get("versions", {})
    status_counts = findings.get("status_counts", {})
    customer_chart = bar_chart(customer_routes, "route", "p95_wall_ms", "Slowest Customer Routes", "p95 wall time from completed WordPress requests.", color="#2563eb")
    admin_chart = bar_chart(admin_routes, "route", "p95_wall_ms", "Slowest Admin Routes", "p95 wall time. Log scale because order search dwarfs the other admin routes.", scale="log", color="#dc2626")
    query_chart = bar_chart(digests[:12], "label", "total_s", "Top MySQL Statement Digests", "Cumulative MySQL time across all load cells. Log scale.", unit="s", scale="log", color="#7c3aed")
    table_chart = bar_chart(table_io[:10], "table", "total_s", "Top Table I/O Wait", "Cumulative Performance Schema table I/O wait.", unit="s", color="#0f766e")
    scatter = scatter_chart(routes)

    worst_customer = max(customer_routes, key=lambda row: row["p95_wall_ms"])
    worst_admin = max(admin_routes, key=lambda row: row["p95_wall_ms"])
    top_digest = digests[0]
    failed_rate = findings.get("failed_flow_rate", 0)
    server_error_rate = findings.get("server_error_rate", 0)

    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WooCommerce HPOS MySQL Large Store Profile</title>
  <style>
    :root {{
      --bg:#f6f8fb;
      --panel:#ffffff;
      --ink:#142033;
      --muted:#5b6b7f;
      --line:#d9e2ee;
      --blue:#2563eb;
      --red:#dc2626;
      --purple:#7c3aed;
      --teal:#0f766e;
      --good:#dcfce7;
      --warn:#fef3c7;
      --bad:#fee2e2;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.48 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    main {{ max-width:1500px; margin:0 auto; padding:30px 24px 54px; }}
    h1 {{ margin:0 0 8px; font-size:34px; letter-spacing:0; }}
    h2 {{ margin:32px 0 12px; font-size:23px; letter-spacing:0; }}
    h3 {{ margin:18px 0 8px; font-size:17px; }}
    p, li {{ color:var(--muted); }}
    a {{ color:var(--blue); font-weight:700; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .lede {{ max-width:980px; margin:0; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:12px; margin:20px 0; }}
    .stat, .panel, .chart {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .stat strong {{ display:block; font-size:25px; color:var(--ink); }}
    .stat span {{ color:var(--muted); }}
    .finding {{ border-color:#fecaca; background:#fff1f2; }}
    .note {{ border-color:#bfdbfe; background:#eff6ff; }}
    .chart {{ margin:14px 0; overflow-x:auto; }}
    .chart svg {{ width:100%; min-width:940px; height:auto; display:block; }}
    .chart-title {{ font-size:22px; font-weight:700; fill:var(--ink); }}
    .chart-subtitle, .bar-label, .bar-value, .tick, .axis-label, .point-label {{ fill:#334155; font-size:12px; }}
    .bar-value {{ font-weight:700; }}
    .axis {{ stroke:#94a3b8; stroke-width:1; }}
    table {{ width:100%; border-collapse:collapse; margin:10px 0 20px; background:var(--panel); }}
    th, td {{ border:1px solid var(--line); padding:8px 10px; text-align:right; vertical-align:top; }}
    th {{ background:#e8eef6; text-transform:uppercase; font-size:12px; color:#334155; }}
    td:first-child, th:first-child {{ text-align:left; }}
    tr:nth-child(even) td {{ background:#fbfcfe; }}
    td.good {{ background:var(--good); }}
    td.warn {{ background:var(--warn); }}
    td.bad {{ background:var(--bad); }}
    code {{ white-space:pre-wrap; word-break:break-word; background:#eef2f7; border-radius:4px; padding:2px 4px; }}
    .wide {{ overflow-x:auto; }}
    .cols {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(420px,1fr)); gap:14px; }}
  </style>
</head>
<body>
<main>
  <h1>WooCommerce HPOS MySQL Large Store Profile</h1>
  <p class="lede">Deep local profiling of WooCommerce on MySQL 8.4 with HPOS enabled and fast-store settings. The fixture used {fmt_num(fixture.get('schema_apparent_bytes'), 0)} apparent schema bytes, {fmt_num(fixture.get('orders'), 0)} HPOS orders, {fmt_num(fixture.get('products'), 0)} products, and {fmt_num(fixture.get('customers'), 0)} customers.</p>

  <div class="grid">
    <div class="stat"><strong>{fmt_num(fixture.get('schema_apparent_bytes'), 0)}</strong><span>MySQL schema bytes</span></div>
    <div class="stat"><strong>{fmt_num(fixture.get('orders'), 0)}</strong><span>HPOS orders before load</span></div>
    <div class="stat"><strong>{fmt_num(len(request_rows), 0)}</strong><span>completed measured WP requests logged</span></div>
    <div class="stat"><strong>{fmt_pct(failed_rate)}</strong><span>benchmark flow timeout rate</span></div>
    <div class="stat"><strong>{fmt_pct(server_error_rate)}</strong><span>HTTP 4xx/5xx response rate</span></div>
    <div class="stat"><strong>{fmt_num(findings.get('lock_waits'), 0)}</strong><span>InnoDB row lock waits</span></div>
  </div>

  <section class="panel finding">
    <h2>Executive Readout</h2>
    <ul>
      <li><strong>Slowest customer route:</strong> {html.escape(worst_customer['route'])}, p95 {fmt_ms(worst_customer['p95_wall_ms'])}, average DB time {fmt_ms(worst_customer['avg_db_ms'])}, average {fmt_num(worst_customer['avg_queries'])} queries/request.</li>
      <li><strong>Slowest admin route:</strong> {html.escape(worst_admin['route'])}, p95 {fmt_ms(worst_admin['p95_wall_ms'])}, max {fmt_ms(worst_admin['max_wall_ms'])}, average DB time {fmt_ms(worst_admin['avg_db_ms'])}.</li>
      <li><strong>Dominant query:</strong> {html.escape(top_digest['label'])}, {fmt_num(top_digest['total_s'])}s cumulative MySQL time, {fmt_ms(top_digest['max_ms'])} max, {fmt_num(top_digest['rows_examined'], 0)} rows examined.</li>
      <li><strong>Failure semantics:</strong> {fmt_num(findings.get('failed_flows'), 0)} failed flows were client-side 30s timeouts, all on admin order reads. The benchmark client observed status counts {html.escape(json.dumps(status_counts, sort_keys=True))}; no HTTP 500 response was observed.</li>
    </ul>
  </section>

  <h2>Charts</h2>
  <div class="chart">{customer_chart}</div>
  <div class="chart">{admin_chart}</div>
  <div class="chart">{query_chart}</div>
  <div class="chart">{table_chart}</div>
  <div class="chart">{scatter}</div>

  <section class="panel note">
    <h2>How The Test Was Conducted</h2>
    <ol>
      <li>Started a fresh local MySQL 8.4 instance with Performance Schema and slow query logging enabled.</li>
      <li>Installed WordPress {html.escape(str(versions.get('wordpress', '')))} and WooCommerce {html.escape(str(versions.get('woocommerce', '')))}.</li>
      <li>Enabled HPOS as the authoritative order store, disabled HPOS compatibility sync, disabled WP-Cron, disabled WooCommerce nonessential admin/task-list features, enabled guest checkout, and used relaxed MySQL durability settings for speed.</li>
      <li>Generated products, customers, {fmt_num(fixture.get('orders'), 0)} historical HPOS orders, order items, order addresses, and order stats, then inserted high-entropy HPOS order meta until the schema directory reached the 5GB target.</li>
      <li>Ran catalog, storefront/cart/checkout, admin-order, and checkout-heavy mixes at {', '.join(str(value) for value in manifest.get('concurrency', []))} concurrent requests for {fmt_num(manifest.get('duration_seconds'), 0)}s per cell after warm-up.</li>
    </ol>
  </section>

  <h2>Slowest Customer Routes</h2>
  <div class="wide"><table>
    <thead><tr><th>Route</th><th>Requests</th><th>Avg wall</th><th>p95 wall</th><th>Max wall</th><th>Avg DB</th><th>Avg queries</th></tr></thead>
    <tbody>{route_table(customer_routes)}</tbody>
  </table></div>

  <h2>Slowest Admin Routes</h2>
  <div class="wide"><table>
    <thead><tr><th>Route</th><th>Requests</th><th>Avg wall</th><th>p95 wall</th><th>Max wall</th><th>Avg DB</th><th>Avg queries</th></tr></thead>
    <tbody>{route_table(admin_routes)}</tbody>
  </table></div>

  <h2>Query Hotspots</h2>
  <div class="wide"><table>
    <thead><tr><th>Query group</th><th>Count</th><th>Total MySQL time</th><th>Max</th><th>Rows examined</th><th>Digest sample</th></tr></thead>
    <tbody>{digest_table(digests[:18])}</tbody>
  </table></div>

  <h2>What Would Make It Faster</h2>
  <div class="cols">
    <section class="panel">
      <h3>Order Admin Search</h3>
      <ul>
        <li>Avoid the broad HPOS order search query that ORs across transaction ID, billing email, HPOS meta, and order item name with <code>LIKE</code>.</li>
        <li>Dispatch by search shape: numeric order IDs should become direct ID lookups; email-like values should use exact or prefix email lookups; transaction IDs should use exact or prefix lookups.</li>
        <li>Move fuzzy order search to a dedicated search index table or external search service. Keep bounded, indexed columns for order number, billing email, transaction ID, customer names, and selected searchable meta.</li>
        <li>Put minimum-length, debounce, and cancellation behavior in the admin UI so broad searches do not leave long PHP/MySQL requests running.</li>
      </ul>
    </section>
    <section class="panel">
      <h3>Order Counts And Admin Lists</h3>
      <ul>
        <li>Cache or maintain order status counts instead of repeatedly counting the whole HPOS order table for admin menu/list badges.</li>
        <li>Keep default order list queries bounded by indexed date/status columns and avoid joining or scanning order meta unless the active filter requires it.</li>
        <li>Consider archival or partitioning strategies for old order/meta rows on very large stores, especially when admin workflows rarely need the entire history inline.</li>
      </ul>
    </section>
    <section class="panel">
      <h3>Checkout And Customer Routes</h3>
      <ul>
        <li>Checkout AJAX averaged about {fmt_num(worst_customer['avg_queries'])} queries/request for the slowest customer route; reduce repeated option, session, postmeta, and order-meta work on checkout submission.</li>
        <li>Use a persistent object cache in production. This run intentionally had no persistent object cache, which makes repeated options and metadata loads visible.</li>
        <li>Offload emails, Action Scheduler work, analytics, and nonessential post-checkout work out of the request path.</li>
      </ul>
    </section>
    <section class="panel">
      <h3>MySQL And Data Shape</h3>
      <ul>
        <li>The test used a 1.5GB InnoDB buffer pool against a 5GB schema; a production store should size the buffer pool closer to the hot working set.</li>
        <li>Keep arbitrary HPOS order meta from becoming the search surface. Large unbounded <code>meta_value</code> rows make useful indexes difficult and amplify I/O.</li>
        <li>After fixing the query shape, rerun without profiling overhead such as <code>SAVEQUERIES</code>, slow-query logging, and Performance Schema consumers to confirm production impact.</li>
      </ul>
    </section>
  </div>

  <h2>Artifacts</h2>
  <p>Data files: <a href="route-summary.csv">route-summary.csv</a>, <a href="query-digests.csv">query-digests.csv</a>, <a href="table-io.csv">table-io.csv</a>, <a href="aggregate.csv">aggregate.csv</a>, <a href="results.csv">results.csv</a>, <a href="manifest.json">manifest.json</a>, <a href="findings.json">findings.json</a>.</p>
  <p>Source run: <code>{html.escape(str(RUN_DIR))}</code>.</p>
</main>
</body>
</html>
"""
    write_text(OUT_DIR / "index.html", html_text)
    write_text(
        OUT_DIR / "README.md",
        "# WooCommerce HPOS MySQL Large Store Profile\n\n"
        "Visual report generated from the local WooCommerce HPOS MySQL profiling run.\n\n"
        "- Report: index.html\n"
        "- Route summary: route-summary.csv\n"
        "- Query digests: query-digests.csv\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
