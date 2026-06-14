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
            '      <a href="progress_summary.html">Progress summary</a>',
            '      <a href="decision_brief.html">Decision brief</a>',
            '      <a href="project_load.html">Project load</a>',
            '      <a href="market_position.html">Market position</a>',
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

    source_rows = "\n".join(
        f"""
          <tr>
            <td><code>{esc(row['table_name'])}</code></td>
            <td>{compact(row['rows'])}</td>
            <td><code>{esc(str(row['sha256'])[:12])}</code></td>
            <td><code>{esc(row['path'])}</code></td>
          </tr>"""
        for row in sources
    )
    gap_rows = "\n".join(
        f"""
          <tr>
            <td><code>{esc(row['signal'])}</code></td>
            <td><span class="status">{esc(row['status'])}</span></td>
            <td>{esc(row['needed_source'])}</td>
            <td>{esc(row['note'])}</td>
          </tr>"""
        for row in gaps
    )
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
    strongest_html = "\n".join(
        f"<tr><td><code>{esc(name)}</code></td><td>{compact(count)}</td><td>{esc(note)}</td></tr>"
        for name, count, note in strongest_rows
    )

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
    table {{ width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 14px; table-layout: fixed; }}
    th, td {{ text-align: left; border-bottom: 1px solid var(--line); padding: 9px 8px; vertical-align: top; overflow-wrap: anywhere; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }}
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
        <table>
          <thead><tr><th>Table</th><th>Rows</th><th>Use</th></tr></thead>
          <tbody>{strongest_html}</tbody>
        </table>
      </div>
      <div class="card">
        <h2>External signal families</h2>
        <p class="note">These tables keep ticket activity separate from ecosystem, adoption, and demand signals.</p>
        <table>
          <tbody>
            <tr><td><code>market_share</code></td><td>W3Techs all-site and CMS-share trend rows.</td></tr>
            <tr><td><code>http_archive_*</code></td><td>Origin counts, tracked-share trend, rank tiers, and Core Web Vitals.</td></tr>
            <tr><td><code>builtwith_*</code></td><td>Current new-site proxy, tier snapshot, and ecommerce history.</td></tr>
            <tr><td><code>make_core_*</code></td><td>Make/Core posts, comments, dev notes, authors, and release tags.</td></tr>
            <tr><td><code>major_plugin_*</code></td><td>Major plugin installs, historical snapshots, support counts, and downloads.</td></tr>
          </tbody>
        </table>
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
          <code>cp data_inventory.html make_data_inventory.py project_load.html make_project_load_report.py market_position.html make_market_position_report.py search_interest.html make_search_interest_report.py developer_interest.html make_developer_interest_report.py job_demand.html make_job_demand_report.py support_load.html make_support_load_report.py contributor_depth.html make_contributor_depth_report.py ecosystem_activity.html make_ecosystem_activity_report.py source_gap_plan.html make_source_gap_plan.py goal_audit.html make_goal_audit.py refresh_report_artifacts.py /Users/admin/sqlite-database-integration-pages/wordpress-community-health/</code>
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
      <table>
        <thead><tr><th>Table</th><th>Rows</th><th>SHA-256 prefix</th><th>Source path</th></tr></thead>
        <tbody>{source_rows}</tbody>
      </table>
    </section>

    <section class="section">
      <h2>Partial-source gaps stored in SQLite</h2>
      <table>
        <thead><tr><th>Signal</th><th>Status</th><th>Best next source</th><th>Current note</th></tr></thead>
        <tbody>{gap_rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""
    OUT.write_text(html_doc, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    render()
