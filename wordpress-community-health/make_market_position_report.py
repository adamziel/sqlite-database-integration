#!/usr/bin/env python3
import html
import math
import sqlite3
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
OUT = ROOT / "market_position.html"

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


def one(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else 0


def rows(conn, sql, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def latest(rows_, key="date"):
    if not rows_:
        return {}
    return max(rows_, key=lambda row: row.get(key, ""))


def nav_html():
    return "\n".join(
        [
            '    <nav class="nav">',
            '      <a href="index.html#market">Market Position</a>',
            '      <a href="index.html#decision-questions">Decision Questions</a>',
            '      <a href="project_load.html">Project load</a>',
            '      <a href="developer_interest.html">Developer interest</a>',
            '      <a href="job_demand.html">Job demand</a>',
            '      <a href="support_load.html">Support load</a>',
            '      <a href="ecosystem_activity.html">Ecosystem activity</a>',
            '      <a href="contributor_depth.html">Contributor depth</a>',
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


def horizontal_bar(label, value, max_value=100, color=COLORS["blue"], suffix="%"):
    value = num(value)
    width = 100 if max_value <= 0 else max(2, min(100, value / max_value * 100))
    shown = f"{value:.1f}{suffix}" if suffix else compact(value)
    return f"""
        <div class="barline">
          <div class="bar-label"><span>{esc(label)}</span><strong>{esc(shown)}</strong></div>
          <div class="bar"><span style="width:{width:.1f}%;background:{esc(color)}"></span></div>
        </div>"""


def line_chart(title, points, color=COLORS["blue"], suffix="%"):
    points = [(str(label), num(value)) for label, value in points if value is not None]
    if not points:
        return ""
    width, height = 520, 168
    left, right, top, bottom = 44, 20, 34, 34
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [value for _label, value in points]
    y_min = 0
    y_max = max(values) if values else 1
    if y_max == y_min:
        y_max = y_min + 1
    y_top = y_max + max(1, y_max * 0.1)
    y_bottom = y_min

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
        pieces.append(f'<text x="{left - 8}" y="{yy + 4:.1f}" class="axis" text-anchor="end">{tick:.1f}{esc(suffix)}</text>')
    pieces.append(f'<path d="{path}" fill="none" stroke="{esc(color)}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />')
    pieces.append(f'<circle cx="{x(len(points) - 1):.1f}" cy="{y(last_value):.1f}" r="4" fill="{esc(color)}" />')
    pieces.append(f'<text x="{left}" y="{height - 10}" class="axis">{esc(points[0][0])}</text>')
    pieces.append(f'<text x="{width - right}" y="{height - 10}" class="axis" text-anchor="end">{esc(last_label)}</text>')
    pieces.append(f'<text x="{width - right}" y="21" class="spark-end" text-anchor="end">{last_value:.1f}{esc(suffix)}</text>')
    pieces.append("</svg>")
    return "\n".join(pieces)


def signal_row(title, text, value, color="blue"):
    return f"""
        <div class="signal-row {esc(color)}">
          <div>
            <strong>{esc(title)}</strong>
            <span>{esc(text)}</span>
          </div>
          <b>{esc(value)}</b>
        </div>"""


def points_for_market(market_rows, metric, technology):
    out = []
    for row in sorted(market_rows, key=lambda item: item.get("date", "")):
        if row.get("metric") == metric and row.get("technology") == technology:
            label = row.get("date", "")[:4]
            if row.get("date", "") == "2026-06-14":
                label = "2026 now"
            out.append((label, row.get("value")))
    return out


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        integrity = one(conn, "PRAGMA integrity_check")
        market_rows = rows(conn, "SELECT * FROM market_share ORDER BY date")
        choice_rows = rows(conn, "SELECT * FROM new_site_choice_summary ORDER BY signal")
        attention_rows = rows(conn, "SELECT * FROM attention_demand_summary ORDER BY signal")
        tier_rows = rows(conn, "SELECT * FROM builtwith_tier_share_snapshot ORDER BY CAST(tier_order AS INTEGER)")
        builtwith_new = rows(conn, "SELECT * FROM builtwith_new_site_snapshot ORDER BY technology")
        http_rows = rows(
            conn,
            """
            SELECT date, technology, total_tracked_share_pct
            FROM http_archive_tracked_share_monthly
            WHERE technology IN ('WordPress', 'Shopify', 'Wix')
            ORDER BY date
            """,
        )
        plugin_rows = rows(conn, "SELECT * FROM major_plugin_install_snapshot")
        vip_rows = rows(conn, "SELECT * FROM enterprise_vip_case_studies")
    finally:
        conn.close()

    latest_all_wp = latest([row for row in market_rows if row.get("metric") == "all_sites_usage" and row.get("technology") == "WordPress"])
    latest_cms_wp = latest([row for row in market_rows if row.get("metric") == "cms_market_share" and row.get("technology") == "WordPress"])
    wp_2025_all = next((row for row in market_rows if row.get("metric") == "all_sites_usage" and row.get("technology") == "WordPress" and row.get("date") == "2025-01-01"), {})
    wp_2025_cms = next((row for row in market_rows if row.get("metric") == "cms_market_share" and row.get("technology") == "WordPress" and row.get("date") == "2025-01-01"), {})
    all_delta = num(latest_all_wp.get("value")) - num(wp_2025_all.get("value"))
    cms_delta = num(latest_cms_wp.get("value")) - num(wp_2025_cms.get("value"))

    choice_by_signal = {row.get("signal"): row for row in choice_rows}
    builtwith_90 = choice_by_signal.get("builtwith_90_day_pipeline", {})
    builtwith_30 = choice_by_signal.get("builtwith_30_day_pipeline", {})
    http_latest = choice_by_signal.get("http_archive_latest_tracked_share", {})
    http_change = choice_by_signal.get("http_archive_tracked_share_change", {})
    top_1m = choice_by_signal.get("builtwith_top_1m_tracked_share", {})
    long_tail = choice_by_signal.get("builtwith_long_tail_tracked_share", {})

    builtwith_by_tech = {row.get("technology"): row for row in builtwith_new}
    total_major_plugin_installs = sum(num(row.get("active_installs")) for row in plugin_rows)

    http_wp_points = [
        (row.get("date", "")[:7], row.get("total_tracked_share_pct"))
        for row in http_rows
        if row.get("technology") == "WordPress"
    ][-36:]

    metrics = "".join(
        [
            metric_card("All-site share", pct(latest_all_wp.get("value")), f"W3Techs, {all_delta:+.1f} pts since Jan 2025", "blue"),
            metric_card("CMS share", pct(latest_cms_wp.get("value")), f"W3Techs, {cms_delta:+.1f} pts since Jan 2025", "blue"),
            metric_card("90-day new-site proxy", pct(builtwith_90.get("wordpress_share_pct")), f"BuiltWith tracked pipeline, {compact(builtwith_90.get('wordpress_value'))} WordPress sites", "green"),
            metric_card("HTTP tracked share", pct(http_latest.get("wordpress_share_pct")), f"{num(http_change.get('wordpress_value')):+.1f} pts since 2020-01-01", "green"),
            metric_card("Top 1M tracked share", pct(top_1m.get("wordpress_share_pct")), "BuiltWith current traffic-tier snapshot", "violet"),
            metric_card("Long-tail tracked share", pct(long_tail.get("wordpress_share_pct")), "BuiltWith current outside-Top-1M snapshot", "violet"),
            metric_card("Major plugin installs", compact(total_major_plugin_installs), "Fixed major-plugin WordPress.org API sample", "amber"),
            metric_card("Enterprise cases", compact(len(vip_rows)), "Current WordPress VIP case-study snapshot", "amber"),
        ]
    )

    lane_rows = "".join(
        [
            signal_row("Installed share", f"W3Techs has WordPress at {pct(latest_all_wp.get('value'))} of all sites and {pct(latest_cms_wp.get('value'))} of CMS sites.", "Still first", "blue"),
            signal_row("Recent direction", f"All-site share moved {all_delta:+.1f} pts and CMS share moved {cms_delta:+.1f} pts since Jan 2025.", "Softer", "amber"),
            signal_row("Current new-site proxy", f"BuiltWith 90-day tracked pipeline: WordPress to {builtwith_90.get('next_peer', 'next peer')} ratio is {num(builtwith_90.get('wordpress_to_next_peer_ratio')):.2f}x.", pct(builtwith_90.get("wordpress_share_pct")), "green"),
            signal_row("Recurring crawl share", f"HTTP Archive tracked share latest month; peer set is WordPress, Shopify, Wix, Squarespace, and Webflow.", pct(http_latest.get("wordpress_share_pct")), "green"),
            signal_row("Traffic tier", f"BuiltWith current Top 1M and long-tail tracked shares bracket where WordPress appears across site sizes.", f"{pct(top_1m.get('wordpress_share_pct'))} / {pct(long_tail.get('wordpress_share_pct'))}", "violet"),
            signal_row("Attention and demand", "All available public/developer/hiring proxy summaries are lower than their baselines.", "Lower", "amber"),
        ]
    )

    new_site_rows = sorted(
        [row for row in builtwith_new if row.get("new_last_3_months") not in (None, "")],
        key=lambda row: num(row.get("new_last_3_months")),
        reverse=True,
    )
    new_site_max = max([num(row.get("new_last_3_months")) for row in new_site_rows] or [1])
    new_site_bars = "".join(
        horizontal_bar(
            row.get("technology"),
            row.get("new_last_3_months") or 0,
            new_site_max,
            COLORS["green"] if row.get("technology") == "WordPress" else COLORS["ink"],
            suffix="",
        )
        for row in new_site_rows
    )

    tier_bars = "".join(
        horizontal_bar(row.get("label"), row.get("wordpress_share_pct"), 100, COLORS["violet"])
        for row in tier_rows
    )

    attention_list = "".join(
        signal_row(
            row.get("label"),
            f"{row.get('latest_period')} vs {row.get('baseline_period')} ({row.get('unit')})",
            f"{num(row.get('change_pct')):+.1f}%",
            "amber",
        )
        for row in attention_rows
    )

    charts = "\n".join(
        [
            line_chart("W3Techs all-site share", points_for_market(market_rows, "all_sites_usage", "WordPress"), COLORS["blue"]),
            line_chart("W3Techs CMS share", points_for_market(market_rows, "cms_market_share", "WordPress"), COLORS["blue"]),
            line_chart("HTTP Archive tracked share", http_wp_points, COLORS["green"]),
        ]
    )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress Market Position</title>
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
    .metric, .section, .signal-panel {{
      background:var(--panel);
      border:1px solid var(--line);
      border-radius:8px;
      box-shadow:0 1px 2px rgba(15,23,42,.04);
    }}
    .metric {{ padding:16px; border-top:5px solid var(--blue); }}
    .metric.green {{ border-top-color:var(--green); }}
    .metric.amber {{ border-top-color:var(--amber); }}
    .metric.violet {{ border-top-color:var(--violet); }}
    .metric strong {{ display:block; font-size:31px; line-height:1; margin:5px 0 7px; }}
    .metric p, .note {{ color:var(--muted); font-size:14px; }}
    .grid {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:14px; align-items:start; }}
    .section, .signal-panel {{ padding:18px; }}
    .signals {{ display:grid; gap:9px; }}
    .signal-row {{ display:flex; justify-content:space-between; gap:14px; align-items:center; border-left:5px solid var(--blue); background:#fbfdff; border-radius:8px; padding:12px; }}
    .signal-row.green {{ border-left-color:var(--green); }}
    .signal-row.amber {{ border-left-color:var(--amber); }}
    .signal-row.violet {{ border-left-color:var(--violet); }}
    .signal-row strong, .signal-row span {{ display:block; }}
    .signal-row span {{ color:var(--muted); font-size:13px; }}
    .signal-row b {{ font-size:20px; white-space:nowrap; }}
    .charts {{ display:grid; gap:12px; }}
    .spark {{ width:100%; height:auto; display:block; background:#fbfdff; border:1px solid var(--line); border-radius:8px; padding:4px; }}
    .spark-title {{ font-size:16px; font-weight:750; fill:var(--ink); }}
    .spark-end {{ font-size:13px; font-weight:800; fill:var(--ink); }}
    .axis {{ font-size:11px; fill:var(--muted); }}
    .spark-grid {{ stroke:#e8eef5; stroke-width:1; }}
    .bar-stack {{ display:grid; gap:10px; margin-top:12px; }}
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
    <h1>WordPress market position</h1>
    <p class="lede">A compact readout of whether WordPress is still widely chosen: installed share, current newly found-site proxy, traffic-tier presence, demand proxies, plugin reach, and enterprise signal.</p>
{nav_html()}

    <section class="metrics" aria-label="Market position summary">
{metrics}
    </section>

    <section class="grid">
      <div class="signal-panel">
        <h2>Decision lanes</h2>
        <p class="note">These lanes separate measured installed share from current new-site and demand proxies.</p>
        <div class="signals">{lane_rows}</div>
      </div>
      <div class="section">
        <h2>Installed-share trend</h2>
        <div class="charts">{charts}</div>
      </div>
    </section>

    <section class="grid" style="margin-top:14px">
      <div class="section">
        <h2>Current new-site proxy</h2>
        <p class="note">BuiltWith public Net New Pipeline counts for the last 90 days where available.</p>
        <div class="bar-stack">{new_site_bars}</div>
      </div>
      <div class="section">
        <h2>Traffic-tier presence</h2>
        <p class="note">BuiltWith current tracked share among WordPress, Shopify, Wix, Squarespace, and Webflow.</p>
        <div class="bar-stack">{tier_bars}</div>
      </div>
    </section>

    <section class="grid" style="margin-top:14px">
      <div class="section">
        <h2>Attention and demand proxy direction</h2>
        <p class="note">These are directional public proxies, not Google Trends or a broad labor-market export.</p>
        <div class="signals">{attention_list}</div>
      </div>
      <div class="section">
        <h2>How to read this</h2>
        <div class="readout">
          <div><strong>Still widely chosen.</strong><span>Installed-share evidence remains much stronger than any peer CMS or builder signal.</span></div>
          <div><strong>Recent share is softer.</strong><span>W3Techs and HTTP Archive show WordPress still leading while its share is lower than recent baselines.</span></div>
          <div><strong>New-site history is partial.</strong><span>BuiltWith and HTTP Archive are useful current proxies; the source gap plan covers the ideal cohort source.</span></div>
        </div>
        <p class="footer-note">Rows come from existing SQLite tables including <code>market_share</code>, <code>new_site_choice_summary</code>, <code>http_archive_tracked_share_monthly</code>, <code>builtwith_tier_share_snapshot</code>, <code>builtwith_new_site_snapshot</code>, and <code>attention_demand_summary</code>. Integrity check: <code>{esc(integrity)}</code>.</p>
      </div>
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
