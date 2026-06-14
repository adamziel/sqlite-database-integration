#!/usr/bin/env python3
import html
import sqlite3
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
OUT = ROOT / "project_load.html"

COLORS = {
    "blue": "#2563eb",
    "green": "#159957",
    "amber": "#b7791f",
    "violet": "#7c3aed",
    "ink": "#172033",
}


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def num(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def compact(value):
    value = int(round(num(value)))
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{value / 1_000:.1f}k"
    return f"{value:,}"


def pct(value):
    return f"{num(value):.1f}%"


def hours(value):
    return f"{num(value):.1f}h"


def days(value):
    return f"{num(value):.1f}d"


def one(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else 0


def rows(conn, sql, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def latest(rows_, key="quarter"):
    if not rows_:
        return {}
    return max(rows_, key=lambda row: row.get(key, ""))


def quarter_label(value):
    if not value:
        return ""
    try:
        year = value[:4]
        month = int(value[5:7])
        return f"{year} Q{((month - 1) // 3) + 1}"
    except (TypeError, ValueError):
        return str(value)


def nav_html():
    return "\n".join(
        [
            '    <nav class="nav">',
            '      <a href="index.html#load">Project Load</a>',
            '      <a href="index.html#decision-questions">Decision Questions</a>',
            '      <a href="market_position.html">Market position</a>',
            '      <a href="new_site_choice.html">New-site choice</a>',
            '      <a href="search_interest.html">Search interest</a>',
            '      <a href="developer_interest.html">Developer interest</a>',
            '      <a href="job_demand.html">Job demand</a>',
            '      <a href="support_load.html">Support load</a>',
            '      <a href="contributor_depth.html">Contributor depth</a>',
            '      <a href="ecosystem_activity.html">Ecosystem activity</a>',
            '      <a href="progress_summary.html">Progress summary</a>',
            '      <a href="decision_brief.html">Decision brief</a>',
            '      <a href="goal_audit.html">Goal audit</a>',
            '      <a href="data_inventory.html">Data inventory</a>',
            '      <a href="source_gap_plan.html">Source gap plan</a>',
            '      <a href="refresh_runbook.html">Refresh runbook</a>',
            "    </nav>",
        ]
    )


def metric_card(label, value, note, color="blue"):
    return f"""
      <article class="metric {esc(color)}">
        <h3>{esc(label)}</h3>
        <strong>{esc(value)}</strong>
        <p>{esc(note)}</p>
      </article>"""


def signal_row(title, text, value, color="blue"):
    return f"""
        <div class="signal-row {esc(color)}">
          <div>
            <strong>{esc(title)}</strong>
            <span>{esc(text)}</span>
          </div>
          <b>{esc(value)}</b>
        </div>"""


def horizontal_bar(label, value, max_value=100, color=COLORS["blue"], suffix="%"):
    value = num(value)
    width = 100 if max_value <= 0 else max(2, min(100, value / max_value * 100))
    shown = f"{value:.1f}{suffix}" if suffix else compact(value)
    return f"""
        <div class="barline">
          <div class="bar-label"><span>{esc(label)}</span><strong>{esc(shown)}</strong></div>
          <div class="bar"><span style="width:{width:.1f}%;background:{esc(color)}"></span></div>
        </div>"""


def line_chart(title, points, color=COLORS["blue"], suffix=""):
    points = [(str(label), num(value)) for label, value in points if value is not None]
    if not points:
        return ""
    width, height = 520, 168
    left, right, top, bottom = 48, 20, 34, 34
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [value for _label, value in points]
    y_min = min(0, min(values))
    y_max = max(values) if values else 1
    if y_max == y_min:
        y_max = y_min + 1
    spread = y_max - y_min
    y_top = y_max + max(1, spread * 0.1)
    y_bottom = y_min - (spread * 0.1 if y_min < 0 else 0)

    def x(index):
        if len(points) == 1:
            return left + plot_w
        return left + index / (len(points) - 1) * plot_w

    def y(value):
        return top + (1 - ((value - y_bottom) / (y_top - y_bottom))) * plot_h

    path = " ".join(("M" if i == 0 else "L") + f"{x(i):.1f},{y(value):.1f}" for i, (_label, value) in enumerate(points))
    last_label, last_value = points[-1]
    ticks = [y_bottom, (y_bottom + y_top) / 2, y_top]
    pieces = [
        f'<svg class="spark" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        f'<text x="{left}" y="20" class="spark-title">{esc(title)}</text>',
    ]
    for tick in ticks:
        yy = y(tick)
        pieces.append(f'<line x1="{left}" x2="{width - right}" y1="{yy:.1f}" y2="{yy:.1f}" class="spark-grid" />')
        pieces.append(f'<text x="{left - 8}" y="{yy + 4:.1f}" class="axis" text-anchor="end">{tick:.0f}{esc(suffix)}</text>')
    pieces.append(f'<path d="{path}" fill="none" stroke="{esc(color)}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />')
    pieces.append(f'<circle cx="{x(len(points) - 1):.1f}" cy="{y(last_value):.1f}" r="4" fill="{esc(color)}" />')
    pieces.append(f'<text x="{left}" y="{height - 10}" class="axis">{esc(points[0][0])}</text>')
    pieces.append(f'<text x="{width - right}" y="{height - 10}" class="axis" text-anchor="end">{esc(last_label)}</text>')
    pieces.append(f'<text x="{width - right}" y="21" class="spark-end" text-anchor="end">{last_value:.0f}{esc(suffix)}</text>')
    pieces.append("</svg>")
    return "\n".join(pieces)


def closure_ratio(rows_, created_key, closed_key, start="2024-01-01"):
    created = sum(num(row.get(created_key)) for row in rows_ if row.get("quarter", "") >= start)
    closed = sum(num(row.get(closed_key)) for row in rows_ if row.get("quarter", "") >= start)
    return closed / created * 100 if created else 0


def age_share(age_rows, source, buckets):
    source_rows = [row for row in age_rows if row.get("source") == source and row.get("age_bucket") in buckets]
    if not source_rows:
        return 0
    total = num(source_rows[0].get("open_total")) or sum(num(row.get("open_count")) for row in source_rows)
    count = sum(num(row.get("open_count")) for row in source_rows)
    return count / total * 100 if total else 0


def open_total(age_rows, source):
    row = next((item for item in age_rows if item.get("source") == source), {})
    return num(row.get("open_total"))


def top_categories(category_rows, source, limit=5):
    source_rows = [row for row in category_rows if row.get("source") == source]
    return sorted(source_rows, key=lambda row: num(row.get("open_count")), reverse=True)[:limit]


def flow_points(rows_, value_key, count=14):
    return [(quarter_label(row.get("quarter")), row.get(value_key)) for row in rows_[-count:]]


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        integrity = one(conn, "PRAGMA integrity_check")
        core_q = rows(conn, "SELECT * FROM core_quarterly ORDER BY quarter")
        gut_q = rows(conn, "SELECT * FROM gutenberg_quarterly ORDER BY quarter")
        core_response = rows(conn, "SELECT * FROM core_response_quarterly ORDER BY quarter")
        gut_timeline = rows(conn, "SELECT * FROM gutenberg_timeline_quarterly ORDER BY quarter")
        closure_age = rows(conn, "SELECT * FROM closure_age_summary ORDER BY quarter")
        core_reopen = rows(conn, "SELECT * FROM core_reopen_quarterly ORDER BY quarter")
        open_age = rows(conn, "SELECT * FROM open_backlog_age_summary ORDER BY source, CAST(bucket_order AS INTEGER)")
        category_rows = rows(conn, "SELECT * FROM category_open_backlog_summary ORDER BY source, open_count DESC")
    finally:
        conn.close()

    latest_core = latest(core_q)
    latest_gut = latest(gut_q)
    latest_core_response = latest(core_response)
    latest_gut_timeline = latest(gut_timeline)
    latest_core_reopen = latest(core_reopen)
    core_closure_latest = latest([row for row in closure_age if row.get("source") == "Core"])
    gut_closure_latest = latest([row for row in closure_age if row.get("source") == "Gutenberg"])
    core_ratio = closure_ratio(core_q, "created", "closed")
    gut_ratio = closure_ratio(gut_q, "created", "closed")
    core_stale = age_share(open_age, "Core", {"1-2 years", "2-5 years", "5+ years"})
    gut_stale = age_share(open_age, "Gutenberg", {"1-2 years", "2-5 years", "5+ years"})
    core_2y = age_share(open_age, "Core", {"2-5 years", "5+ years"})
    gut_2y = age_share(open_age, "Gutenberg", {"2-5 years", "5+ years"})

    metrics = "".join(
        [
            metric_card("Core closure balance", pct(core_ratio), "closed / opened since 2024", "green" if core_ratio >= 100 else "amber"),
            metric_card("Gutenberg closure balance", pct(gut_ratio), "closed / opened since 2024", "green" if gut_ratio >= 100 else "amber"),
            metric_card("Core open backlog", compact(latest_core.get("open_at_end")), f"latest quarter {latest_core.get('label', '')}", "blue"),
            metric_card("Gutenberg open backlog", compact(latest_gut.get("open_at_end")), f"latest quarter {quarter_label(latest_gut.get('quarter'))}", "blue"),
            metric_card("Core 1+ year open share", pct(core_stale), f"{pct(core_2y)} is 2+ years since activity", "amber"),
            metric_card("Gutenberg 1+ year open share", pct(gut_stale), f"{pct(gut_2y)} is 2+ years since activity", "amber"),
            metric_card("Core first response", hours(latest_core_response.get("median_first_non_reporter_activity_hours")), f"{latest_core_response.get('coverage_percent', 'n/a')}% RSS coverage", "green"),
            metric_card("Gutenberg first response", hours(latest_gut_timeline.get("median_first_non_author_response_hours")), "median first non-author response", "green"),
        ]
    )

    lane_rows = "".join(
        [
            signal_row("Keeping up?", f"Since 2024 closure ratios are Core {pct(core_ratio)} and Gutenberg {pct(gut_ratio)}.", "Mostly", "green"),
            signal_row("Latest quarter flow", f"Core net {compact(latest_core.get('net'))}; Gutenberg net {compact(latest_gut.get('net_created_minus_closed'))}.", "Mixed", "amber"),
            signal_row("Backlog age", f"Open share with 1+ year since activity is Core {pct(core_stale)} and Gutenberg {pct(gut_stale)}.", "Aged", "amber"),
            signal_row("Response time", f"Latest medians: Core {hours(latest_core_response.get('median_first_non_reporter_activity_hours'))}, Gutenberg {hours(latest_gut_timeline.get('median_first_non_author_response_hours'))}.", "Hours", "green"),
            signal_row("Closure time", f"Latest median days to close: Core {days(core_closure_latest.get('median_days_to_close'))}, Gutenberg {days(gut_closure_latest.get('median_days_to_close'))}.", "Uneven", "violet"),
            signal_row("Reopened flow", f"Latest Core reopened events per 100 closed: {num(latest_core_reopen.get('reopened_events_per_100_closed')):.1f}. Gutenberg latest: {num(latest_gut_timeline.get('reopened_events_per_100_closed')):.1f}.", "Watch", "amber"),
        ]
    )

    charts = "\n".join(
        [
            line_chart("Core open backlog by quarter", flow_points(core_q, "open_at_end"), COLORS["blue"]),
            line_chart("Gutenberg open backlog by quarter", flow_points(gut_q, "open_at_end"), COLORS["violet"]),
            line_chart("Core net flow", flow_points(core_q, "net"), COLORS["green"]),
            line_chart("Gutenberg net flow", flow_points(gut_q, "net_created_minus_closed"), COLORS["green"]),
        ]
    )

    core_category_bars = "".join(
        horizontal_bar(row.get("category"), row.get("open_count"), open_total(open_age, "Core"), COLORS["blue"], suffix="")
        for row in top_categories(category_rows, "Core")
    )
    gut_category_bars = "".join(
        horizontal_bar(row.get("category"), row.get("open_count"), open_total(open_age, "Gutenberg"), COLORS["violet"], suffix="")
        for row in top_categories(category_rows, "Gutenberg")
    )
    core_age_bars = "".join(
        horizontal_bar(row.get("age_bucket"), row.get("open_share_pct"), 100, COLORS["amber"])
        for row in open_age
        if row.get("source") == "Core" and row.get("age_bucket") != "unknown"
    )
    gut_age_bars = "".join(
        horizontal_bar(row.get("age_bucket"), row.get("open_share_pct"), 100, COLORS["amber"])
        for row in open_age
        if row.get("source") == "Gutenberg" and row.get("age_bucket") != "unknown"
    )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress Project Load</title>
  <style>
    :root {{
      color-scheme: light;
      --ink:#172033;
      --muted:#637083;
      --line:#d9e1ea;
      --paper:#f6f8fb;
      --panel:#fff;
      --blue:#2563eb;
      --green:#159957;
      --amber:#b7791f;
      --violet:#7c3aed;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--paper); color:var(--ink); font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    main {{ max-width:1180px; margin:0 auto; padding:36px 22px 48px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(32px,4vw,52px); line-height:1.05; letter-spacing:0; }}
    h2 {{ margin:0 0 12px; font-size:23px; line-height:1.15; letter-spacing:0; }}
    h3 {{ margin:0 0 8px; font-size:12px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }}
    p {{ margin:0; }}
    a {{ color:var(--blue); }}
    code {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:13px; overflow-wrap:anywhere; }}
    .lede {{ max-width:920px; color:var(--muted); font-size:18px; margin-bottom:18px; }}
    .nav {{ display:flex; flex-wrap:wrap; gap:8px; margin:18px 0 22px; }}
    .nav a {{ border:1px solid var(--line); border-radius:999px; padding:7px 11px; background:#fbfdff; color:var(--muted); font-size:13px; text-decoration:none; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin:22px 0; }}
    .metric, .section, .signal-panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; box-shadow:0 1px 2px rgba(15,23,42,.04); }}
    .metric {{ padding:16px; border-top:5px solid var(--blue); }}
    .metric.green {{ border-top-color:var(--green); }}
    .metric.amber {{ border-top-color:var(--amber); }}
    .metric.violet {{ border-top-color:var(--violet); }}
    .metric strong {{ display:block; font-size:31px; line-height:1; margin:5px 0 7px; }}
    .metric p, .note {{ color:var(--muted); font-size:14px; }}
    .grid {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:14px; align-items:start; }}
    .section, .signal-panel {{ padding:18px; }}
    .signals, .bar-stack, .charts {{ display:grid; gap:10px; }}
    .signal-row {{ display:flex; justify-content:space-between; gap:14px; align-items:center; border-left:5px solid var(--blue); background:#fbfdff; border-radius:8px; padding:12px; }}
    .signal-row.green {{ border-left-color:var(--green); }}
    .signal-row.amber {{ border-left-color:var(--amber); }}
    .signal-row.violet {{ border-left-color:var(--violet); }}
    .signal-row strong, .signal-row span {{ display:block; }}
    .signal-row span {{ color:var(--muted); font-size:13px; }}
    .signal-row b {{ font-size:20px; white-space:nowrap; }}
    .spark {{ width:100%; height:auto; display:block; background:#fbfdff; border:1px solid var(--line); border-radius:8px; padding:4px; }}
    .spark-title {{ font-size:16px; font-weight:750; fill:var(--ink); }}
    .spark-end {{ font-size:13px; font-weight:800; fill:var(--ink); }}
    .axis {{ font-size:11px; fill:var(--muted); }}
    .spark-grid {{ stroke:#e8eef5; stroke-width:1; }}
    .bar-label {{ display:flex; justify-content:space-between; gap:8px; font-size:13px; margin-bottom:4px; }}
    .bar-label span {{ color:var(--muted); }}
    .bar-label strong {{ white-space:nowrap; }}
    .bar {{ height:9px; border-radius:999px; background:#e8eef5; overflow:hidden; }}
    .bar span {{ display:block; height:100%; border-radius:inherit; }}
    .readout {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin-top:14px; }}
    .readout div {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:#fbfdff; }}
    .readout strong {{ display:block; margin-bottom:5px; }}
    .readout span {{ color:var(--muted); font-size:14px; }}
    .footer-note {{ margin-top:14px; background:#eef4ff; border:1px solid #cfe0ff; border-radius:8px; padding:14px 16px; color:#244067; }}
    @media (max-width:980px) {{
      .metrics {{ grid-template-columns:1fr 1fr; }}
      .grid, .readout {{ grid-template-columns:1fr; }}
    }}
    @media (max-width:640px) {{
      main {{ padding:24px 14px 36px; }}
      .metrics {{ grid-template-columns:1fr; }}
      .signal-row {{ display:block; }}
      .signal-row b {{ display:block; margin-top:5px; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>WordPress project load</h1>
    <p class="lede">A compact workload readout for Core Trac and Gutenberg: incoming work, closures, net flow, backlog size, stale open work, response time, closure time, reopen flow, and bug/feature mix.</p>
{nav_html()}

    <section class="metrics" aria-label="Project load summary">
{metrics}
    </section>

    <section class="grid">
      <div class="signal-panel">
        <h2>Decision lanes</h2>
        <p class="note">This keeps workload separate from overall participation and market demand.</p>
        <div class="signals">{lane_rows}</div>
      </div>
      <div class="section">
        <h2>Recent workload shape</h2>
        <div class="charts">{charts}</div>
      </div>
    </section>

    <section class="grid" style="margin-top:14px">
      <div class="section">
        <h2>Open backlog age</h2>
        <p class="note">Current open items bucketed by time since last activity or update.</p>
        <div class="bar-stack">{core_age_bars}</div>
        <p class="note" style="margin:12px 0 8px">Gutenberg</p>
        <div class="bar-stack">{gut_age_bars}</div>
      </div>
      <div class="section">
        <h2>Open backlog by category</h2>
        <p class="note">Largest current open categories by source.</p>
        <div class="bar-stack">{core_category_bars}</div>
        <p class="note" style="margin:12px 0 8px">Gutenberg</p>
        <div class="bar-stack">{gut_category_bars}</div>
      </div>
    </section>

    <section class="section" style="margin-top:14px">
      <h2>How to read this</h2>
      <div class="readout">
        <div><strong>Flow is closer to balanced.</strong><span>Since 2024, Core closures slightly exceed new tickets on average; Gutenberg is near balanced and had a cleanup quarter in 2026 Q2.</span></div>
        <div><strong>The backlog is still aged.</strong><span>Most open Core and Gutenberg items have had no recent activity, so backlog size alone understates the age issue.</span></div>
        <div><strong>Response is measured in hours.</strong><span>Latest median first response is still fairly fast, even while closure age and backlog age remain uneven.</span></div>
      </div>
      <p class="footer-note">Rows come from existing SQLite tables including <code>core_quarterly</code>, <code>gutenberg_quarterly</code>, <code>core_response_quarterly</code>, <code>gutenberg_timeline_quarterly</code>, <code>closure_age_summary</code>, <code>core_reopen_quarterly</code>, <code>open_backlog_age_summary</code>, and <code>category_open_backlog_summary</code>. Integrity check: <code>{esc(integrity)}</code>.</p>
    </section>
  </main>
</body>
</html>
"""
    clean_doc = "\n".join(line.rstrip() for line in html_doc.splitlines()) + "\n"
    OUT.write_text(clean_doc, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
