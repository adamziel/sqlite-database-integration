#!/usr/bin/env python3
import html
import sqlite3
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
OUT = ROOT / "support_load.html"

COLORS = {
    "blue": "#2563eb",
    "green": "#159957",
    "amber": "#b7791f",
    "violet": "#7c3aed",
    "red": "#c2410c",
    "teal": "#0f766e",
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


def table_exists(conn, name):
    return bool(one(conn, "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)))


def latest(rows_, key):
    return max(rows_, key=lambda row: row.get(key, ""), default={})


def nav_html():
    return "\n".join(
        [
            '    <nav class="nav">',
            '      <a href="index.html#participation">Participation</a>',
            '      <a href="ecosystem_activity.html">Ecosystem activity</a>',
            '      <a href="project_load.html">Project load</a>',
            '      <a href="market_position.html">Market position</a>',
            '      <a href="new_site_choice.html">New-site choice</a>',
            '      <a href="search_interest.html">Search interest</a>',
            '      <a href="developer_interest.html">Developer interest</a>',
            '      <a href="job_demand.html">Job demand</a>',
            '      <a href="contributor_depth.html">Contributor depth</a>',
            '      <a href="progress_summary.html">Progress summary</a>',
            '      <a href="decision_brief.html">Decision brief</a>',
            '      <a href="goal_audit.html">Goal audit</a>',
            '      <a href="data_inventory.html">Data inventory</a>',
            '      <a href="source_gap_plan.html">Source gap plan</a>',
            "    </nav>",
        ]
    )


def metric_card(label, value, note, tone="blue"):
    return f"""
      <article class="metric {esc(tone)}">
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


def bar_row(label, value, max_value, color=COLORS["blue"], suffix=""):
    value = num(value)
    width = 0 if max_value <= 0 else max(2, min(100, value / max_value * 100))
    shown = f"{compact(value)}{suffix}"
    return f"""
        <div class="barline">
          <div class="bar-label"><span>{esc(label)}</span><strong>{esc(shown)}</strong></div>
          <div class="bar"><span style="width:{width:.1f}%;background:{esc(color)}"></span></div>
        </div>"""


def point_series(rows_, key, value_key, label_key="label"):
    return [
        (row.get(label_key) or str(row.get(key, ""))[:7], num(row.get(value_key)))
        for row in sorted(rows_, key=lambda item: item.get(key, ""))
    ]


def multi_line_chart(title, note, series, value_decimals=0):
    series = [
        {
            "name": item["name"],
            "color": item["color"],
            "points": [(str(label), num(value)) for label, value in item["points"] if value is not None],
        }
        for item in series
        if item.get("points")
    ]
    if not series:
        return ""
    width, height = 760, 300
    left, right, top, bottom = 58, 26, 42, 48
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [value for item in series for _label, value in item["points"]]
    y_max = max(values or [1])
    y_top = y_max + max(1, y_max * 0.12)
    max_points = max(len(item["points"]) for item in series)

    def x(index):
        if max_points <= 1:
            return left + plot_w
        return left + index / (max_points - 1) * plot_w

    def y(value):
        return top + (1 - value / y_top) * plot_h

    def fmt(value):
        return compact(value) if value >= 1000 and value_decimals == 0 else f"{value:.{value_decimals}f}"

    pieces = [
        '<article class="chart-card">',
        f'<h2>{esc(title)}</h2>',
        f'<p>{esc(note)}</p>',
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
    ]
    for tick in [0, y_top / 2, y_top]:
        yy = y(tick)
        pieces.append(f'<line x1="{left}" x2="{width - right}" y1="{yy:.1f}" y2="{yy:.1f}" class="gridline" />')
        pieces.append(f'<text x="{left - 10}" y="{yy + 4:.1f}" class="axis" text-anchor="end">{esc(fmt(tick))}</text>')
    for item in series:
        points = item["points"]
        path = " ".join(
            ("M" if i == 0 else "L") + f"{x(i):.1f},{y(value):.1f}"
            for i, (_label, value) in enumerate(points)
        )
        pieces.append(
            f'<path d="{path}" fill="none" stroke="{esc(item["color"])}" stroke-width="3" '
            'stroke-linecap="round" stroke-linejoin="round" />'
        )
        pieces.append(f'<circle cx="{x(len(points) - 1):.1f}" cy="{y(points[-1][1]):.1f}" r="4" fill="{esc(item["color"])}" />')
    first_label = series[0]["points"][0][0]
    last_label = series[0]["points"][-1][0]
    pieces.append(f'<text x="{left}" y="{height - 16}" class="axis">{esc(first_label)}</text>')
    pieces.append(f'<text x="{width - right}" y="{height - 16}" class="axis" text-anchor="end">{esc(last_label)}</text>')
    pieces.append("</svg>")
    pieces.append('<div class="legend">')
    for item in series:
        latest_value = item["points"][-1][1]
        pieces.append(f'<span><i style="background:{esc(item["color"])}"></i>{esc(item["name"])} <b>{esc(fmt(latest_value))}</b></span>')
    pieces.append("</div>")
    pieces.append("</article>")
    return "\n".join(pieces)


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        integrity = one(conn, "PRAGMA integrity_check")
        snapshot = latest(rows(conn, "SELECT * FROM support_forum_snapshot_summary"), "snapshot_at")
        monthly = rows(conn, "SELECT * FROM support_forum_activity_monthly ORDER BY month")
        age_buckets = rows(conn, "SELECT * FROM support_forum_age_buckets ORDER BY CAST(bucket_order AS INTEGER)")
        forums = rows(
            conn,
            """
            SELECT forum_name, topics, unresolved, unresolved_share_pct, resolved_share_pct, no_replies
            FROM support_forum_unanswered_by_forum
            ORDER BY CAST(unresolved AS REAL) DESC
            LIMIT 8
            """,
        )
        archive = (
            rows(
                conn,
                """
                SELECT *
                FROM support_forum_archive_snapshots
                WHERE CAST(estimated_total_topics AS REAL) > 0
                  AND NOT (view='all_topics' AND CAST(estimated_total_topics AS REAL) > 100000)
                ORDER BY quarter, view
                """,
            )
            if table_exists(conn, "support_forum_archive_snapshots")
            else []
        )
        plugin_rows = rows(
            conn,
            """
            SELECT slug, name, active_installs, support_threads, support_threads_resolved,
                   (CAST(support_threads AS REAL) - CAST(support_threads_resolved AS REAL)) AS unresolved_threads,
                   CASE WHEN CAST(support_threads AS REAL) > 0
                        THEN ROUND(CAST(support_threads_resolved AS REAL) / CAST(support_threads AS REAL) * 100, 1)
                        ELSE 0 END AS resolved_pct
            FROM major_plugin_install_snapshot
            ORDER BY unresolved_threads DESC
            LIMIT 8
            """,
        )
        gap = rows(conn, "SELECT * FROM source_gaps WHERE signal='support_forum_history'")
    finally:
        conn.close()

    metrics = "".join(
        [
            metric_card("Topics sampled", compact(snapshot.get("topics")), f"{snapshot.get('snapshot_at', '')[:10]} support queue snapshot", "blue"),
            metric_card("Unresolved", compact(snapshot.get("unresolved")), f"{pct(snapshot.get('unresolved_share_pct'))} of sampled topics", "amber"),
            metric_card("Resolved", compact(snapshot.get("resolved")), f"{pct(snapshot.get('resolved_share_pct'))} of sampled topics", "green"),
            metric_card("Participants", compact(snapshot.get("participants")), f"{compact(snapshot.get('unique_starters'))} unique topic starters", "violet"),
            metric_card("No replies", compact(snapshot.get("no_replies")), f"{pct(snapshot.get('no_reply_share_pct'))} of sampled topics", "green"),
            metric_card("Archive quarters", compact(len({row.get("quarter") for row in archive if row.get("quarter")})), f"{compact(len(archive))} Wayback rows", "blue"),
        ]
    )

    month_chart = multi_line_chart(
        "Support queue by last activity month",
        "Current support topics grouped by the month of last activity. This is a snapshot distribution, not all topics opened in the month.",
        [
            {"name": "Topics", "color": COLORS["blue"], "points": point_series(monthly, "month", "topics")},
            {"name": "Unresolved", "color": COLORS["amber"], "points": point_series(monthly, "month", "unresolved")},
            {"name": "Resolved", "color": COLORS["green"], "points": point_series(monthly, "month", "resolved")},
            {"name": "Replies", "color": COLORS["violet"], "points": point_series(monthly, "month", "replies")},
        ],
    )
    archive_chart = multi_line_chart(
        "Archived support queue estimate",
        "Quarterly Wayback first-page snapshots. Estimate equals pagination pages times first-page topic count; zero parses and one early all-topics outlier are excluded.",
        [
            {
                "name": "Unresolved",
                "color": COLORS["amber"],
                "points": point_series([row for row in archive if row.get("view") == "unresolved"], "quarter", "estimated_total_topics"),
            },
            {
                "name": "Resolved",
                "color": COLORS["green"],
                "points": point_series([row for row in archive if row.get("view") == "resolved"], "quarter", "estimated_total_topics"),
            },
            {
                "name": "No replies",
                "color": COLORS["red"],
                "points": point_series([row for row in archive if row.get("view") == "no_replies"], "quarter", "estimated_total_topics"),
            },
        ],
    )

    max_age_topics = max([num(row.get("topics")) for row in age_buckets] or [1])
    max_forum_unresolved = max([num(row.get("unresolved")) for row in forums] or [1])
    max_plugin_unresolved = max([num(row.get("unresolved_threads")) for row in plugin_rows] or [1])

    age_rows = "".join(
        bar_row(
            f"{row.get('age_bucket')} unresolved",
            row.get("unresolved"),
            max_age_topics,
            COLORS["amber"],
        )
        + bar_row(
            f"{row.get('age_bucket')} resolved",
            row.get("resolved"),
            max_age_topics,
            COLORS["green"],
        )
        for row in age_buckets
    )
    forum_rows = "".join(
        bar_row(
            str(row.get("forum_name", "")),
            row.get("unresolved"),
            max_forum_unresolved,
            COLORS["amber"],
            f" of {compact(row.get('topics'))}",
        )
        for row in forums
    )
    plugin_rows_html = "".join(
        bar_row(
            str(row.get("name", "")),
            row.get("unresolved_threads"),
            max_plugin_unresolved,
            COLORS["red"] if num(row.get("resolved_pct")) < 50 else COLORS["violet"],
            f" unresolved, {pct(row.get('resolved_pct'))} resolved",
        )
        for row in plugin_rows
    )

    oldest = snapshot.get("oldest_last_activity_at", "")[:10]
    latest_activity = snapshot.get("latest_last_activity_at", "")[:10]
    largest_forum = forums[0] if forums else {}
    stale_90 = sum(num(row.get("topics")) for row in age_buckets if row.get("age_bucket") in ("91-180 days", "181+ days"))
    stale_90_share = stale_90 / num(snapshot.get("topics"), 1) * 100 if num(snapshot.get("topics")) else 0
    gap_note = gap[0].get("note") if gap else "The support-forum source is a current snapshot, not a full history."

    readout = "".join(
        [
            signal_row(
                "Current queue is visible",
                "The sampled WordPress.org support queue has enough rows to show where open help load sits now.",
                compact(snapshot.get("topics")),
                "blue",
            ),
            signal_row(
                "Archive adds direction",
                "Wayback snapshots now add quarterly support-view estimates from 2018 onward.",
                compact(len(archive)),
                "blue",
            ),
            signal_row(
                "Open load is concentrated",
                f"{largest_forum.get('forum_name', 'Top forum')} holds the largest unresolved count in the current sample.",
                compact(largest_forum.get("unresolved")),
                "amber",
            ),
            signal_row(
                "Older active topics remain present",
                "Topics with last activity more than 90 days ago are still present in the sampled queue.",
                pct(stale_90_share),
                "amber",
            ),
            signal_row(
                "No-reply count is low in this snapshot",
                "The current sampled queue has few topics with no visible replies.",
                compact(snapshot.get("no_replies")),
                "green",
            ),
        ]
    )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress Support Load</title>
  <style>
    :root {{
      color-scheme: light;
      --ink:#172033; --muted:#637083; --line:#d9e1ea; --paper:#f6f8fb; --panel:#fff;
      --blue:#2563eb; --green:#159957; --amber:#b7791f; --violet:#7c3aed; --red:#c2410c;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--paper); color:var(--ink); font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    main {{ max-width:1220px; margin:0 auto; padding:34px 20px 48px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(34px,4vw,56px); line-height:1.04; letter-spacing:0; }}
    h2 {{ margin:0 0 8px; font-size:22px; }}
    h3 {{ margin:0 0 7px; font-size:13px; text-transform:uppercase; letter-spacing:.07em; color:var(--muted); }}
    p {{ margin:0; color:var(--muted); }}
    a {{ color:var(--blue); }}
    code {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:13px; overflow-wrap:anywhere; }}
    .lede {{ max-width:900px; font-size:18px; margin-bottom:20px; }}
    .nav {{ display:flex; flex-wrap:wrap; gap:8px; margin:18px 0 22px; }}
    .nav a {{ border:1px solid var(--line); border-radius:999px; padding:7px 11px; background:#fbfdff; text-decoration:none; font-weight:700; font-size:13px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; margin:22px 0; }}
    .metric, .section, .chart-card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .metric {{ border-top:5px solid var(--blue); min-height:148px; }}
    .metric.green {{ border-top-color:var(--green); }}
    .metric.amber {{ border-top-color:var(--amber); }}
    .metric.violet {{ border-top-color:var(--violet); }}
    .metric strong {{ display:block; font-size:32px; line-height:1; margin:6px 0 8px; }}
    .metric p {{ font-size:14px; }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; align-items:start; }}
    .charts {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:14px; }}
    .chart-card p, .section p {{ font-size:14px; margin-bottom:10px; }}
    svg {{ display:block; width:100%; height:auto; overflow:visible; }}
    .gridline {{ stroke:#e6edf5; stroke-width:1; }}
    .axis {{ fill:#64748b; font-size:12px; }}
    .legend {{ display:flex; flex-wrap:wrap; gap:8px 13px; margin-top:8px; font-size:13px; color:var(--muted); }}
    .legend span {{ display:inline-flex; align-items:center; gap:6px; }}
    .legend i {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
    .legend b {{ color:var(--ink); }}
    .signals, .bar-stack {{ display:grid; gap:9px; }}
    .signal-row {{ display:flex; justify-content:space-between; gap:14px; align-items:center; border-left:5px solid var(--blue); background:#fbfdff; border-radius:8px; padding:12px; }}
    .signal-row.green {{ border-left-color:var(--green); }}
    .signal-row.amber {{ border-left-color:var(--amber); }}
    .signal-row strong {{ display:block; line-height:1.2; }}
    .signal-row span {{ display:block; color:var(--muted); font-size:14px; margin-top:3px; }}
    .signal-row b {{ white-space:nowrap; font-size:19px; }}
    .bar-label {{ display:flex; justify-content:space-between; gap:10px; font-size:13px; margin-bottom:4px; }}
    .bar-label span {{ overflow-wrap:anywhere; }}
    .bar-label strong {{ white-space:nowrap; }}
    .bar {{ height:9px; border-radius:999px; background:#e7edf5; overflow:hidden; }}
    .bar span {{ display:block; height:100%; border-radius:inherit; }}
    .callout {{ margin-top:14px; padding:14px; border:1px solid var(--line); border-left:5px solid var(--amber); border-radius:8px; background:#fffaf0; color:#7c4a03; }}
    .footer-note {{ margin-top:18px; font-size:13px; }}
    @media (max-width:960px) {{
      main {{ padding:24px 14px 36px; }}
      .metrics, .grid, .charts {{ grid-template-columns:1fr; }}
      .metric {{ min-height:auto; }}
      .signal-row {{ align-items:flex-start; flex-direction:column; }}
      .signal-row b, .bar-label strong {{ white-space:normal; }}
    }}
  </style>
</head>
<body>
<main>
  <h1>WordPress support load</h1>
  <p class="lede">A compact view of WordPress.org support data already stored in SQLite: current sampled topics, archived quarterly support-view estimates, unresolved and resolved counts, last-activity age buckets, forum-level open load, and major-plugin support counts.</p>
{nav_html()}

  <section class="metrics" aria-label="Support summary">
{metrics}
  </section>

  <section class="grid">
    <article class="section">
      <h2>Decision lanes</h2>
      <div class="signals">
{readout}
      </div>
    </article>
    <article class="section">
      <h2>How to read this</h2>
      <p>This page uses a current WordPress.org support snapshot plus Wayback first-page snapshots. It is useful for where support load sits now and for rough archive direction, but it is not a full historical forum export. The last-activity range in the current sample is {esc(oldest)} to {esc(latest_activity)}.</p>
      <p class="callout">{esc(gap_note)}</p>
    </article>
  </section>

  <section class="charts">
{archive_chart}
{month_chart}
    <article class="chart-card">
      <h2>Open load by age</h2>
      <p>Current topics grouped by age since last visible activity.</p>
      <div class="bar-stack">
{age_rows}
      </div>
    </article>
    <article class="chart-card">
      <h2>Unresolved by forum</h2>
      <p>Forum-level view of where unresolved support topics sit in the sampled queue.</p>
      <div class="bar-stack">
{forum_rows}
      </div>
    </article>
    <article class="chart-card">
      <h2>Major-plugin support load</h2>
      <p>Current WordPress.org plugin API support-thread counts for the tracked major-plugin list.</p>
      <div class="bar-stack">
{plugin_rows_html}
      </div>
    </article>
  </section>

  <p class="footer-note">Rows come from <code>support_forum_snapshot_summary</code>, <code>support_forum_archive_snapshots</code>, <code>support_forum_activity_monthly</code>, <code>support_forum_age_buckets</code>, <code>support_forum_unanswered_by_forum</code>, <code>support_forum_topics</code>, and <code>major_plugin_install_snapshot</code>. Integrity check: <code>{esc(integrity)}</code>.</p>
</main>
</body>
</html>
"""
    OUT.write_text(html_doc, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
