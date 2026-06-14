#!/usr/bin/env python3
import html
import sqlite3
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
OUT = ROOT / "data_inventory.html"


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


def table_count(conn, name):
    if not table_exists(conn, name):
        return 0
    return one(conn, f'SELECT COUNT(*) FROM "{name}"')


def source_file_rows(conn):
    if not table_exists(conn, "source_files"):
        return []
    return conn.execute(
        """
        SELECT table_name, rows, sha256, path
        FROM source_files
        ORDER BY table_name
        """
    ).fetchall()


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


def table_rows(conn):
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    return [(name, table_count(conn, name)) for name in tables]


def nav_html():
    return "\n".join(
        [
            '    <nav class="nav">',
            '      <a href="index.html#scorecard">Report scorecard</a>',
            '      <a href="index.html#goal-map">Coverage map</a>',
            '      <a href="work_so_far.html">Work so far</a>',
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
            '      <a href="source_gap_plan.html">Source gap plan</a>',
            '      <a href="refresh_runbook.html">Refresh runbook</a>',
            '      <a href="community_health.sqlite.gz">SQLite download</a>',
            "    </nav>",
        ]
    )


def source_cards(rows):
    return "\n".join(
        f"""
        <article class="source-card">
          <strong><code>{esc(row['table_name'])}</code></strong>
          <div class="meta"><span>Rows</span><b>{compact(row['rows'])}</b></div>
          <div class="meta"><span>Hash prefix</span><code>{esc(str(row['sha256'])[:12])}</code></div>
          <p><code>{esc(row['path'])}</code></p>
        </article>"""
        for row in rows
    )


def gap_cards(rows):
    return "\n".join(
        f"""
        <article class="gap-card">
          <span class="status">{esc(row['status'])}</span>
          <strong>{esc(row['signal'].replace('_', ' ').title())}</strong>
          <b>Best next source</b>
          <p>{esc(row['needed_source'])}</p>
          <b>Current coverage</b>
          <p>{esc(row['note'])}</p>
        </article>"""
        for row in rows
    )


def evidence_cards(items):
    return "\n".join(
        f"""
        <article class="evidence-card">
          <strong><code>{esc(name)}</code></strong>
          <div class="meta"><span>Rows</span><b>{compact(count)}</b></div>
          <p>{esc(note)}</p>
        </article>"""
        for name, count, note in items
    )


def family_cards(items):
    return "\n".join(
        f"""
        <article class="family-card">
          <strong><code>{esc(name)}</code></strong>
          <p>{esc(note)}</p>
        </article>"""
        for name, note in items
    )


def render():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    integrity = one(conn, "PRAGMA integrity_check")
    tables = table_rows(conn)
    sources = source_file_rows(conn)
    gaps = source_gap_rows(conn)

    core_tickets = table_count(conn, "core_tickets")
    gutenberg_issues = table_count(conn, "gutenberg_issues")
    github_prs = table_count(conn, "github_prs")
    ticket_total = core_tickets + gutenberg_issues

    table_cards = "\n".join(
        f'<div class="table-chip"><code>{esc(name)}</code><span>{compact(count)} rows</span></div>'
        for name, count in tables
    )
    strongest_rows = [
        ("core_tickets", core_tickets, "Core Trac ticket rows."),
        ("core_events", table_count(conn, "core_events"), "Core Trac event rows."),
        ("gutenberg_issues", gutenberg_issues, "Gutenberg GitHub issue rows."),
        ("github_prs", github_prs, "wordpress-develop pull request rows."),
        ("classification_trend", table_count(conn, "classification_trend"), "Quarterly classification rows."),
    ]
    external_rows = [
        ("market_share", "W3Techs all-site and CMS-share trend rows."),
        ("http_archive_*", "Origin counts, tracked-share trend, rank tiers, and Core Web Vitals."),
        ("builtwith_*", "Current new-site proxy, tier snapshot, and ecommerce history."),
        ("make_core_*", "Make/Core posts, comments, dev notes, authors, and release tags."),
        ("major_plugin_*", "Major plugin installs, historical snapshots, support counts, and downloads."),
        ("plugin_search_snapshot", "Current WordPress.org plugin search-result counts and top matching plugins by category."),
        ("theme_search_snapshot", "Current WordPress.org theme search-result counts and top matching themes by site category."),
        ("packagist_package_snapshot", "Current Composer package downloads, favorites, dependents, and release timestamps."),
        ("github_repo_search_snapshot", "Current GitHub repository-search totals and top matching repositories for selected WordPress ecosystem topics."),
        ("remotive_*", "Current Remotive job snapshot with term summaries and matching rows."),
    ]

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress Report Data Inventory</title>
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
    .lede {{ max-width: 900px; color: var(--muted); font-size: 18px; margin-bottom: 18px; }}
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
    .grid {{ display: grid; gap: 14px; }}
    .metrics {{ grid-template-columns: repeat(5, minmax(0, 1fr)); margin: 22px 0; }}
    .metric, .card, .section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
    }}
    .metric strong {{ display: block; font-size: 30px; line-height: 1; margin: 4px 0 7px; }}
    .metric span, .note {{ color: var(--muted); font-size: 14px; }}
    .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .commands {{ display: grid; gap: 8px; margin-top: 8px; }}
    .command {{
      border: 1px solid var(--line);
      border-left: 4px solid var(--blue);
      border-radius: 8px;
      padding: 10px 12px;
      background: #fbfdff;
    }}
    .command b {{ display: block; margin-bottom: 4px; }}
    .command code {{ display: block; white-space: normal; }}
    .table-list {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px; }}
    .table-chip {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      background: #fbfdff;
      min-width: 0;
    }}
    .table-chip code, .table-chip span {{ display: block; }}
    .table-chip span {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}
    .evidence-grid, .family-grid, .source-grid, .gap-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      margin-top: 12px;
    }}
    .evidence-card, .family-card, .source-card, .gap-card {{
      border: 1px solid var(--line);
      border-left: 5px solid var(--blue);
      border-radius: 8px;
      padding: 12px;
      background: #fbfdff;
      min-width: 0;
    }}
    .family-card {{ border-left-color: var(--green); }}
    .source-card {{ border-left-color: var(--blue); }}
    .gap-card {{ border-left-color: var(--amber); }}
    .evidence-card strong, .family-card strong, .source-card strong, .gap-card strong {{
      display: block;
      line-height: 1.25;
      margin-bottom: 8px;
    }}
    .evidence-card p, .family-card p, .source-card p, .gap-card p {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.4;
      margin: 0;
    }}
    .source-card p {{ margin-top: 8px; }}
    .gap-card b {{
      display: block;
      color: var(--ink);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .06em;
      margin: 11px 0 4px;
    }}
    .meta {{ display: flex; justify-content: space-between; gap: 10px; color: var(--muted); font-size: 13px; margin-top: 5px; }}
    .meta b {{ color: var(--ink); }}
    .status {{ display: inline-block; border-radius: 999px; padding: 3px 8px; font-size: 12px; font-weight: 800; background: #fef3c7; color: #92400e; }}
    .section {{ margin-top: 14px; }}
    @media (max-width: 860px) {{
      main {{ padding: 24px 14px 36px; }}
      .metrics, .cards {{ grid-template-columns: 1fr; }}
      table {{ font-size: 13px; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>WordPress report data inventory</h1>
    <p class="lede">A compact map of the SQLite database behind the WordPress Community & Adoption Health report. Use this to see what data is already stored, what local source files are hashed, and which source areas remain partial.</p>
    {nav_html()}

    <section class="grid metrics" aria-label="Database summary">
      <div class="metric"><h3>Tables</h3><strong>{compact(len(tables))}</strong><span>SQLite tables in the report database.</span></div>
      <div class="metric"><h3>Local sources</h3><strong>{compact(len(sources))}</strong><span>Imported files with SHA-256 hashes.</span></div>
      <div class="metric"><h3>Tickets/issues</h3><strong>{compact(ticket_total)}</strong><span>Core Trac tickets plus Gutenberg issues.</span></div>
      <div class="metric"><h3>Pull requests</h3><strong>{compact(github_prs)}</strong><span>wordpress-develop GitHub PR records.</span></div>
      <div class="metric"><h3>Integrity</h3><strong>{esc(integrity)}</strong><span>SQLite integrity check result.</span></div>
    </section>

    <section class="grid cards">
      <div class="card">
        <h2>Tracker and PR data</h2>
        <p class="note">The strongest evidence in the report: direct project workload and participation history.</p>
        <div class="evidence-grid">
{evidence_cards(strongest_rows)}
        </div>
      </div>
      <div class="card">
        <h2>External signal families</h2>
        <p class="note">These tables keep ticket activity separate from ecosystem, adoption, and demand signals.</p>
        <div class="family-grid">
{family_cards(external_rows)}
        </div>
      </div>
    </section>

    <section class="section">
      <h2>Refresh this inventory</h2>
      <p class="note">Run this after the report database changes so table counts, source hashes, and partial-source gaps stay synchronized with SQLite.</p>
      <div class="commands">
        <div class="command">
          <b>Check the database</b>
          <code>sqlite3 community_health.sqlite "PRAGMA integrity_check; SELECT count(*) FROM sqlite_master WHERE type='table';"</code>
        </div>
        <div class="command">
          <b>Regenerate the inventory</b>
          <code>python3 make_data_inventory.py</code>
        </div>
        <div class="command">
          <b>Publish with the report</b>
          <code>cp data_inventory.html make_data_inventory.py decision_brief.html make_decision_brief.py progress_summary.html make_progress_summary.py work_so_far.html make_work_so_far.py project_load.html make_project_load_report.py market_position.html make_market_position_report.py new_site_choice.html make_new_site_choice_report.py search_interest.html make_search_interest_report.py developer_interest.html make_developer_interest_report.py job_demand.html make_job_demand_report.py support_load.html make_support_load_report.py contributor_depth.html make_contributor_depth_report.py ecosystem_activity.html make_ecosystem_activity_report.py source_gap_plan.html make_source_gap_plan.py goal_audit.html make_goal_audit.py refresh_report_artifacts.py /Users/admin/sqlite-database-integration-pages/wordpress-community-health/</code>
        </div>
      </div>
    </section>

    <section class="section">
      <h2>Full table list</h2>
      <p class="note">Generated from <code>sqlite_master</code>; row counts are current for this local database.</p>
      <div class="table-list">{table_cards}</div>
    </section>

    <section class="section">
      <h2>Hashed local sources</h2>
      <p class="note">The database stores full SHA-256 values. This page shows shortened hashes to keep the inventory readable.</p>
      <div class="source-grid">
{source_cards(sources)}
      </div>
    </section>

    <section class="section">
      <h2>Partial-source gaps stored in SQLite</h2>
      <div class="gap-grid">
{gap_cards(gaps)}
      </div>
    </section>
  </main>
</body>
</html>
"""
    OUT.write_text(html_doc, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    render()
