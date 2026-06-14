#!/usr/bin/env python3
import html
import math
import sqlite3
from datetime import datetime
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
OUT = ROOT / "ecosystem_activity.html"


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


def latest(rows_, date_key):
    if not rows_:
        return {}
    return max(rows_, key=lambda row: row.get(date_key, ""))


def nav_html():
    return "\n".join(
        [
            '    <nav class="nav">',
            '      <a href="index.html#participation">Participation</a>',
            '      <a href="index.html#scorecard">Scorecard</a>',
            '      <a href="market_position.html">Market position</a>',
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


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def sparkline(title, points, color="#2563eb", suffix=""):
    points = [(str(label), num(value)) for label, value in points if value is not None]
    if not points:
        return ""
    width, height = 520, 168
    left, right, top, bottom = 44, 20, 34, 34
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [value for _label, value in points]
    y_max = max(values) if values else 1
    if y_max <= 0:
        y_max = 1
    y_top = math.ceil(y_max / 10) * 10 if y_max > 10 else y_max
    if y_top <= 0:
        y_top = 1

    def x(index):
        if len(points) == 1:
            return left + plot_w
        return left + index / (len(points) - 1) * plot_w

    def y(value):
        return top + (1 - value / y_top) * plot_h

    path = " ".join(("M" if i == 0 else "L") + f"{x(i):.1f},{y(value):.1f}" for i, (_label, value) in enumerate(points))
    last_label, last_value = points[-1]
    tick_values = [0, y_top / 2, y_top]
    pieces = [
        f'<svg class="spark" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        f'<text x="{left}" y="20" class="spark-title">{esc(title)}</text>',
    ]
    for tick in tick_values:
        yy = y(tick)
        pieces.append(f'<line x1="{left}" x2="{width - right}" y1="{yy:.1f}" y2="{yy:.1f}" class="spark-grid" />')
        pieces.append(f'<text x="{left - 8}" y="{yy + 4:.1f}" class="axis" text-anchor="end">{esc(compact(tick))}{esc(suffix)}</text>')
    pieces.append(f'<path d="{path}" fill="none" stroke="{esc(color)}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />')
    pieces.append(f'<circle cx="{x(len(points) - 1):.1f}" cy="{y(last_value):.1f}" r="4" fill="{esc(color)}" />')
    pieces.append(f'<text x="{left}" y="{height - 10}" class="axis">{esc(points[0][0])}</text>')
    pieces.append(f'<text x="{width - right}" y="{height - 10}" class="axis" text-anchor="end">{esc(last_label)}</text>')
    pieces.append(f'<text x="{width - right}" y="21" class="spark-end" text-anchor="end">{esc(compact(last_value))}{esc(suffix)}</text>')
    pieces.append("</svg>")
    return "\n".join(pieces)


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


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        integrity = one(conn, "PRAGMA integrity_check")
        wordcamp_yearly = rows(conn, "SELECT * FROM wordcamp_yearly ORDER BY year")
        make_comments = rows(conn, "SELECT * FROM make_core_comment_quarterly ORDER BY quarter")
        dev_notes = rows(conn, "SELECT * FROM make_core_dev_note_quarterly ORDER BY quarter")
        release_credits = rows(conn, "SELECT * FROM core_release_credits ORDER BY release_date")
        directory = rows(conn, "SELECT * FROM directory_snapshots")
        directory_activity = rows(conn, "SELECT * FROM directory_activity_snapshots")
        translation = rows(conn, "SELECT * FROM translation_snapshots")
        fttf = rows(conn, "SELECT * FROM fttf_snapshots")
        support = rows(conn, "SELECT * FROM support_forum_snapshot_summary")
        events = rows(conn, "SELECT * FROM wp_event_snapshots")
        plugin_maintenance = rows(conn, "SELECT * FROM plugin_maintenance_summary")
    finally:
        conn.close()

    latest_wc_full = max(
        [row for row in wordcamp_yearly if row.get("year", "") <= "2025-01-01"],
        key=lambda row: row.get("year", ""),
        default={},
    )
    latest_wc_any = latest(wordcamp_yearly, "year")
    latest_comments = latest(make_comments, "quarter")
    latest_dev_notes = latest(dev_notes, "quarter")
    latest_release = latest(release_credits, "release_date")
    latest_directory_activity = latest(directory_activity, "snapshot_date")
    latest_translation = latest(translation, "snapshot_date")
    latest_fttf = latest(fttf, "snapshot_date")
    latest_support = latest(support, "snapshot_at")
    latest_events = latest(events, "snapshot_date")
    latest_plugin_maintenance = latest(plugin_maintenance, "snapshot_date")

    directory_by_metric = {row.get("metric"): row for row in directory}
    plugin_count = directory_by_metric.get("plugin_directory_plugins", {}).get("value", 0)
    theme_count = directory_by_metric.get("theme_directory_themes", {}).get("value", 0)

    make_comment_points = [
        (row.get("quarter", "")[:4] + " Q" + str((int(row.get("quarter", "")[5:7] or 1) - 1) // 3 + 1), row.get("comments"))
        for row in make_comments[-14:]
        if row.get("quarter")
    ]
    dev_note_points = [
        (row.get("quarter", "")[:4] + " Q" + str((int(row.get("quarter", "")[5:7] or 1) - 1) // 3 + 1), row.get("dev_notes"))
        for row in dev_notes[-14:]
        if row.get("quarter")
    ]
    wordcamp_points = [(row.get("label") or row.get("year", "")[:4], row.get("events")) for row in wordcamp_yearly if row.get("year", "") <= "2025-01-01"][-12:]
    release_prop_points = [(row.get("version"), row.get("props_count")) for row in release_credits[-10:]]

    metric_html = "".join(
        [
            metric_card("Latest Core release props", compact(latest_release.get("props_count")), f"WordPress {latest_release.get('version', 'n/a')} credits API", "blue"),
            metric_card("Make/Core commenters", compact(latest_comments.get("unique_commenters")), f"Latest quarter: {latest_comments.get('label', '')}", "green"),
            metric_card("WordCamps in 2025", compact(latest_wc_full.get("events")), f"{compact(latest_wc_full.get('anticipated_attendance'))} anticipated attendance", "violet"),
            metric_card("Upcoming events", compact(latest_events.get("event_count")), f"{compact(latest_events.get('meetup_count'))} Meetups, {compact(latest_events.get('wordcamp_count'))} WordCamps", "green"),
            metric_card("Translation locales", compact(latest_translation.get("locale_count")), f"{compact(latest_translation.get('locale_contributor_profile_sum'))} contributor profiles", "blue"),
            metric_card("Five for the Future hours", compact(latest_fttf.get("pledged_hours_per_week")), f"{compact(latest_fttf.get('pledges_fetched'))} pledges fetched", "violet"),
            metric_card("Support topics sampled", compact(latest_support.get("topics")), f"{pct(latest_support.get('resolved_share_pct'))} resolved in current queue", "amber"),
            metric_card("Plugin directory", compact(plugin_count), f"{compact(theme_count)} themes also listed", "green"),
        ]
    )

    lane_html = "".join(
        [
            signal_row("Releases", f"Latest credits snapshot: WordPress {latest_release.get('version', 'n/a')}", f"{compact(latest_release.get('credited_people_count'))} people", "blue"),
            signal_row("Make/Core discussion", f"{compact(latest_comments.get('comments'))} comments on {compact(latest_comments.get('posts_commented_on'))} posts in latest quarter", f"{compact(latest_comments.get('unique_commenters'))} commenters", "green"),
            signal_row("Developer notes", "Release-tagged Make/Core dev-note posts in the latest quarter", f"{compact(latest_dev_notes.get('release_tagged_dev_notes'))}", "violet"),
            signal_row("WordCamps", f"Latest full-year event count uses {latest_wc_full.get('label', 'n/a')}", f"{compact(latest_wc_full.get('events'))}", "blue"),
            signal_row("Events calendar", f"{compact(latest_events.get('unique_meetup_groups'))} unique Meetup groups in current events snapshot", f"{compact(latest_events.get('event_count'))} events", "green"),
            signal_row("Translation", f"{compact(latest_translation.get('core_dev_90_plus'))} Core dev locales are at least 90% translated", f"{compact(latest_translation.get('locale_count'))} locales", "blue"),
            signal_row("Pledged contribution", "Current Five for the Future public pledge listing", f"{compact(latest_fttf.get('pledged_hours_per_week'))} hrs/wk", "violet"),
            signal_row("Support queue", f"{compact(latest_support.get('participants'))} participants in current support snapshot", f"{pct(latest_support.get('unresolved_share_pct'))} unresolved", "amber"),
            signal_row("Plugin maintenance", f"Popular-plugin sample median update age is {num(latest_plugin_maintenance.get('median_days_since_update')):.0f} days", f"{compact(latest_plugin_maintenance.get('stale_2y_count'))} stale 2y", "green"),
            signal_row("Directory activity", f"{compact(latest_directory_activity.get('plugins_added_30d'))} plugins added and {compact(latest_directory_activity.get('plugins_updated_30d'))} updated in 30 days", f"{compact(plugin_count)} plugins", "green"),
        ]
    )

    chart_html = "\n".join(
        [
            sparkline("Make/Core comments by quarter", make_comment_points, "#159957"),
            sparkline("Make/Core dev notes by quarter", dev_note_points, "#7c3aed"),
            sparkline("WordCamp records by year", wordcamp_points, "#2563eb"),
            sparkline("Core release props", release_prop_points, "#b7791f"),
        ]
    )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress Ecosystem Activity</title>
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
    .lede {{ max-width:900px; color:var(--muted); font-size:18px; margin-bottom:18px; }}
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
    .grid {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.1fr); gap:14px; align-items:start; }}
    .section, .signal-panel {{ padding:18px; }}
    .signals {{ display:grid; gap:9px; }}
    .signal-row {{ display:flex; justify-content:space-between; gap:14px; align-items:center; border-left:5px solid var(--blue); background:#fbfdff; border-radius:8px; padding:12px; }}
    .signal-row.green {{ border-left-color:var(--green); }}
    .signal-row.amber {{ border-left-color:var(--amber); }}
    .signal-row.violet {{ border-left-color:var(--violet); }}
    .signal-row strong, .signal-row span {{ display:block; }}
    .signal-row span {{ color:var(--muted); font-size:13px; }}
    .signal-row b {{ font-size:20px; white-space:nowrap; }}
    .charts {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
    .spark {{ width:100%; height:auto; display:block; background:#fbfdff; border:1px solid var(--line); border-radius:8px; padding:4px; }}
    .spark-title {{ font-size:16px; font-weight:750; fill:var(--ink); }}
    .spark-end {{ font-size:13px; font-weight:800; fill:var(--ink); }}
    .axis {{ font-size:11px; fill:var(--muted); }}
    .spark-grid {{ stroke:#e8eef5; stroke-width:1; }}
    .readout {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin-top:14px; }}
    .readout div {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:#fbfdff; }}
    .readout strong {{ display:block; margin-bottom:5px; }}
    .readout span {{ color:var(--muted); font-size:14px; }}
    .footer-note {{ margin-top:14px; background:#eef4ff; border:1px solid #cfe0ff; border-radius:8px; padding:14px 16px; color:#244067; }}
    @media (max-width:980px) {{
      .metrics {{ grid-template-columns:1fr 1fr; }}
      .grid, .charts, .readout {{ grid-template-columns:1fr; }}
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
    <h1>WordPress ecosystem activity</h1>
    <p class="lede">A compact readout of community activity outside Core Trac and Gutenberg issues: releases, Make/Core discussion, WordCamps, events, translations, pledges, support, plugins, and themes.</p>
{nav_html()}

    <section class="metrics" aria-label="Ecosystem activity summary">
{metric_html}
    </section>

    <section class="grid">
      <div class="signal-panel">
        <h2>Activity lanes</h2>
        <p class="note">These lanes keep non-ticket activity separate from issue tracker flow, which helps avoid treating GitHub and Trac as the whole WordPress community.</p>
        <div class="signals">{lane_html}</div>
      </div>
      <div class="section">
        <h2>Recent patterns</h2>
        <div class="charts">{chart_html}</div>
      </div>
    </section>

    <section class="section" style="margin-top:14px">
      <h2>How to read this</h2>
      <div class="readout">
        <div><strong>Community activity is wider than tickets.</strong><span>Release credits, discussion, events, translation, support, and directories show multiple active participation channels.</span></div>
        <div><strong>Some signals are snapshots.</strong><span>Events, support queues, plugin freshness, translation, and pledge counts are current-state views, while WordCamp, Make/Core, and release rows have historical shape.</span></div>
        <div><strong>Use this with tracker data.</strong><span>Fewer first-time reporters does not mean the whole ecosystem is inactive; it means tracker participation is softer than before.</span></div>
      </div>
      <p class="footer-note">Rows come from existing SQLite tables including <code>wordcamp_yearly</code>, <code>make_core_comment_quarterly</code>, <code>make_core_dev_note_quarterly</code>, <code>core_release_credits</code>, <code>translation_snapshots</code>, <code>fttf_snapshots</code>, <code>support_forum_snapshot_summary</code>, and <code>directory_activity_snapshots</code>. Integrity check: <code>{esc(integrity)}</code>. Latest WordCamp row in the database is {esc(latest_wc_any.get("label", "n/a"))}; current and future years are partial.</p>
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
