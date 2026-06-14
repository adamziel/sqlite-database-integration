#!/usr/bin/env python3
import html
import sqlite3
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
OUT = ROOT / "developer_interest.html"

COLORS = {
    "wordpress": "#2563eb",
    "woocommerce": "#7c3aed",
    "shopify": "#159957",
    "wix": "#b7791f",
    "webflow": "#0f766e",
    "squarespace": "#64748b",
    "php": "#4f46e5",
    "agency": "#c2410c",
    "green": "#159957",
    "amber": "#b7791f",
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


def quarter_label(value):
    value = str(value or "")
    if len(value) < 7:
        return value
    month = value[5:7]
    q = {"01": "Q1", "04": "Q2", "07": "Q3", "10": "Q4"}.get(month, "")
    return f"{value[:4]} {q}".strip()


def latest(rows_, key):
    return max(rows_, key=lambda row: row.get(key, ""), default={})


def change_label(summary):
    if not summary:
        return "n/a"
    return f"{pct(summary.get('change_pct'))} vs {summary.get('baseline_period', 'baseline')}"


def nav_html():
    return "\n".join(
        [
            '    <nav class="nav">',
            '      <a href="index.html#market">Market Position</a>',
            '      <a href="index.html#participation">Participation</a>',
            '      <a href="market_position.html">Market position</a>',
            '      <a href="search_interest.html">Search interest</a>',
            '      <a href="job_demand.html">Job demand</a>',
            '      <a href="project_load.html">Project load</a>',
            '      <a href="ecosystem_activity.html">Ecosystem activity</a>',
            '      <a href="support_load.html">Support load</a>',
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


def point_series(rows_, key, value_key, label_transform=quarter_label, limit=None):
    out = []
    for row in sorted(rows_, key=lambda item: item.get(key, "")):
        label = label_transform(row.get(key, ""))
        out.append((label, num(row.get(value_key))))
    if limit:
        return out[-limit:]
    return out


def multi_line_chart(title, note, series, suffix="", value_decimals=0):
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
    y_min = 0
    y_max = max(values or [1])
    if y_max <= y_min:
        y_max = y_min + 1
    y_top = y_max + max(1, y_max * 0.12)

    max_points = max(len(item["points"]) for item in series)

    def x(index):
        if max_points <= 1:
            return left + plot_w
        return left + index / (max_points - 1) * plot_w

    def y(value):
        return top + (1 - ((value - y_min) / (y_top - y_min))) * plot_h

    def fmt(value):
        if value >= 1000 and value_decimals == 0:
            return compact(value)
        return f"{value:.{value_decimals}f}{suffix}"

    ticks = [0, y_top / 2, y_top]
    pieces = [
        '<article class="chart-card">',
        f'<h2>{esc(title)}</h2>',
        f'<p>{esc(note)}</p>',
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
    ]
    for tick in ticks:
        yy = y(tick)
        pieces.append(f'<line x1="{left}" x2="{width - right}" y1="{yy:.1f}" y2="{yy:.1f}" class="gridline" />')
        pieces.append(f'<text x="{left - 10}" y="{yy + 4:.1f}" class="axis" text-anchor="end">{esc(fmt(tick))}</text>')

    for item in series:
        points = item["points"]
        if len(points) == 1:
            path = f"M{x(0):.1f},{y(points[0][1]):.1f}"
        else:
            path = " ".join(
                ("M" if i == 0 else "L") + f"{x(i):.1f},{y(value):.1f}"
                for i, (_label, value) in enumerate(points)
            )
        pieces.append(
            f'<path d="{path}" fill="none" stroke="{esc(item["color"])}" stroke-width="3" '
            'stroke-linecap="round" stroke-linejoin="round" />'
        )
        last_index = len(points) - 1
        _last_label, last_value = points[-1]
        pieces.append(f'<circle cx="{x(last_index):.1f}" cy="{y(last_value):.1f}" r="4" fill="{esc(item["color"])}" />')

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


def signal_row(title, text, value, color="wordpress"):
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
        attention = rows(conn, "SELECT * FROM attention_demand_summary ORDER BY signal")
        stack = rows(conn, "SELECT * FROM stack_overflow_tag_quarterly ORDER BY quarter, technology")
        wiki = rows(conn, "SELECT * FROM wikimedia_pageviews_quarterly ORDER BY quarter, technology")
        hn = rows(conn, "SELECT * FROM hn_hiring_wordpress_quarterly ORDER BY quarter")
        jobs = rows(conn, "SELECT * FROM wordpress_jobs_board_snapshots ORDER BY snapshot_date")
        prs = rows(conn, "SELECT * FROM github_pr_quarterly ORDER BY quarter")
        gap = rows(conn, "SELECT * FROM source_gaps WHERE signal='developer_interest_proxy'")
    finally:
        conn.close()

    attention_by_signal = {row.get("signal"): row for row in attention}
    so_summary = attention_by_signal.get("stack_overflow_wordpress_questions", {})
    wiki_summary = attention_by_signal.get("wikimedia_wordpress_pageviews", {})
    hn_summary = attention_by_signal.get("hn_wordpress_woocommerce_hiring_rate", {})
    jobs_summary = attention_by_signal.get("wordpress_jobs_open_listings", {})

    latest_pr = latest(prs, "quarter")
    latest_hn = latest(hn, "quarter")
    latest_jobs = latest(jobs, "snapshot_date")
    latest_so = latest([row for row in stack if row.get("technology") == "WordPress"], "quarter")
    latest_wiki = latest([row for row in wiki if row.get("technology") == "WordPress"], "quarter")

    stack_techs = [
        ("WordPress", COLORS["wordpress"]),
        ("WooCommerce", COLORS["woocommerce"]),
        ("Shopify", COLORS["shopify"]),
        ("Wix", COLORS["wix"]),
        ("Webflow", COLORS["webflow"]),
    ]
    wiki_techs = [
        ("WordPress", COLORS["wordpress"]),
        ("Shopify", COLORS["shopify"]),
        ("Wix", COLORS["wix"]),
        ("Webflow", COLORS["webflow"]),
        ("WooCommerce", COLORS["woocommerce"]),
    ]

    stack_chart = multi_line_chart(
        "Developer-help questions",
        "Quarterly Stack Overflow tag totals. This shows visible help-seeking on Stack Overflow, not total WordPress development.",
        [
            {
                "name": tech,
                "color": color,
                "points": point_series([row for row in stack if row.get("technology") == tech], "quarter", "question_count", limit=18),
            }
            for tech, color in stack_techs
        ],
        value_decimals=0,
    )
    wiki_chart = multi_line_chart(
        "Public attention proxy",
        "Quarterly English Wikipedia article pageviews. This is broad public attention, not search-query volume.",
        [
            {
                "name": tech,
                "color": color,
                "points": point_series([row for row in wiki if row.get("technology") == tech], "quarter", "views", limit=18),
            }
            for tech, color in wiki_techs
        ],
        value_decimals=0,
    )
    pr_chart = multi_line_chart(
        "GitHub code-review activity",
        "Quarterly wordpress-develop pull requests. This is project contribution activity, not market demand.",
        [
            {"name": "Created PRs", "color": COLORS["wordpress"], "points": point_series(prs, "quarter", "created", limit=18)},
            {"name": "Closed PRs", "color": COLORS["green"], "points": point_series(prs, "quarter", "closed", limit=18)},
            {"name": "Unique authors", "color": COLORS["woocommerce"], "points": point_series(prs, "quarter", "unique_authors", limit=18)},
            {"name": "First-time authors", "color": COLORS["amber"], "points": point_series(prs, "quarter", "first_time_authors", limit=18)},
        ],
        value_decimals=0,
    )
    hn_chart = multi_line_chart(
        "Hiring-thread mention rates",
        "Quarterly mentions per 100 top-level comments in Hacker News Who is hiring threads.",
        [
            {"name": "WP or Woo", "color": COLORS["wordpress"], "points": point_series(hn, "quarter", "wordpress_or_woocommerce_per_100_comments", limit=24)},
            {"name": "PHP", "color": COLORS["php"], "points": point_series(hn, "quarter", "php_per_100_comments", limit=24)},
            {"name": "Agency", "color": COLORS["agency"], "points": point_series(hn, "quarter", "agency_per_100_comments", limit=24)},
        ],
        suffix="",
        value_decimals=2,
    )
    jobs_chart = multi_line_chart(
        "WordPress Jobs board snapshots",
        "Visible open listings on jobs.wordpress.net from annual archived snapshots plus the current page.",
        [
            {"name": "All listings", "color": COLORS["wordpress"], "points": point_series(jobs, "snapshot_date", "total_jobs", lambda value: str(value)[:4])},
            {"name": "Development", "color": COLORS["green"], "points": point_series(jobs, "snapshot_date", "development_jobs", lambda value: str(value)[:4])},
            {"name": "Project", "color": COLORS["amber"], "points": point_series(jobs, "snapshot_date", "project_jobs", lambda value: str(value)[:4])},
        ],
        value_decimals=0,
    )

    metrics = "".join(
        [
            metric_card(
                "Stack Overflow WP",
                compact(latest_so.get("question_count")),
                f"{quarter_label(latest_so.get('quarter'))}; {change_label(so_summary)}",
                "amber",
            ),
            metric_card(
                "Wikipedia views",
                compact(latest_wiki.get("views")),
                f"{quarter_label(latest_wiki.get('quarter'))}; {change_label(wiki_summary)}",
                "blue",
            ),
            metric_card(
                "HN WP/Woo hiring rate",
                f"{num(latest_hn.get('wordpress_or_woocommerce_per_100_comments')):.2f}",
                f"mentions per 100 comments; {change_label(hn_summary)}",
                "amber",
            ),
            metric_card(
                "GitHub PR authors",
                compact(latest_pr.get("unique_authors")),
                f"{quarter_label(latest_pr.get('quarter'))}; {compact(latest_pr.get('first_time_authors'))} first-time authors",
                "green",
            ),
            metric_card(
                "Jobs board listings",
                compact(latest_jobs.get("total_jobs")),
                f"{latest_jobs.get('snapshot_date', 'latest')}; {change_label(jobs_summary)}",
                "amber",
            ),
        ]
    )

    readout = "".join(
        [
            signal_row(
                "Help-seeking moved lower",
                "Stack Overflow WordPress-tag questions are far below the pre-2024 baseline in the stored API series.",
                change_label(so_summary),
                "amber",
            ),
            signal_row(
                "Public attention is softer",
                "Wikipedia WordPress pageviews are lower than the pre-2024 comparison quarter but still much larger than most peer pages in the tracked set.",
                change_label(wiki_summary),
                "wordpress",
            ),
            signal_row(
                "Code-review activity is not showing the same drop",
                "wordpress-develop PR creation and author counts remain substantial in recent quarters.",
                f"{compact(latest_pr.get('created'))} PRs",
                "green",
            ),
            signal_row(
                "Hiring proxies are narrower and lower",
                "HN WP/Woo mentions and jobs.wordpress.net open listings are both lower than their stored baselines.",
                f"{compact(latest_jobs.get('total_jobs'))} listings",
                "amber",
            ),
        ]
    )

    gap_note = gap[0].get("note") if gap else "The developer-interest source is still a proxy-led signal."

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress Developer Interest</title>
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
    .metric strong {{ display:block; font-size:32px; line-height:1; margin:6px 0 8px; }}
    .metric p {{ font-size:14px; }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; align-items:start; }}
    .charts {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-top:14px; }}
    .chart-card p {{ font-size:14px; margin-bottom:10px; }}
    svg {{ display:block; width:100%; height:auto; overflow:visible; }}
    .gridline {{ stroke:#e6edf5; stroke-width:1; }}
    .axis {{ fill:#64748b; font-size:12px; }}
    .end-label {{ font-size:11px; font-weight:700; paint-order:stroke; stroke:#fff; stroke-width:4px; stroke-linejoin:round; }}
    .legend {{ display:flex; flex-wrap:wrap; gap:8px 13px; margin-top:8px; font-size:13px; color:var(--muted); }}
    .legend span {{ display:inline-flex; align-items:center; gap:6px; }}
    .legend b {{ color:var(--ink); }}
    .legend i {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
    .signals {{ display:grid; gap:9px; }}
    .signal-row {{ display:flex; justify-content:space-between; gap:14px; align-items:center; border-left:5px solid var(--blue); background:#fbfdff; border-radius:8px; padding:12px; }}
    .signal-row.green {{ border-left-color:var(--green); }}
    .signal-row.amber {{ border-left-color:var(--amber); }}
    .signal-row strong {{ display:block; line-height:1.2; }}
    .signal-row span {{ display:block; color:var(--muted); font-size:14px; margin-top:3px; }}
    .signal-row b {{ white-space:nowrap; font-size:19px; }}
    .callout {{ margin-top:14px; padding:14px; border:1px solid var(--line); border-left:5px solid var(--amber); border-radius:8px; background:#fffaf0; color:#7c4a03; }}
    .footer-note {{ margin-top:18px; font-size:13px; }}
    @media (max-width:960px) {{
      main {{ padding:24px 14px 36px; }}
      .metrics, .grid, .charts {{ grid-template-columns:1fr; }}
      .metric {{ min-height:auto; }}
      .signal-row {{ align-items:flex-start; flex-direction:column; }}
      .signal-row b {{ white-space:normal; }}
    }}
  </style>
</head>
<body>
<main>
  <h1>WordPress developer interest</h1>
  <p class="lede">A compact readout of developer-attention and demand proxies already stored in SQLite: Stack Overflow questions, Wikipedia pageviews, Hacker News hiring mentions, WordPress Jobs snapshots, and wordpress-develop PR activity.</p>
{nav_html()}

  <section class="metrics" aria-label="Developer interest summary">
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
      <p>This page separates public attention, developer help-seeking, code-review participation, and hiring proxies. Lower help questions can mean less interest, fewer Stack Overflow users, better docs, or answers moving elsewhere, so it should not be read as adoption by itself.</p>
      <p class="callout">{esc(gap_note)}</p>
    </article>
  </section>

  <section class="charts">
{stack_chart}
{wiki_chart}
{pr_chart}
{hn_chart}
{jobs_chart}
  </section>

  <p class="footer-note">Rows come from <code>stack_overflow_tag_quarterly</code>, <code>wikimedia_pageviews_quarterly</code>, <code>hn_hiring_wordpress_quarterly</code>, <code>wordpress_jobs_board_snapshots</code>, <code>github_pr_quarterly</code>, and <code>attention_demand_summary</code>. Integrity check: <code>{esc(integrity)}</code>.</p>
</main>
</body>
</html>
"""
    OUT.write_text(html_doc, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
