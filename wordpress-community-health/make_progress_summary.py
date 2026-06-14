#!/usr/bin/env python3
import html
import sqlite3
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
OUT = ROOT / "progress_summary.html"


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
        return f"{value / 1_000:.0f}k"
    return f"{value:,}"


def value(conn, sql, params=(), default=0):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else default


def values(conn, sql, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def quarter_label(value_):
    value_ = str(value_ or "")
    if value_.endswith("-01-01"):
        return f"Q1 {value_[:4]}"
    if value_.endswith("-04-01"):
        return f"Q2 {value_[:4]}"
    if value_.endswith("-07-01"):
        return f"Q3 {value_[:4]}"
    if value_.endswith("-10-01"):
        return f"Q4 {value_[:4]}"
    return value_ or "latest quarter"


def card(label, metric, small, note, bar_class="green", width=90):
    return f"""
      <div class="card">
        <h3>{esc(label)}</h3>
        <div class="metric">{esc(metric)} <small>{esc(small)}</small></div>
        <p class="note">{esc(note)}</p>
        <div class="bar {esc(bar_class)}"><span style="width:{max(2, min(100, num(width))):.0f}%"></span></div>
      </div>"""


def link_card(title, text, href, tone=""):
    return f"""
      <a class="linkcard {esc(tone)}" href="{esc(href)}">
        <strong>{esc(title)}</strong>
        <span>{esc(text)}</span>
      </a>"""


def timeline_item(label, body):
    return f"""
          <div class="item">
            <div class="date">{esc(label)}</div>
            <div><p>{body}</p></div>
          </div>"""


GAP_SUMMARIES = {
    "developer_interest_proxy": {
        "title": "Developer interest",
        "current": "Stack Overflow, Wikimedia, npm downloads, Packagist Composer package snapshots, GitHub PRs, GitHub review comments, repository-interest snapshots, and GitHub topic-search breadth are in.",
        "next": "Add another stable developer-community source if available.",
    },
    "job_demand": {
        "title": "Hiring demand",
        "current": "HN hiring threads, Remote OK current jobs, and WordPress Jobs snapshots are in.",
        "next": "Add a broad hiring-platform export.",
    },
    "new_site_share_history": {
        "title": "New-site history",
        "current": "BuiltWith current pipeline and HTTP Archive proxies are in.",
        "next": "Add a true first-seen site cohort.",
    },
    "search_interest": {
        "title": "Search interest",
        "current": "Wikimedia, Stack Overflow, and current autocomplete query-intent proxies are in.",
        "next": "Add Google Trends or a similar search-provider export.",
    },
    "support_forum_history": {
        "title": "Support history",
        "current": "Current support queues and unresolved snapshots are in.",
        "next": "Add long-running topic and reply history.",
    },
}


def tone_for_status(status):
    return "amber" if "partial" in str(status).lower() else "green"


def status_badge(status):
    tone = tone_for_status(status)
    return f'<span class="badge {esc(tone)}">{esc(status)}</span>'


def state_cards(items):
    return "\n".join(
        f"""
          <div class="statecard {esc(tone_for_status(state))}">
            <strong>{esc(label)}</strong>
            <span>{esc(state)}</span>
          </div>"""
        for label, state in items
    )


def coverage_cards(items):
    return "\n".join(
        f"""
          <div class="coveragecard {esc(tone_for_status(item[2]))}">
            {status_badge(item[2])}
            <strong>{esc(item[0])}</strong>
            <p>{item[1]}</p>
          </div>"""
        for item in items
    )


def gap_cards(rows):
    cards = []
    for row in rows:
        signal = row["signal"]
        summary = GAP_SUMMARIES.get(
            signal,
            {
                "title": signal.replace("_", " ").title(),
                "current": row["note"],
                "next": row["needed_source"],
            },
        )
        cards.append(
            f"""
          <div class="gapcard">
            <strong>{esc(summary["title"])}</strong>
            <span>{esc(summary["current"])}</span>
            <b>Best next source</b>
            <span>{esc(summary["next"])}</span>
          </div>"""
        )
    return "\n".join(cards)


def source_strength_bar(label, width, tone="green"):
    return f"""
          <div class="strength">
            <div><strong>{esc(label)}</strong><span>{max(2, min(100, num(width))):.0f}%</span></div>
            <div class="bar {esc(tone)}"><span style="width:{max(2, min(100, num(width))):.0f}%"></span></div>
          </div>"""


def source_strength_bars():
    items = [
        ("Ticket history", 96, "green"),
        ("Ecosystem snapshots", 76, "green"),
        ("Market share history", 72, "green"),
        ("New-site choice", 48, "amber"),
        ("Hiring and search interest", 44, "amber"),
    ]
    return "\n".join(
        source_strength_bar(label, width, tone) for label, width, tone in items
    )


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        table_count = value(conn, "SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        core_count = value(conn, "SELECT COUNT(*) FROM core_tickets")
        gut_count = value(conn, "SELECT COUNT(*) FROM gutenberg_issues")
        source_gaps = value(conn, "SELECT COUNT(*) FROM source_gaps")
        partial_gaps = value(conn, "SELECT COUNT(*) FROM source_gaps WHERE status='partial'")
        npm_quarter = value(conn, "SELECT MAX(quarter) FROM npm_wordpress_downloads_quarterly", default="")
        npm_downloads = value(
            conn,
            "SELECT SUM(CAST(downloads AS REAL)) FROM npm_wordpress_downloads_quarterly WHERE quarter=?",
            (npm_quarter,),
        )
        theme_count = value(conn, "SELECT COUNT(DISTINCT slug) FROM theme_directory_activity_sample")
        gaps = values(conn, "SELECT signal, needed_source, note FROM source_gaps ORDER BY signal")
    finally:
        conn.close()

    ticket_total = num(core_count) + num(gut_count)
    link_cards = "".join(
        [
            link_card("Relevance scorecard", "Short decision view: still in a good place, with softer momentum.", "index.html#scorecard", "green"),
            link_card("Decision Questions", "Seven plain-English answers mapped to the exact questions from goal.md.", "index.html#decision-questions", "green"),
            link_card("Goal coverage map", "Separates strong quarterly evidence from snapshots and proxies.", "index.html#goal-map"),
            link_card("Project load", "Compact flow, backlog age, response, closure, and category readout.", "project_load.html", "amber"),
            link_card("Contributor depth", "Drive-by, repeat, regular, and sustained participation readout.", "contributor_depth.html", "green"),
            link_card("Market position", "Installed-share, current new-site proxy, and demand direction readout.", "market_position.html", "amber"),
            link_card("New-site choice", "Current newly found-site, recurring crawl, and traffic-tier readout.", "new_site_choice.html", "amber"),
            link_card("Developer interest", "Help-seeking, public attention, npm and Packagist packages, GitHub topic breadth, hiring proxies, PR flow, and review-comment activity.", "developer_interest.html", "amber"),
            link_card("Search interest", "Wikimedia pageviews, Stack Overflow questions, and autocomplete query-intent snapshots.", "search_interest.html", "amber"),
            link_card("Job demand", "HN hiring mentions, Remote OK current jobs, WordPress Jobs snapshots, and jobs-board categories.", "job_demand.html", "amber"),
            link_card("Ecosystem activity", "Non-ticket community channels, plugin and theme breadth, and current ecosystem snapshots.", "ecosystem_activity.html", "green"),
            link_card("Support load", "Current support queues, forum load, age buckets, and major-plugin support counts.", "support_load.html", "amber"),
            link_card("Decision brief", "SQLite-generated one-page summary for quick sharing and review.", "decision_brief.html", "amber"),
            link_card("Goal audit", "Maps goal.md requirements to report sections, evidence, and source gaps.", "goal_audit.html"),
            link_card("Data inventory", "SQLite tables, source hashes, and partial-source gaps.", "data_inventory.html"),
            link_card("Source gap plan", "Visual collection order for the five remaining partial signals.", "source_gap_plan.html", "amber"),
            link_card("Refresh runbook", "How to refresh safely, including low-disk constraints.", "refresh_runbook.html"),
        ]
    )

    timeline = "".join(
        [
            timeline_item("Plan", "Wrote <code>goal.md</code>: a visual report on WordPress participation, project load, and market position."),
            timeline_item("Tickets", "Built quarterly Core Trac and Gutenberg GitHub metrics for new/closed flow, backlog, reporters, first-time reporters, bug/feature mix, response time, closure time, stale share, and contributor concentration."),
            timeline_item("Classification", "Loaded bug, feature request, documentation, support, and other classification outputs into the SQLite-backed pipeline."),
            timeline_item("Ecosystem", "Added Core release credits and committers, Make/Core posts and comments, dev notes, WordCamps, events, translation snapshots, Five for the Future, support snapshots, plugin/theme directory samples, plugin and theme search breadth, major plugin stats, and enterprise case studies."),
            timeline_item("Adoption", "Added W3Techs, HTTP Archive, BuiltWith, WordPress.org stats, Stack Overflow, Wikimedia, autocomplete query-intent snapshots, Packagist Composer package snapshots, GitHub topic-search breadth, Hacker News hiring threads, Remote OK current jobs, WordPress Jobs snapshots, compact new-site summaries, and attention/demand proxy summaries."),
            timeline_item("Companions", 'Added focused pages for <a href="project_load.html">Project Load</a>, <a href="market_position.html">Market Position</a>, <a href="new_site_choice.html">New-site Choice</a>, <a href="search_interest.html">Search Interest</a>, <a href="developer_interest.html">Developer Interest</a>, <a href="job_demand.html">Job Demand</a>, <a href="support_load.html">Support Load</a>, <a href="contributor_depth.html">Contributor Depth</a>, <a href="ecosystem_activity.html">Ecosystem Activity</a>, and <a href="source_gap_plan.html">Source Gap Plan</a>.'),
            timeline_item("Decision brief", "Added <code>make_decision_brief.py</code> so installed share, current new-site proxy, closure ratios, first-time reporter retention, backlog age, contributor concentration, npm package downloads, and theme sample counts regenerate from SQLite."),
            timeline_item("Progress summary", "Added <code>make_progress_summary.py</code> so this progress page is regenerated from SQLite counts and the current report artifact list."),
            timeline_item("Refresh", "Updated <code>refresh_report_artifacts.py</code> so the main report, focused companion pages, generated decision brief, generated progress summary, source gap plan, goal audit, and data inventory can be rebuilt and validated in order."),
            timeline_item("Publishing", 'Published the GitHub Pages report as <a href="index.html">index.html</a>, with <a href="community_health.sqlite.gz">community_health.sqlite.gz</a> for the supporting database export.'),
        ]
    )

    current_state = state_cards(
        [
            ("Ticket participation", "Implemented with quarterly charts."),
            ("Project load", "Implemented with flow, backlog, response, closure, reopen, and age charts."),
            ("Market position", "Implemented with all-site/CMS share, HTTP Archive, BuiltWith, traffic tiers, competitor signals, and compact demand summaries."),
            ("Refreshability", "Generated companion pages, source metadata, source gaps, and a compressed database export."),
        ]
    )

    coverage_grid = coverage_cards(
        [
            ("Three report views", 'Participation, Project Load, and Market Position sections in <a href="index.html">index.html</a>.', "Covered"),
            ("Ticket-derived participation and load", "Quarterly Core Trac, Gutenberg, and wordpress-develop PR charts for flow, reporters, response, closure, reopen, stale share, and concentration.", "Covered"),
            ("Bug, feature request, and all-ticket views", "Separate Core and Gutenberg line charts plus open-backlog category summaries.", "Covered"),
            ("Community outside tickets", "Release credits, committers, Make/Core, WordCamp, Events, Translate, Five for the Future, support snapshots and answer summaries, plugin/theme directory, plugin and theme search breadth, stale popular plugins, and enterprise case studies.", "Covered with snapshots"),
            ("Market position and adoption", "W3Techs installed share, HTTP Archive origin and tracked-share trends, BuiltWith pipeline/tier data, plugin install/download history, WooCommerce, and compact new-site plus attention/demand proxy summaries.", "Covered with proxies for new-site and demand history"),
            ("Decision questions", '<a href="index.html#decision-questions">Seven plain-English answer cards</a> plus final evidence-strength and decision readout sections.', "Covered"),
            ("Short visual decision readout", "Relevance Scorecard, Goal Coverage Map, generated Decision Brief, and final Decision Readout.", "Covered"),
            ("Refresh metadata", "SQLite source hashes, source_gaps, generated data inventory, generated decision brief, generated progress summary, generator scripts, cached public-source tables, and compressed DB export.", "Covered"),
            ("Remaining ideal sources", "True multi-year new-site cohorts, Google Trends or equivalent, multi-year labor-market exports, fuller support-forum history, and another developer-community source if a stable public source is available.", "Partial by design"),
        ]
    )

    next_grid = gap_cards(gaps)
    strength_bars = source_strength_bars()

    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress Relevance Report Progress</title>
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
    h2 {{ margin: 0 0 14px; font-size: 22px; }}
    h3 {{ margin: 0 0 8px; font-size: 15px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }}
    p {{ margin: 0; }}
    a {{ color: var(--blue); }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; overflow-wrap: anywhere; }}
    .lede {{ max-width: 900px; color: var(--muted); font-size: 18px; margin-bottom: 24px; }}
    .grid {{ display: grid; gap: 14px; }}
    .cards {{ grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 22px 0; }}
    .two {{ grid-template-columns: 1.05fr .95fr; align-items: start; }}
    .card, .section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
    }}
    .metric {{ font-size: 32px; font-weight: 760; line-height: 1; margin: 4px 0 8px; }}
    .metric small {{ font-size: 15px; color: var(--muted); font-weight: 650; }}
    .note {{ color: var(--muted); font-size: 14px; }}
    .bar {{ height: 9px; border-radius: 999px; background: #e7edf5; overflow: hidden; margin-top: 14px; }}
    .bar span {{ display: block; height: 100%; border-radius: inherit; background: var(--blue); }}
    .bar.green span {{ background: var(--green); }}
    .bar.amber span {{ background: var(--amber); }}
    .timeline {{ display: grid; gap: 12px; margin-top: 6px; }}
    .item {{ display: grid; grid-template-columns: 130px 1fr; gap: 14px; padding-bottom: 12px; border-bottom: 1px solid var(--line); }}
    .item:last-child {{ border-bottom: 0; padding-bottom: 0; }}
    .date {{ font-weight: 750; color: var(--blue); }}
    .pillrow {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
    .pill {{ border: 1px solid var(--line); border-radius: 999px; padding: 6px 10px; background: #fbfdff; font-size: 13px; color: var(--muted); text-decoration: none; }}
    .linkcards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin: 18px 0; }}
    .linkcard {{
      display: block;
      color: inherit;
      text-decoration: none;
      background: var(--panel);
      border: 1px solid var(--line);
      border-top: 5px solid var(--blue);
      border-radius: 8px;
      padding: 14px;
      min-height: 126px;
    }}
    .linkcard.green {{ border-top-color: var(--green); }}
    .linkcard.amber {{ border-top-color: var(--amber); }}
    .linkcard strong {{ display: block; font-size: 18px; line-height: 1.2; margin-bottom: 7px; }}
    .linkcard span {{ color: var(--muted); font-size: 14px; }}
    ul {{ margin: 10px 0 0; padding-left: 20px; }}
    li + li {{ margin-top: 6px; }}
    .status {{ display: inline-flex; align-items: center; gap: 7px; font-weight: 750; }}
    .dot {{ width: 10px; height: 10px; border-radius: 50%; background: var(--green); }}
    .mini-grid, .coveragegrid, .gapcards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; margin-top: 12px; }}
    .statecard, .coveragecard, .gapcard {{
      min-width: 0;
      border: 1px solid var(--line);
      border-left: 5px solid var(--blue);
      border-radius: 8px;
      background: #fbfdff;
      padding: 13px;
    }}
    .statecard.green, .coveragecard.green {{ border-left-color: var(--green); }}
    .statecard.amber, .coveragecard.amber, .gapcard {{ border-left-color: var(--amber); }}
    .statecard strong, .coveragecard strong, .gapcard strong {{ display: block; font-size: 15px; line-height: 1.25; margin-bottom: 6px; }}
    .statecard span, .coveragecard p, .gapcard span {{ display: block; color: var(--muted); font-size: 14px; line-height: 1.4; }}
    .gapcard b {{ display: block; margin-top: 12px; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--ink); }}
    .badge {{ display: inline-flex; border-radius: 999px; padding: 4px 8px; margin-bottom: 8px; background: #eef8f1; color: var(--green); font-size: 12px; font-weight: 750; }}
    .badge.amber {{ background: #fff7ed; color: var(--amber); }}
    .strength {{ margin-top: 12px; }}
    .strength div:first-child {{ display: flex; justify-content: space-between; gap: 12px; color: var(--muted); font-size: 13px; }}
    .strength strong {{ color: var(--ink); }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 14px; table-layout: fixed; }}
    th, td {{ text-align: left; border-bottom: 1px solid var(--line); padding: 9px 8px; vertical-align: top; overflow-wrap: anywhere; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }}
    @media (max-width: 820px) {{
      main {{ padding: 24px 14px 36px; }}
      .cards, .two, .linkcards {{ grid-template-columns: 1fr; }}
      .item {{ grid-template-columns: 1fr; gap: 3px; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>WordPress relevance report progress</h1>
    <p class="lede">This is the working state as of June 14, 2026. The active direction is the WordPress Community & Adoption Health report, not the SQLite benchmark runner. The public report opens with a decision scorecard, a Decision Questions checklist, visible data-source strength, a SQLite-generated decision brief, and this SQLite-generated progress summary.</p>

    <section class="grid cards">
{card("Database", compact(table_count), "tables", "SQLite stores imported ticket data, fetched ecosystem data, theme breadth, npm, Packagist, and GitHub topic snapshots, source hashes, generated summaries, and known source gaps.", "green", 92)}
{card("Ticket records", compact(ticket_total), "items", f"{compact(core_count)} Core Trac tickets plus {compact(gut_count)} Gutenberg GitHub issues are loaded for quarterly analysis.", "green", 96)}
{card("Package signal", compact(npm_downloads), quarter_label(npm_quarter), "Tracked @wordpress npm package downloads add developer/package activity beyond help-question volume.", "green", 78)}
{card("Known gaps", compact(partial_gaps), f"of {compact(source_gaps)} partial", "Remaining ideal sources are true new-site history, search-provider data, broad hiring demand, longer support history, and another stable developer-community source.", "amber", 35)}
    </section>

    <section class="linkcards" aria-label="Current public report links">
{link_cards}
    </section>

    <section class="grid two">
      <div class="section">
        <h2>What has been done</h2>
        <div class="timeline">
{timeline}
        </div>
      </div>

      <div class="section">
        <h2>Current report coverage</h2>
        <p class="status"><span class="dot"></span> Strong local evidence</p>
        <ul>
          <li>Quarterly Core Trac history since 2003.</li>
          <li>Quarterly Gutenberg GitHub issue history.</li>
          <li>Bug vs feature request trends for Core and Gutenberg.</li>
          <li>Contributor concentration, first-time vs repeat reporters, and maintainer participation.</li>
          <li>Top-level evidence lanes and a visual decision readout with direct answers to the seven goal questions.</li>
        </ul>
        <div class="pillrow">
          <span class="pill">community_health.sqlite</span>
          <span class="pill">final_report.html</span>
          <span class="pill">index.html</span>
          <span class="pill">community_health.sqlite.gz</span>
          <span class="pill">Decision Questions</span>
          <span class="pill">make_decision_brief.py</span>
          <span class="pill">make_progress_summary.py</span>
          <span class="pill">scorecard</span>
          <span class="pill">coverage map</span>
          <span class="pill">project load</span>
          <span class="pill">market position</span>
          <span class="pill">contributor depth</span>
          <span class="pill">ecosystem activity</span>
          <span class="pill">goal audit</span>
          <span class="pill">data inventory</span>
        </div>
        <div class="mini-grid">
{current_state}
        </div>
      </div>
    </section>

    <section class="section" style="margin-top:14px">
      <h2>Goal coverage checklist</h2>
      <p class="note">This maps the current artifacts back to goal.md. Items marked partial are present in the report, but rely on proxies or snapshots rather than the ideal broad historical source.</p>
      <div class="coveragegrid">
{coverage_grid}
      </div>
    </section>

    <section class="section" style="margin-top:14px">
      <h2>Next report work</h2>
      <p>The next useful work is to deepen the partial-source areas. The current report labels those areas as proxies or partial coverage, and the source gap plan records the target tables.</p>
      <div class="pillrow">
        <span class="pill">Next: true new-site history</span>
        <span class="pill">Next: search-interest data</span>
        <span class="pill">Next: broader hiring demand</span>
        <span class="pill">Later: support history export</span>
        <a class="pill" href="decision_brief.html">Decision brief</a>
        <a class="pill" href="source_gap_plan.html">Source gap plan</a>
        <a class="pill" href="refresh_runbook.html">Refresh runbook</a>
      </div>
      <div class="gapcards">
{next_grid}
      </div>
      <div class="strengthwrap">
{strength_bars}
      </div>
      <p class="note" style="margin-top:10px">Disk is currently very tight, so the next data pull should either free local cache space first or import one source at a time and checkpoint SQLite after each refresh.</p>
    </section>
  </main>
</body>
</html>
"""
    OUT.write_text(html_text, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
