#!/usr/bin/env python3
import html
import sqlite3
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
OUT = ROOT / "new_site_choice.html"

COLORS = {
    "WordPress": "#2563eb",
    "Shopify": "#159957",
    "Wix": "#b7791f",
    "Squarespace": "#64748b",
    "Webflow": "#7c3aed",
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


def signed_pts(value):
    return f"{num(value):+.1f} pts"


def one(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else 0


def rows(conn, sql, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def nav_html():
    return "\n".join(
        [
            '    <nav class="nav">',
            '      <a href="index.html#market">Market Position</a>',
            '      <a href="market_position.html">Market position</a>',
            '      <a href="new_site_choice.html">New-site choice</a>',
            '      <a href="search_interest.html">Search interest</a>',
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
    shown = compact(value) if not suffix else f"{value:.1f}{suffix}"
    return f"""
        <div class="barline">
          <div class="bar-label"><span>{esc(label)}</span><strong>{esc(shown)}</strong></div>
          <div class="bar"><span style="width:{width:.1f}%;background:{esc(color)}"></span></div>
        </div>"""


def grouped_snapshot(title, note, rows_, value_key):
    usable = [row for row in rows_ if row.get(value_key) not in (None, "")]
    usable.sort(key=lambda row: num(row.get(value_key)), reverse=True)
    max_value = max([num(row.get(value_key)) for row in usable] or [1])
    bars = "".join(
        bar_row(
            row.get("technology"),
            row.get(value_key),
            max_value,
            COLORS.get(row.get("technology"), COLORS["ink"]),
        )
        for row in usable
    )
    return f"""
      <article class="panel">
        <h2>{esc(title)}</h2>
        <p>{esc(note)}</p>
        <div class="bar-stack">{bars}</div>
      </article>"""


def tier_line_chart(title, note, rows_):
    points = [(row.get("label"), num(row.get("wordpress_share_pct"))) for row in rows_]
    if not points:
        return ""
    width, height = 720, 260
    left, right, top, bottom = 54, 28, 44, 50
    plot_w = width - left - right
    plot_h = height - top - bottom
    y_top = max(100, max(value for _label, value in points) + 8)

    def x(index):
        if len(points) <= 1:
            return left + plot_w
        return left + index / (len(points) - 1) * plot_w

    def y(value):
        return top + (1 - value / y_top) * plot_h

    path = " ".join(
        ("M" if index == 0 else "L") + f"{x(index):.1f},{y(value):.1f}"
        for index, (_label, value) in enumerate(points)
    )
    pieces = [
        '<article class="chart-card">',
        f'<h2>{esc(title)}</h2>',
        f'<p>{esc(note)}</p>',
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
    ]
    for tick in [0, 50, 100]:
        yy = y(tick)
        pieces.append(f'<line x1="{left}" x2="{width - right}" y1="{yy:.1f}" y2="{yy:.1f}" class="gridline" />')
        pieces.append(f'<text x="{left - 9}" y="{yy + 4:.1f}" class="axis" text-anchor="end">{tick}%</text>')
    pieces.append(f'<path d="{path}" fill="none" stroke="{COLORS["violet"]}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />')
    for index, (label, value) in enumerate(points):
        pieces.append(f'<circle cx="{x(index):.1f}" cy="{y(value):.1f}" r="4" fill="{COLORS["violet"]}" />')
        pieces.append(f'<text x="{x(index):.1f}" y="{height - 18}" class="axis" text-anchor="middle">{esc(label)}</text>')
    pieces.append(f'<text x="{width - right}" y="24" class="chart-end" text-anchor="end">{pct(points[-1][1])}</text>')
    pieces.append("</svg>")
    pieces.append("</article>")
    return "\n".join(pieces)


def multi_line_chart(title, note, series, value_decimals=1, y_suffix="%"):
    clean = []
    for item in series:
        points = [(str(label), num(value)) for label, value in item.get("points", []) if value is not None]
        if points:
            clean.append({"name": item["name"], "color": item["color"], "points": points})
    if not clean:
        return ""
    width, height = 760, 310
    left, right, top, bottom = 58, 28, 46, 50
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [value for item in clean for _label, value in item["points"]]
    y_max = max(values or [1])
    y_top = max(1, y_max + max(1, y_max * 0.1))
    max_points = max(len(item["points"]) for item in clean)

    def x(index):
        if max_points <= 1:
            return left + plot_w
        return left + index / (max_points - 1) * plot_w

    def y(value):
        return top + (1 - value / y_top) * plot_h

    def fmt(value):
        if y_suffix == "":
            return compact(value)
        return f"{value:.{value_decimals}f}{y_suffix}"

    pieces = [
        '<article class="chart-card">',
        f'<h2>{esc(title)}</h2>',
        f'<p>{esc(note)}</p>',
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
    ]
    for tick in [0, y_top / 2, y_top]:
        yy = y(tick)
        pieces.append(f'<line x1="{left}" x2="{width - right}" y1="{yy:.1f}" y2="{yy:.1f}" class="gridline" />')
        pieces.append(f'<text x="{left - 9}" y="{yy + 4:.1f}" class="axis" text-anchor="end">{esc(fmt(tick))}</text>')
    for item in clean:
        path = " ".join(
            ("M" if index == 0 else "L") + f"{x(index):.1f},{y(value):.1f}"
            for index, (_label, value) in enumerate(item["points"])
        )
        pieces.append(
            f'<path d="{path}" fill="none" stroke="{esc(item["color"])}" stroke-width="3" '
            'stroke-linecap="round" stroke-linejoin="round" />'
        )
        pieces.append(
            f'<circle cx="{x(len(item["points"]) - 1):.1f}" cy="{y(item["points"][-1][1]):.1f}" '
            f'r="4" fill="{esc(item["color"])}" />'
        )
    first_label = clean[0]["points"][0][0]
    last_label = clean[0]["points"][-1][0]
    pieces.append(f'<text x="{left}" y="{height - 18}" class="axis">{esc(first_label)}</text>')
    pieces.append(f'<text x="{width - right}" y="{height - 18}" class="axis" text-anchor="end">{esc(last_label)}</text>')
    pieces.append("</svg>")
    pieces.append('<div class="legend">')
    for item in clean:
        latest_value = item["points"][-1][1]
        pieces.append(
            f'<span><i style="background:{esc(item["color"])}"></i>{esc(item["name"])} '
            f'<b>{esc(fmt(latest_value))}</b></span>'
        )
    pieces.append("</div>")
    pieces.append("</article>")
    return "\n".join(pieces)


def points_for(rows_, technology, value_key):
    return [
        (row.get("label") or row.get("date", "")[:7], row.get(value_key))
        for row in rows_
        if row.get("technology") == technology
    ]


def rank_snapshot(rows_):
    totals = {}
    for row in rows_:
        rank = row.get("rank")
        totals.setdefault(rank, {"order": num(row.get("rank_order")), "tracked": 0, "wordpress": 0})
        totals[rank]["tracked"] += num(row.get("mobile_origins"))
        if row.get("technology") == "WordPress":
            totals[rank]["wordpress"] += num(row.get("mobile_origins"))
    ordered = sorted(totals.items(), key=lambda item: item[1]["order"])
    bars = []
    for label, data in ordered:
        share = data["wordpress"] / data["tracked"] * 100 if data["tracked"] else 0
        bars.append(bar_row(label, share, 100, COLORS["blue"], suffix="%"))
    return "".join(bars)


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        integrity = one(conn, "PRAGMA integrity_check")
        summary = rows(conn, "SELECT * FROM new_site_choice_summary ORDER BY signal")
        builtwith = rows(conn, "SELECT * FROM builtwith_new_site_snapshot ORDER BY technology")
        tier_rows = rows(conn, "SELECT * FROM builtwith_tier_share_snapshot ORDER BY CAST(tier_order AS INTEGER)")
        http_share = rows(
            conn,
            """
            SELECT quarter AS date, label, technology,
                   avg_mobile_tracked_share_pct AS mobile_tracked_share_pct,
                   avg_total_tracked_share_pct AS total_tracked_share_pct,
                   avg_mobile_origins AS mobile_origins,
                   months
            FROM http_archive_tracked_share_quarterly
            WHERE technology IN ('WordPress','Shopify','Wix','Squarespace','Webflow')
            ORDER BY quarter, technology
            """,
        )
        rank_rows = rows(
            conn,
            """
            SELECT date, rank, rank_order, technology, mobile_origins
            FROM http_archive_rank_adoption_snapshot
            ORDER BY CAST(rank_order AS INTEGER), technology
            """,
        )
        gap = rows(conn, "SELECT * FROM source_gaps WHERE signal='new_site_share_history'")
    finally:
        conn.close()

    by_signal = {row.get("signal"): row for row in summary}
    builtwith_90 = by_signal.get("builtwith_90_day_pipeline", {})
    builtwith_30 = by_signal.get("builtwith_30_day_pipeline", {})
    http_latest = by_signal.get("http_archive_latest_tracked_share", {})
    http_change = by_signal.get("http_archive_tracked_share_change", {})
    top_1m = by_signal.get("builtwith_top_1m_tracked_share", {})
    long_tail = by_signal.get("builtwith_long_tail_tracked_share", {})

    metrics = "".join(
        [
            metric_card(
                "90-day newly found share",
                pct(builtwith_90.get("wordpress_share_pct")),
                f"BuiltWith tracked pipeline; {compact(builtwith_90.get('wordpress_value'))} WordPress sites",
                "green",
            ),
            metric_card(
                "30-day newly found share",
                pct(builtwith_30.get("wordpress_share_pct")),
                f"BuiltWith tracked pipeline; {compact(builtwith_30.get('wordpress_value'))} WordPress sites",
                "green",
            ),
            metric_card(
                "HTTP Archive share",
                pct(http_latest.get("wordpress_share_pct")),
                f"latest recurring mobile crawl, {http_latest.get('period', '')}",
                "blue",
            ),
            metric_card(
                "HTTP Archive change",
                signed_pts(http_change.get("wordpress_value")),
                "WordPress tracked-share change since 2020-01",
                "amber",
            ),
            metric_card("Top 1M tracked share", pct(top_1m.get("wordpress_share_pct")), "BuiltWith current traffic-tier snapshot", "violet"),
            metric_card("Long-tail tracked share", pct(long_tail.get("wordpress_share_pct")), "BuiltWith current outside-Top-1M snapshot", "violet"),
        ]
    )

    thirty_vs_ninety = num(builtwith_30.get("wordpress_share_pct")) - num(builtwith_90.get("wordpress_share_pct"))
    lanes = "".join(
        [
            signal_row(
                "WordPress still leads the current pipeline",
                f"BuiltWith 90-day newly found counts show WordPress {num(builtwith_90.get('wordpress_to_next_peer_ratio')):.2f}x the next tracked peer.",
                pct(builtwith_90.get("wordpress_share_pct")),
                "green",
            ),
            signal_row(
                "The shorter window is lower",
                "The 30-day tracked share is below the 90-day tracked share, so the freshest current proxy is softer.",
                signed_pts(thirty_vs_ninety),
                "amber",
            ),
            signal_row(
                "Recurring crawl share is lower than 2020",
                "HTTP Archive tracked share still leads, but it is below the first stored month.",
                signed_pts(http_change.get("wordpress_value")),
                "amber",
            ),
            signal_row(
                "High-traffic presence remains strong",
                "BuiltWith current Top 1M tracked share stays well above every peer builder in the tracked set.",
                pct(top_1m.get("wordpress_share_pct")),
                "violet",
            ),
            signal_row(
                "True new-site history is still incomplete",
                "This page uses current newly found-site counts plus recurring crawl share until a first-seen cohort source is added.",
                "Partial",
                "blue",
            ),
        ]
    )

    tech_order = ["WordPress", "Shopify", "Wix", "Squarespace", "Webflow"]
    share_chart = multi_line_chart(
        "Quarterly tracked share over time",
        "HTTP Archive mobile-crawl share averaged by quarter across WordPress, Shopify, Wix, Squarespace, and Webflow. This is not a first-seen new-site cohort.",
        [
            {
                "name": tech,
                "color": COLORS[tech],
                "points": points_for(http_share, tech, "mobile_tracked_share_pct"),
            }
            for tech in tech_order
        ],
        value_decimals=1,
        y_suffix="%",
    )
    origin_chart = multi_line_chart(
        "Quarterly detected mobile origins",
        "HTTP Archive recurring mobile-crawl origin counts averaged by quarter. Use it for direction, not exact market sizing.",
        [
            {
                "name": tech,
                "color": COLORS[tech],
                "points": points_for(http_share, tech, "mobile_origins"),
            }
            for tech in ["WordPress", "Shopify", "Wix", "Webflow"]
        ],
        value_decimals=0,
        y_suffix="",
    )
    tier_chart = tier_line_chart(
        "BuiltWith traffic-tier profile",
        "WordPress share among tracked CMS/builder technologies in each current BuiltWith traffic tier.",
        tier_rows,
    )

    gap_note = gap[0].get("note") if gap else "New-site history is recorded as a partial source."
    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress New-Site Choice</title>
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
    h3 {{ margin:0 0 8px; font-size:12px; text-transform:uppercase; letter-spacing:0; color:var(--muted); }}
    p {{ margin:0; }}
    a {{ color:var(--blue); }}
    code {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:13px; overflow-wrap:anywhere; }}
    .lede {{ max-width:920px; color:var(--muted); font-size:18px; margin-bottom:18px; }}
    .nav {{ display:flex; flex-wrap:wrap; gap:8px; margin:18px 0 22px; }}
    .nav a {{ border:1px solid var(--line); border-radius:999px; padding:7px 11px; background:#fbfdff; color:var(--blue); font-size:13px; font-weight:650; text-decoration:none; }}
    .metrics {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin:22px 0; }}
    .metric, .panel, .chart-card, .signal-panel {{
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
    .metric p, .panel p, .chart-card p, .note {{ color:var(--muted); font-size:14px; }}
    .grid {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:14px; align-items:start; }}
    .panel, .chart-card, .signal-panel {{ padding:18px; min-width:0; }}
    .signals {{ display:grid; gap:9px; margin-top:12px; }}
    .signal-row {{ display:flex; justify-content:space-between; gap:14px; align-items:center; border-left:5px solid var(--blue); background:#fbfdff; border-radius:8px; padding:12px; }}
    .signal-row.green {{ border-left-color:var(--green); }}
    .signal-row.amber {{ border-left-color:var(--amber); }}
    .signal-row.violet {{ border-left-color:var(--violet); }}
    .signal-row strong, .signal-row span {{ display:block; }}
    .signal-row span {{ color:var(--muted); font-size:13px; }}
    .signal-row b {{ font-size:20px; white-space:nowrap; }}
    .bar-stack {{ display:grid; gap:11px; margin-top:14px; }}
    .bar-label {{ display:flex; justify-content:space-between; gap:8px; font-size:13px; margin-bottom:4px; }}
    .bar-label span {{ color:var(--muted); }}
    .bar-label strong {{ white-space:nowrap; }}
    .bar {{ height:10px; border-radius:999px; background:#e8eef5; overflow:hidden; }}
    .bar span {{ display:block; height:100%; border-radius:inherit; }}
    .chart-card svg {{ width:100%; height:auto; display:block; margin-top:10px; }}
    .gridline {{ stroke:#e8eef5; stroke-width:1; }}
    .axis {{ font-size:11px; fill:var(--muted); }}
    .chart-end {{ font-size:13px; font-weight:800; fill:var(--ink); }}
    .legend {{ display:flex; flex-wrap:wrap; gap:8px 14px; margin-top:10px; color:var(--muted); font-size:13px; }}
    .legend span {{ display:inline-flex; align-items:center; gap:6px; }}
    .legend i {{ width:10px; height:10px; border-radius:50%; display:inline-block; }}
    .legend b {{ color:var(--ink); }}
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
    <h1>WordPress new-site choice</h1>
    <p class="lede">A compact view of whether new or newly detected sites still point toward WordPress. It combines BuiltWith current newly found-site counts with recurring HTTP Archive crawl signals and traffic-tier context stored in SQLite.</p>
{nav_html()}

    <section class="metrics" aria-label="New-site choice summary">
{metrics}
    </section>

    <section class="grid">
      <div class="signal-panel">
        <h2>Decision lanes</h2>
        <p class="note">Use these lanes as the short version before reading the charts.</p>
        <div class="signals">{lanes}</div>
      </div>
      <div class="panel">
        <h2>How to read this</h2>
        <div class="readout">
          <div><strong>Current pipeline</strong><span>BuiltWith newly found-site counts show WordPress still first among tracked peers.</span></div>
          <div><strong>Trend context</strong><span>HTTP Archive recurring share shows WordPress lower than 2020 while still far ahead.</span></div>
          <div><strong>Best next source</strong><span>A first-seen cohort export would turn this from a proxy page into true new-site history.</span></div>
        </div>
        <p class="footer-note">{esc(gap_note)} SQLite integrity check: <code>{esc(integrity)}</code>.</p>
      </div>
    </section>

    <section class="grid" style="margin-top:14px">
      {share_chart}
      {origin_chart}
    </section>

    <section class="grid" style="margin-top:14px">
      {grouped_snapshot("BuiltWith 90-day newly found sites", "Current Net New Pipeline counts where the public page exposes them. Squarespace is omitted because the fetched page did not expose comparable counts.", builtwith, "new_last_3_months")}
      {grouped_snapshot("BuiltWith 30-day newly found sites", "A shorter current window from the same public BuiltWith pages.", builtwith, "new_last_month")}
    </section>

    <section class="grid" style="margin-top:14px">
      {tier_chart}
      <article class="panel">
        <h2>HTTP Archive current rank tiers</h2>
        <p>Latest mobile-crawl WordPress share among the five tracked technologies within each HTTP Archive rank tier.</p>
        <div class="bar-stack">{rank_snapshot(rank_rows)}</div>
      </article>
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
