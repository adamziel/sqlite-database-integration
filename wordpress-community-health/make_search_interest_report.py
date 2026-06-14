#!/usr/bin/env python3
import html
import sqlite3
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
OUT = ROOT / "search_interest.html"

COLORS = {
    "wordpress": "#2563eb",
    "woocommerce": "#7c3aed",
    "shopify": "#159957",
    "wix": "#b7791f",
    "webflow": "#0f766e",
    "squarespace": "#64748b",
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


def table_exists(conn, name):
    return bool(one(conn, "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)))


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
            '      <a href="new_site_choice.html">New-site choice</a>',
            '      <a href="developer_interest.html">Developer interest</a>',
            '      <a href="job_demand.html">Job demand</a>',
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
    return f"""
        <div class="barline">
          <div class="bar-label"><span>{esc(label)}</span><strong>{esc(compact(value))}{esc(suffix)}</strong></div>
          <div class="bar"><span style="width:{width:.1f}%;background:{esc(color)}"></span></div>
        </div>"""


def suggestion_card(row):
    top = [item.strip() for item in str(row.get("top_suggestions") or "").split(";") if item.strip()]
    items = "".join(f"<span>{esc(item)}</span>" for item in top[:5])
    counts = [
        ("developer", row.get("developer_count"), COLORS["blue"]),
        ("jobs", row.get("job_count"), COLORS["green"]),
        ("alternatives", row.get("alternative_count"), COLORS["amber"]),
        ("comparisons", row.get("comparison_count"), COLORS["violet"]),
    ]
    max_count = max([num(count) for _label, count, _color in counts] or [1])
    bars = "".join(
        bar_row(label, count, max_count, color)
        for label, count, color in counts
        if num(count) > 0
    )
    return f"""
      <article class="suggest-card">
        <h3>{esc(row.get("seed_query"))}</h3>
        <div class="suggestions">{items}</div>
        <div class="mini-bars">{bars}</div>
      </article>"""


def point_series(rows_, key, value_key, label_transform=quarter_label, limit=None):
    points = [
        (label_transform(row.get(key, "")), num(row.get(value_key)))
        for row in sorted(rows_, key=lambda item: item.get(key, ""))
    ]
    return points[-limit:] if limit else points


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
        wiki = rows(conn, "SELECT * FROM wikimedia_pageviews_quarterly ORDER BY quarter, technology")
        stack = rows(conn, "SELECT * FROM stack_overflow_tag_quarterly ORDER BY quarter, technology")
        suggest = (
            rows(conn, "SELECT * FROM search_query_suggestions ORDER BY seed_group, seed_query, CAST(rank AS INTEGER)")
            if table_exists(conn, "search_query_suggestions")
            else []
        )
        suggest_summary = (
            rows(conn, "SELECT * FROM search_query_intent_summary ORDER BY seed_group, seed_query")
            if table_exists(conn, "search_query_intent_summary")
            else []
        )
        attention = rows(conn, "SELECT * FROM attention_demand_summary WHERE signal IN ('wikimedia_wordpress_pageviews','stack_overflow_wordpress_questions')")
        gap = rows(conn, "SELECT * FROM source_gaps WHERE signal='search_interest'")
    finally:
        conn.close()

    tech_order = ["WordPress", "Shopify", "Wix", "Squarespace", "Webflow", "WooCommerce"]
    attention_by_signal = {row.get("signal"): row for row in attention}
    wiki_summary = attention_by_signal.get("wikimedia_wordpress_pageviews", {})
    so_summary = attention_by_signal.get("stack_overflow_wordpress_questions", {})
    latest_wiki_by_tech = {
        tech: latest([row for row in wiki if row.get("technology") == tech], "quarter")
        for tech in tech_order
    }
    latest_stack_by_tech = {
        tech: latest([row for row in stack if row.get("technology") == tech], "quarter")
        for tech in tech_order
    }

    latest_wp_wiki = latest_wiki_by_tech.get("WordPress", {})
    latest_shopify_wiki = latest_wiki_by_tech.get("Shopify", {})
    latest_wp_stack = latest_stack_by_tech.get("WordPress", {})
    suggest_by_seed = {row.get("seed_query"): row for row in suggest_summary}
    developer_seed = suggest_by_seed.get("wordpress developer", {})
    alternatives_seed = suggest_by_seed.get("wordpress alternatives", {})
    comparison_seed_count = sum(num(row.get("comparison_count")) for row in suggest_summary)
    suggestion_total = len(suggest)
    wiki_ratio = num(latest_wp_wiki.get("views")) / num(latest_shopify_wiki.get("views"), 1)
    latest_total_views = sum(num(row.get("views")) for row in latest_wiki_by_tech.values())
    wp_latest_share = num(latest_wp_wiki.get("views")) / latest_total_views * 100 if latest_total_views else 0
    latest_total_questions = sum(num(row.get("question_count")) for row in latest_stack_by_tech.values())
    wp_question_share = num(latest_wp_stack.get("question_count")) / latest_total_questions * 100 if latest_total_questions else 0

    metrics = "".join(
        [
            metric_card(
                "Wikipedia WordPress views",
                compact(latest_wp_wiki.get("views")),
                f"{quarter_label(latest_wp_wiki.get('quarter'))}; {pct(wiki_summary.get('change_pct'))} vs {wiki_summary.get('baseline_period', 'baseline')}",
                "blue",
            ),
            metric_card(
                "Tracked attention share",
                pct(wp_latest_share),
                "of latest tracked Wikimedia pageviews",
                "green",
            ),
            metric_card(
                "WordPress vs Shopify",
                f"{wiki_ratio:.1f}x",
                "latest Wikimedia pageviews",
                "green",
            ),
            metric_card(
                "Stack Overflow WP",
                compact(latest_wp_stack.get("question_count")),
                f"{quarter_label(latest_wp_stack.get('quarter'))}; {pct(so_summary.get('change_pct'))} vs {so_summary.get('baseline_period', 'baseline')}",
                "amber",
            ),
            metric_card(
                "SO tracked share",
                pct(wp_question_share),
                "of latest tracked Stack Overflow questions",
                "violet",
            ),
            metric_card(
                "Search suggestions",
                compact(suggestion_total),
                "current autocomplete snapshot",
                "blue",
            ),
            metric_card(
                "Developer suggestions",
                compact(num(developer_seed.get("suggestion_count"))),
                "for wordpress developer",
                "green",
            ),
            metric_card(
                "Alternatives suggestions",
                compact(num(alternatives_seed.get("suggestion_count"))),
                "for wordpress alternatives",
                "amber",
            ),
        ]
    )

    wiki_chart = multi_line_chart(
        "Public attention proxy",
        "Quarterly English Wikipedia article pageviews. This is a stable public-interest signal, not search-query volume.",
        [
            {
                "name": tech,
                "color": COLORS.get(tech.lower(), COLORS["blue"]),
                "points": point_series([row for row in wiki if row.get("technology") == tech], "quarter", "views"),
            }
            for tech in tech_order
        ],
    )
    stack_chart = multi_line_chart(
        "Developer-help proxy",
        "Quarterly Stack Overflow tag questions. This shows visible help-seeking, not all developer interest.",
        [
            {
                "name": tech,
                "color": COLORS.get(tech.lower(), COLORS["blue"]),
                "points": point_series([row for row in stack if row.get("technology") == tech], "quarter", "question_count"),
            }
            for tech in tech_order
        ],
    )

    max_views = max([num(row.get("views")) for row in latest_wiki_by_tech.values()] or [1])
    max_questions = max([num(row.get("question_count")) for row in latest_stack_by_tech.values()] or [1])
    wiki_bars = "".join(
        bar_row(tech, latest_wiki_by_tech[tech].get("views"), max_views, COLORS.get(tech.lower(), COLORS["blue"]))
        for tech in tech_order
    )
    stack_bars = "".join(
        bar_row(tech, latest_stack_by_tech[tech].get("question_count"), max_questions, COLORS.get(tech.lower(), COLORS["blue"]))
        for tech in tech_order
    )
    suggestion_cards = "".join(suggestion_card(row) for row in suggest_summary)

    gap_note = gap[0].get("note") if gap else "True search-query interest still needs a search-interest provider."
    readout = "".join(
        [
            signal_row(
                "Public attention still leads the tracked set",
                "WordPress has the highest latest Wikimedia pageview count among the tracked CMS and builder terms.",
                pct(wp_latest_share),
                "green",
            ),
            signal_row(
                "Public attention is softer than pre-2024",
                "The WordPress Wikipedia pageview proxy is lower than the stored pre-2024 comparison quarter.",
                pct(wiki_summary.get("change_pct")),
                "amber",
            ),
            signal_row(
                "Developer-help questions moved much lower",
                "Stack Overflow WordPress-tag questions are far below the stored pre-2024 comparison quarter.",
                pct(so_summary.get("change_pct")),
                "amber",
            ),
            signal_row(
                "Search-query intent is now captured as a snapshot",
                "Autocomplete suggestions include developer, alternatives, comparison, job, pricing, and open/self-hosted themes for selected WordPress queries.",
                compact(suggestion_total),
                "blue",
            ),
            signal_row(
                "This is not Google Trends",
                "Use this page as public-attention, developer-help, and query-intent context, not as true search-query volume.",
                "proxy",
                "violet",
            ),
        ]
    )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress Search Interest</title>
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
    .metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:22px 0; }}
    .metric, .section, .chart-card, .suggest-card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }}
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
    .suggest-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin-top:14px; }}
    .suggest-card h3 {{ text-transform:none; letter-spacing:0; color:var(--ink); font-size:18px; }}
    .suggestions {{ display:flex; flex-wrap:wrap; gap:7px; margin:10px 0 12px; }}
    .suggestions span {{ border:1px solid var(--line); border-radius:999px; padding:5px 8px; background:#fbfdff; color:var(--muted); font-size:13px; }}
    .mini-bars {{ display:grid; gap:6px; }}
    .callout {{ margin-top:14px; padding:14px; border:1px solid var(--line); border-left:5px solid var(--amber); border-radius:8px; background:#fffaf0; color:#7c4a03; }}
    .footer-note {{ margin-top:18px; font-size:13px; }}
    @media (max-width:960px) {{
      main {{ padding:24px 14px 36px; }}
      .metrics, .grid, .charts, .suggest-grid {{ grid-template-columns:1fr; }}
      .metric {{ min-height:auto; }}
      .signal-row {{ align-items:flex-start; flex-direction:column; }}
      .signal-row b, .bar-label strong {{ white-space:normal; }}
    }}
  </style>
</head>
<body>
<main>
  <h1>WordPress search interest</h1>
  <p class="lede">A compact proxy readout for search and public attention using data already stored in SQLite: Wikimedia article pageviews, Stack Overflow tag-question volume, and current autocomplete suggestions for WordPress, developer, alternatives, and comparison queries.</p>
{nav_html()}

  <section class="metrics" aria-label="Search interest summary">
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
      <p>This page is a public-attention proxy. Wikimedia pageviews and Stack Overflow questions are stable public sources, but they do not replace Google Trends or another search-interest provider.</p>
      <p class="callout">{esc(gap_note)}</p>
    </article>
  </section>

  <section class="charts">
    <article class="chart-card" style="grid-column:1 / -1">
      <h2>Search query intent snapshot</h2>
      <p>Current autocomplete suggestions for selected WordPress queries. This captures query themes, not search volume or history.</p>
      <div class="suggest-grid">
{suggestion_cards}
      </div>
    </article>
{wiki_chart}
{stack_chart}
    <article class="chart-card">
      <h2>Latest Wikimedia peer comparison</h2>
      <p>Latest quarter pageviews across the tracked public-interest terms.</p>
      <div class="bar-stack">
{wiki_bars}
      </div>
    </article>
    <article class="chart-card">
      <h2>Latest Stack Overflow peer comparison</h2>
      <p>Latest quarter questions across the tracked developer-help tags.</p>
      <div class="bar-stack">
{stack_bars}
      </div>
    </article>
  </section>

  <p class="footer-note">Rows come from <code>wikimedia_pageviews_quarterly</code>, <code>stack_overflow_tag_quarterly</code>, <code>search_query_suggestions</code>, <code>search_query_intent_summary</code>, and <code>attention_demand_summary</code>. Integrity check: <code>{esc(integrity)}</code>.</p>
</main>
</body>
</html>
"""
    OUT.write_text(html_doc, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
