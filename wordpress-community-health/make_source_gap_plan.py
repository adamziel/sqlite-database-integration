#!/usr/bin/env python3
import html
import sqlite3
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
OUT = ROOT / "source_gap_plan.html"


PLAN = {
    "new_site_share_history": {
        "label": "New-site choice history",
        "order": "1",
        "color": "blue",
        "next_step": "Add a paid BuiltWith historical trend export or an HTTP Archive first-seen-origin cohort query.",
        "target_tables": ["new_site_cohort_quarterly", "builder_new_site_share_quarterly"],
        "success": "Quarterly WordPress, Shopify, Wix, Squarespace, and Webflow rows across multiple years.",
        "why": "Separates installed presence from whether new site builders are choosing WordPress now.",
    },
    "search_interest": {
        "label": "Search interest",
        "order": "2",
        "color": "green",
        "next_step": "Import Google Trends or an equivalent search-interest export for WordPress, WordPress developer, Shopify, Wix, Squarespace, and Webflow.",
        "target_tables": ["search_interest_quarterly", "search_query_suggestions", "search_query_intent_summary"],
        "success": "Normalized quarterly search series for WordPress and peer builders, plus refreshable query-intent snapshots.",
        "why": "Turns the current Wikimedia, Stack Overflow, and autocomplete proxies into a direct broad-interest signal.",
    },
    "job_demand": {
        "label": "Job demand",
        "order": "3",
        "color": "amber",
        "next_step": "Import a labor-market export such as Lightcast, Indeed/Hiring Lab, LinkedIn, or a comparable source.",
        "target_tables": ["job_demand_quarterly", "wordpress_jobs_board_quarterly_snapshots"],
        "success": "Quarterly WordPress, PHP, CMS, Shopify, Wix, Squarespace, and Webflow demand rows, with the current WordPress Jobs board proxy already stored quarterly.",
        "why": "Separates broad labor-market demand from narrower HN, Remote OK, Remotive, and jobs.wordpress.net proxies.",
    },
    "support_forum_history": {
        "label": "Support history",
        "order": "4",
        "color": "red",
        "next_step": "Keep the Wayback support-view estimate refreshed, then add a fuller WordPress.org topic/reply export if one is available.",
        "target_tables": ["support_forum_archive_snapshots", "support_forum_history_quarterly"],
        "success": "Quarterly topics opened, resolved, unresolved, unanswered, reply counts, and response-age rows from a topic-level source.",
        "why": "Turns the live queue snapshot into a trend that can be compared with ticket load.",
    },
    "developer_interest_proxy": {
        "label": "Developer interest",
        "order": "5",
        "color": "violet",
        "next_step": "Keep Stack Overflow, Wikimedia, npm and Packagist package snapshots, GitHub PR activity, GitHub topic-search breadth, and GitHub review-comment activity, then add another developer-community source if a stable public source is available.",
        "target_tables": ["developer_interest_quarterly", "packagist_package_snapshot"],
        "success": "Developer-attention rows that combine help questions, public attention, package use, Composer ecosystem usage, and contribution activity.",
        "why": "Distinguishes fewer public help questions from actual developer adoption or migration.",
    },
}


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def compact(value):
    value = int(value or 0)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{value / 1_000:.1f}k"
    return f"{value:,}"


def one(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else 0


def table_exists(conn, name):
    return bool(one(conn, "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)))


def source_gap_rows(conn):
    if not table_exists(conn, "source_gaps"):
        return []
    return conn.execute(
        """
        SELECT signal, status, needed_source, note
        FROM source_gaps
        ORDER BY signal
        """
    ).fetchall()


def nav_html():
    return "\n".join(
        [
            '    <nav class="nav">',
            '      <a href="index.html#scorecard">Report scorecard</a>',
            '      <a href="index.html#goal-map">Coverage map</a>',
            '      <a href="progress_summary.html">Progress summary</a>',
            '      <a href="decision_brief.html">Decision brief</a>',
            '      <a href="project_load.html">Project load</a>',
            '      <a href="market_position.html">Market position</a>',
            '      <a href="new_site_choice.html">New-site choice</a>',
            '      <a href="search_interest.html">Search interest</a>',
            '      <a href="developer_interest.html">Developer interest</a>',
            '      <a href="job_demand.html">Job demand</a>',
            '      <a href="support_load.html">Support load</a>',
            '      <a href="contributor_depth.html">Contributor depth</a>',
            '      <a href="ecosystem_activity.html">Ecosystem activity</a>',
            '      <a href="goal_audit.html">Goal audit</a>',
            '      <a href="data_inventory.html">Data inventory</a>',
            '      <a href="refresh_runbook.html">Refresh runbook</a>',
            '      <a href="community_health.sqlite.gz">SQLite download</a>',
            "    </nav>",
        ]
    )


def plan_for(signal):
    return PLAN.get(
        signal,
        {
            "label": signal.replace("_", " ").title(),
            "order": "-",
            "color": "gray",
            "next_step": "Add the missing source and store it as a separate quarterly table.",
            "target_tables": [f"{signal}_quarterly"],
            "success": "Quarterly rows that can be regenerated from a named source.",
            "why": "Improves the source coverage map without changing existing tables.",
        },
    )


def sort_key(row):
    value = plan_for(row["signal"])["order"]
    try:
        return int(value)
    except ValueError:
        return 999


def status_counts(rows):
    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return counts


def render_cards(rows):
    cards = []
    for row in rows:
        plan = plan_for(row["signal"])
        target_tables = " ".join(f"<code>{esc(name)}</code>" for name in plan["target_tables"])
        cards.append(
            f"""
      <article class="gap-card {esc(plan['color'])}">
        <div class="gap-head">
          <span class="order">{esc(plan['order'])}</span>
          <div>
            <h2>{esc(plan['label'])}</h2>
            <p>{esc(plan['why'])}</p>
          </div>
        </div>
        <div class="gap-grid">
          <div>
            <h3>Current coverage</h3>
            <p>{esc(row['note'])}</p>
          </div>
          <div>
            <h3>Best next source</h3>
            <p>{esc(row['needed_source'])}</p>
          </div>
          <div>
            <h3>Collection step</h3>
            <p>{esc(plan['next_step'])}</p>
          </div>
          <div>
            <h3>Target tables</h3>
            <p class="targets">{target_tables}</p>
          </div>
        </div>
        <div class="success">
          <b>Done when</b>
          <span>{esc(plan['success'])}</span>
        </div>
      </article>"""
        )
    return "\n".join(cards)


def render_timeline(rows):
    items = []
    for row in rows:
        plan = plan_for(row["signal"])
        items.append(
            f"""
        <div class="timeline-item {esc(plan['color'])}">
          <span>{esc(plan['order'])}</span>
          <div>
            <strong>{esc(plan['label'])}</strong>
            <p>{esc(plan['success'])}</p>
          </div>
        </div>"""
        )
    return "\n".join(items)


def render():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = sorted(source_gap_rows(conn), key=sort_key)
        integrity = one(conn, "PRAGMA integrity_check")
        table_total = one(conn, "SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        counts = status_counts(rows)
    finally:
        conn.close()

    gap_cards = render_cards(rows)
    timeline = render_timeline(rows)
    partial_count = counts.get("partial", 0)

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress Report Source Gap Plan</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #172033;
      --muted: #637083;
      --line: #d9e1ea;
      --paper: #f6f8fb;
      --panel: #ffffff;
      --blue: #2563eb;
      --green: #159957;
      --amber: #b7791f;
      --red: #c2413b;
      --violet: #7c3aed;
      --gray: #64748b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 36px 22px 48px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(32px, 4vw, 52px); line-height: 1.05; letter-spacing: 0; }}
    h2 {{ margin: 0 0 4px; font-size: 23px; line-height: 1.15; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 12px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }}
    p {{ margin: 0; }}
    a {{ color: var(--blue); }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; overflow-wrap: anywhere; }}
    .lede {{ max-width: 920px; color: var(--muted); font-size: 18px; margin-bottom: 18px; }}
    .nav {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 18px 0 22px; }}
    .nav a {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 7px 11px;
      background: #fbfdff;
      color: var(--muted);
      font-size: 13px;
      text-decoration: none;
    }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 22px 0; }}
    .metric, .section, .gap-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
    }}
    .metric {{ padding: 16px; }}
    .metric strong {{ display: block; font-size: 31px; line-height: 1; margin: 5px 0 7px; }}
    .metric span, .note {{ color: var(--muted); font-size: 14px; }}
    .section {{ padding: 18px; margin-top: 14px; }}
    .section h2 {{ margin-bottom: 8px; }}
    .gap-stack {{ display: grid; gap: 14px; }}
    .gap-card {{ padding: 18px; border-top: 5px solid var(--gray); }}
    .gap-card.blue {{ border-top-color: var(--blue); }}
    .gap-card.green {{ border-top-color: var(--green); }}
    .gap-card.amber {{ border-top-color: var(--amber); }}
    .gap-card.red {{ border-top-color: var(--red); }}
    .gap-card.violet {{ border-top-color: var(--violet); }}
    .gap-head {{ display: grid; grid-template-columns: 46px minmax(0, 1fr); gap: 12px; align-items: start; margin-bottom: 16px; }}
    .gap-head p {{ color: var(--muted); font-size: 15px; }}
    .order {{
      width: 42px;
      height: 42px;
      display: inline-grid;
      place-items: center;
      border-radius: 50%;
      background: #eef4ff;
      color: var(--blue);
      font-weight: 850;
      font-size: 19px;
    }}
    .gap-card.green .order {{ background: #e8f8ef; color: var(--green); }}
    .gap-card.amber .order {{ background: #fff5da; color: var(--amber); }}
    .gap-card.red .order {{ background: #fff0ef; color: var(--red); }}
    .gap-card.violet .order {{ background: #f2edff; color: var(--violet); }}
    .gap-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
    .gap-grid > div {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fbfdff;
      min-width: 0;
    }}
    .gap-grid p {{ color: #2b3547; font-size: 14px; overflow-wrap: anywhere; }}
    .targets {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .targets code {{ background: #eef2f7; border-radius: 5px; padding: 3px 6px; }}
    .success {{
      display: flex;
      gap: 8px;
      align-items: baseline;
      border-top: 1px solid var(--line);
      margin-top: 14px;
      padding-top: 12px;
      color: var(--muted);
      font-size: 14px;
    }}
    .success b {{ color: var(--ink); }}
    .timeline {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }}
    .timeline-item {{
      border: 1px solid var(--line);
      border-bottom: 4px solid var(--gray);
      border-radius: 8px;
      padding: 12px;
      background: #fbfdff;
      min-width: 0;
    }}
    .timeline-item.blue {{ border-bottom-color: var(--blue); }}
    .timeline-item.green {{ border-bottom-color: var(--green); }}
    .timeline-item.amber {{ border-bottom-color: var(--amber); }}
    .timeline-item.red {{ border-bottom-color: var(--red); }}
    .timeline-item.violet {{ border-bottom-color: var(--violet); }}
    .timeline-item > span {{ display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 5px; }}
    .timeline-item strong {{ display: block; margin-bottom: 4px; }}
    .timeline-item p {{ color: var(--muted); font-size: 13px; }}
    .callout {{
      background: #eef4ff;
      border: 1px solid #cfe0ff;
      border-radius: 8px;
      padding: 14px 16px;
      margin: 18px 0 0;
      color: #244067;
    }}
    @media (max-width: 980px) {{
      .metrics, .gap-grid, .timeline {{ grid-template-columns: 1fr 1fr; }}
    }}
    @media (max-width: 640px) {{
      main {{ padding: 24px 14px 36px; }}
      .metrics, .gap-grid, .timeline {{ grid-template-columns: 1fr; }}
      .success {{ display: block; }}
      .success span {{ display: block; margin-top: 3px; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>WordPress report source gap plan</h1>
    <p class="lede">A visual collection plan for the partial-source areas already stored in <code>source_gaps</code>. This page does not change the current report status; it makes the next data pulls explicit and refreshable.</p>
{nav_html()}

    <section class="metrics" aria-label="Source gap summary">
      <div class="metric"><h3>Partial signals</h3><strong>{compact(partial_count)}</strong><span>Stored in <code>source_gaps</code>.</span></div>
      <div class="metric"><h3>Database tables</h3><strong>{compact(table_total)}</strong><span>Existing report tables remain intact.</span></div>
      <div class="metric"><h3>Integrity</h3><strong>{esc(integrity)}</strong><span>SQLite integrity check.</span></div>
      <div class="metric"><h3>Next mode</h3><strong>1 at a time</strong><span>Import, validate, then publish each source family.</span></div>
    </section>

    <section class="section">
      <h2>Collection order</h2>
      <p class="note">Start with new-site history because it most directly answers whether people still choose WordPress for new builds. Search interest and job demand are next because they broaden the demand picture beyond tickets.</p>
      <div class="timeline">{timeline}</div>
    </section>

    <section class="gap-stack" aria-label="Source gap cards">
{gap_cards}
    </section>

    <section class="section">
      <h2>Refresh workflow</h2>
      <p class="note">After each import, update the relevant generated summary table, rerun the report artifacts, and keep the gap marked partial until the new source materially improves the signal.</p>
      <p class="callout">Use <a href="refresh_runbook.html">refresh_runbook.html</a> for the command order and <a href="data_inventory.html">data_inventory.html</a> to confirm the new table count, row count, source hash, and gap status.</p>
    </section>
  </main>
</body>
</html>
"""
    OUT.write_text(html_doc, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    render()
