#!/usr/bin/env python3
import html
import sqlite3
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
OUT = ROOT / "job_demand.html"

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


def latest(rows_, key):
    return max(rows_, key=lambda row: row.get(key, ""), default={})


def quarter_label(value):
    value = str(value or "")
    if len(value) < 7:
        return value
    month = value[5:7]
    q = {"01": "Q1", "04": "Q2", "07": "Q3", "10": "Q4"}.get(month, "")
    return f"{value[:4]} {q}".strip()


def nav_html():
    return "\n".join(
        [
            '    <nav class="nav">',
            '      <a href="index.html#market">Market Position</a>',
            '      <a href="market_position.html">Market position</a>',
            '      <a href="search_interest.html">Search interest</a>',
            '      <a href="developer_interest.html">Developer interest</a>',
            '      <a href="support_load.html">Support load</a>',
            '      <a href="project_load.html">Project load</a>',
            '      <a href="ecosystem_activity.html">Ecosystem activity</a>',
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


def point_series(rows_, key, value_key, label_transform=quarter_label):
    return [
        (label_transform(row.get(key, "")), num(row.get(value_key)))
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


def date_year(value):
    return str(value or "")[:4]


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        integrity = one(conn, "PRAGMA integrity_check")
        hn = rows(conn, "SELECT * FROM hn_hiring_wordpress_quarterly ORDER BY quarter")
        hn_summary = rows(conn, "SELECT * FROM hn_hiring_demand_summary ORDER BY window")
        jobs = rows(conn, "SELECT * FROM wordpress_jobs_board_snapshots ORDER BY snapshot_date")
        categories = rows(conn, "SELECT * FROM wordpress_jobs_board_category_snapshots ORDER BY snapshot_date, category")
        attention = rows(conn, "SELECT * FROM attention_demand_summary WHERE signal IN ('hn_wordpress_woocommerce_hiring_rate','wordpress_jobs_open_listings','wordpress_jobs_development_listings')")
        gap = rows(conn, "SELECT * FROM source_gaps WHERE signal='job_demand'")
    finally:
        conn.close()

    latest_hn = latest(hn, "quarter")
    latest_jobs = latest(jobs, "snapshot_date")
    summary_by_window = {row.get("window"): row for row in hn_summary}
    latest_4q = summary_by_window.get("latest_4q", {})
    pre_2024 = summary_by_window.get("pre_2024", {})
    attention_by_signal = {row.get("signal"): row for row in attention}
    jobs_summary = attention_by_signal.get("wordpress_jobs_open_listings", {})
    dev_jobs_summary = attention_by_signal.get("wordpress_jobs_development_listings", {})
    hn_attention = attention_by_signal.get("hn_wordpress_woocommerce_hiring_rate", {})

    latest_jobs_date = latest_jobs.get("snapshot_date", "")
    latest_categories = [
        row for row in categories if row.get("snapshot_date") == latest_jobs_date
    ]
    max_category = max([num(row.get("open_jobs")) for row in latest_categories] or [1])
    category_rows = "".join(
        bar_row(str(row.get("category", "")), row.get("open_jobs"), max_category, COLORS["blue"], f" of {compact(row.get('total_jobs'))}")
        for row in sorted(latest_categories, key=lambda item: num(item.get("open_jobs")), reverse=True)
    )

    metrics = "".join(
        [
            metric_card(
                "HN WP/Woo rate",
                f"{num(latest_hn.get('wordpress_or_woocommerce_per_100_comments')):.2f}",
                f"mentions per 100 comments in {quarter_label(latest_hn.get('quarter'))}",
                "amber",
            ),
            metric_card(
                "Latest four-quarter rate",
                f"{num(latest_4q.get('wordpress_or_woocommerce_per_100_comments')):.2f}",
                f"vs {num(pre_2024.get('wordpress_or_woocommerce_per_100_comments')):.2f} before 2024",
                "amber",
            ),
            metric_card(
                "Jobs board listings",
                compact(latest_jobs.get("total_jobs")),
                f"{latest_jobs_date}; {pct(jobs_summary.get('change_pct'))} vs {jobs_summary.get('baseline_period', 'baseline')}",
                "blue",
            ),
            metric_card(
                "Development listings",
                compact(latest_jobs.get("development_jobs")),
                f"{pct(dev_jobs_summary.get('change_pct'))} vs {dev_jobs_summary.get('baseline_period', 'baseline')}",
                "green",
            ),
            metric_card(
                "Remote listings",
                compact(latest_jobs.get("remote_jobs")),
                f"{compact(latest_jobs.get('full_time_jobs'))} full-time listings in current snapshot",
                "violet",
            ),
        ]
    )

    hn_rate_chart = multi_line_chart(
        "HN hiring mention rates",
        "Quarterly mentions per 100 top-level comments in Hacker News Who is hiring threads.",
        [
            {"name": "WP or Woo", "color": COLORS["blue"], "points": point_series(hn, "quarter", "wordpress_or_woocommerce_per_100_comments")},
            {"name": "PHP", "color": COLORS["violet"], "points": point_series(hn, "quarter", "php_per_100_comments")},
            {"name": "Agency", "color": COLORS["red"], "points": point_series(hn, "quarter", "agency_per_100_comments")},
        ],
        value_decimals=2,
    )
    hn_count_chart = multi_line_chart(
        "HN hiring mention counts",
        "Quarterly top-level comments mentioning WordPress or WooCommerce, PHP, or agency/studio terms.",
        [
            {"name": "WP or Woo", "color": COLORS["blue"], "points": point_series(hn, "quarter", "wordpress_or_woocommerce_comments")},
            {"name": "PHP", "color": COLORS["violet"], "points": point_series(hn, "quarter", "php_comments")},
            {"name": "Agency", "color": COLORS["red"], "points": point_series(hn, "quarter", "agency_comments")},
        ],
        value_decimals=0,
    )
    jobs_chart = multi_line_chart(
        "WordPress Jobs board snapshots",
        "Annual archived snapshots plus the current jobs.wordpress.net page. These are visible open listings, not total postings over each year.",
        [
            {"name": "All listings", "color": COLORS["blue"], "points": point_series(jobs, "snapshot_date", "total_jobs", date_year)},
            {"name": "Development", "color": COLORS["green"], "points": point_series(jobs, "snapshot_date", "development_jobs", date_year)},
            {"name": "Project", "color": COLORS["amber"], "points": point_series(jobs, "snapshot_date", "project_jobs", date_year)},
            {"name": "Remote", "color": COLORS["violet"], "points": point_series(jobs, "snapshot_date", "remote_jobs", date_year)},
        ],
        value_decimals=0,
    )

    gap_note = gap[0].get("note") if gap else "The job-demand source is a proxy-led signal."
    hn_change = f"{pct(hn_attention.get('change_pct'))} vs {hn_attention.get('baseline_period', 'baseline')}"

    readout = "".join(
        [
            signal_row(
                "HN mentions are lower",
                "WordPress/WooCommerce mentions in HN Who is hiring threads are lower than the stored pre-2024 baseline.",
                hn_change,
                "amber",
            ),
            signal_row(
                "Jobs board is smaller",
                "The WordPress-specific jobs board has fewer visible open listings than the 2023 archived snapshot.",
                compact(latest_jobs.get("total_jobs")),
                "blue",
            ),
            signal_row(
                "Development remains the largest current category",
                "Development listings are the largest visible category on jobs.wordpress.net in the latest snapshot.",
                compact(latest_jobs.get("development_jobs")),
                "green",
            ),
            signal_row(
                "Agency demand is a separate proxy",
                "Agency/studio mentions in HN hiring threads remain visible, but they are not WordPress-specific by themselves.",
                f"{num(latest_hn.get('agency_per_100_comments')):.2f}",
                "violet",
            ),
        ]
    )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress Job Demand</title>
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
    .metrics {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; margin:22px 0; }}
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
    .signal-row.violet {{ border-left-color:var(--violet); }}
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
  <h1>WordPress job demand</h1>
  <p class="lede">A compact readout of job-demand proxies already stored in SQLite: Hacker News Who is hiring mention rates, WordPress/WooCommerce and PHP mentions, agency/studio mentions, and jobs.wordpress.net archived snapshots.</p>
{nav_html()}

  <section class="metrics" aria-label="Job demand summary">
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
      <p>This page separates WordPress-specific jobs board snapshots from broader hiring-thread mentions. It helps show direction, but it is narrower than a labor-market export from a hiring platform.</p>
      <p class="callout">{esc(gap_note)}</p>
    </article>
  </section>

  <section class="charts">
{hn_rate_chart}
{hn_count_chart}
{jobs_chart}
    <article class="chart-card">
      <h2>Current jobs board categories</h2>
      <p>Visible open listings by category on the latest jobs.wordpress.net snapshot.</p>
      <div class="bar-stack">
{category_rows}
      </div>
    </article>
  </section>

  <p class="footer-note">Rows come from <code>hn_hiring_wordpress_quarterly</code>, <code>hn_hiring_demand_summary</code>, <code>wordpress_jobs_board_snapshots</code>, <code>wordpress_jobs_board_category_snapshots</code>, and <code>attention_demand_summary</code>. Integrity check: <code>{esc(integrity)}</code>.</p>
</main>
</body>
</html>
"""
    OUT.write_text(html_doc, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
