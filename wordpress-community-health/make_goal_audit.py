#!/usr/bin/env python3
import html
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from string import Template


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
OUT = ROOT / "goal_audit.html"


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


def audit_row(title, prompt, status, detail, class_name="covered"):
    status_class = "partial" if class_name == "partial" else "covered"
    row_class = " partial-row" if class_name == "partial" else ""
    return f"""
      <div class="audit-row{row_class}">
        <div><strong>{esc(title)}</strong><p>{esc(prompt)}</p></div>
        <div><span class="status {status_class}">{esc(status)}</span></div>
        <div><p>{detail}</p></div>
      </div>"""


def gap_table_rows(gaps):
    return "\n".join(
        f"""
          <tr>
            <td><code>{esc(row['signal'])}</code></td>
            <td><span class="status partial">{esc(row['status'])}</span></td>
            <td>{esc(row['needed_source'])}</td>
            <td>{esc(row['note'])}</td>
          </tr>"""
        for row in gaps
    )


def render():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    table_total = one(conn, "SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
    source_file_total = table_count(conn, "source_files")
    gaps = source_gap_rows(conn)
    source_gap_total = len(gaps)
    core_tickets = table_count(conn, "core_tickets")
    gutenberg_issues = table_count(conn, "gutenberg_issues")
    github_prs = table_count(conn, "github_prs")
    classification_rows = table_count(conn, "classification_trend")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rows = [
        audit_row(
            "HTML progress summary",
            "Summarize what has been done so far.",
            "Covered",
            '<a href="progress_summary.html">progress_summary.html</a> summarizes the work, links current artifacts, and includes the latest Decision Questions update.',
        ),
        audit_row(
            "Visual decision report",
            "Explain community involvement, project workload, and market position.",
            "Covered",
            '<a href="index.html">index.html</a> contains the three main views, a relevance scorecard, a Goal Coverage Map, Source Coverage, and a final Decision Readout.',
        ),
        audit_row(
            "Separate evidence lanes",
            "Do not treat tickets as the whole community.",
            "Covered",
            "The report separates ticket-derived signals, ecosystem signals, and adoption/demand signals at the top of the page.",
        ),
        audit_row(
            "Ticket participation and load",
            "New, closed, net flow, reporters, first-time, repeat, maintainer split, response, close time, reopen, stale share, concentration, drive-by vs sustained.",
            "Covered",
            f"{compact(core_tickets)} Core tickets, {compact(gutenberg_issues)} Gutenberg issues, and {compact(github_prs)} wordpress-develop PRs are loaded. The report uses quarterly Core, Gutenberg, PR, timeline, response, reopen, concentration, and depth tables.",
        ),
        audit_row(
            "Bug and feature mix",
            "Show bugs, feature requests, and all tickets/issues separately where useful.",
            "Covered",
            f"The classification trend contains {compact(classification_rows)} quarterly category rows, with separate Core and Gutenberg category charts plus open-backlog category summaries.",
        ),
        audit_row(
            "Community outside tickets",
            "Props, committers, Make/Core, WordCamps, Meetups, plugins, themes, translations, Five for the Future, support, dev notes.",
            "Covered",
            "The report includes release credits, committers, Make/Core posts/comments/dev notes, WordCamp records, Events/Meetups, Translate snapshots, Five for the Future, support answer summaries, plugin/theme directory activity, and a stale popular-plugin sample.",
        ),
        audit_row(
            "Popularity and likelihood to choose WordPress",
            "Installed share, CMS share, newly detected sites, traffic tiers, peer builders, demand signals, plugins, WooCommerce, enterprise.",
            "Mixed",
            "Installed-share and CMS-share evidence is direct. Newly detected sites, search interest, and broad job demand are presented with public proxies, including compact new-site and attention/demand summaries, and clearly labeled as partial.",
            "partial",
        ),
        audit_row(
            "Quarterly preference",
            "Prefer quarterly time series where the data supports it.",
            "Covered",
            "Core, Gutenberg, PR, classification, Make/Core, dev-note, support snapshot buckets, Stack Overflow, Wikimedia, HN hiring, plugin downloads, and many market/demand charts use quarterly or monthly-to-quarterly series where available.",
        ),
        audit_row(
            "Refreshable source metadata",
            "Enough metadata to refresh without rediscovering the model.",
            "Covered",
            '<a href="data_inventory.html">data_inventory.html</a> lists table counts, local source hashes, and partial-source gaps. <a href="source_gap_plan.html">source_gap_plan.html</a> turns those gaps into a collection order. <a href="refresh_runbook.html">refresh_runbook.html</a> records the refresh path.',
        ),
        audit_row(
            "Short visual decision readout",
            "End with community health, project load, and market position.",
            "Covered",
            'The main report ends with a Decision Readout, and <a href="decision_brief.html">decision_brief.html</a> provides a shareable one-page version with seven visual answer cards.',
        ),
    ]

    html_doc = Template(HTML_TEMPLATE).substitute(
        table_total=compact(table_total),
        source_file_total=compact(source_file_total),
        source_gap_total=compact(source_gap_total),
        audit_rows="\n".join(rows),
        gap_rows=gap_table_rows(gaps),
        generated_at=esc(generated_at),
    )
    OUT.write_text(html_doc, encoding="utf-8")
    print(f"wrote {OUT}")


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress Report Goal Audit</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #172033;
      --muted: #637083;
      --line: #d9e1ea;
      --paper: #f6f8fb;
      --panel: #ffffff;
      --blue: #2563eb;
      --green: #159957;
      --amber: #b7791f;
      --red: #c2410c;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main { max-width: 1180px; margin: 0 auto; padding: 36px 20px 48px; }
    h1 { margin: 0 0 8px; font-size: clamp(34px, 4vw, 54px); line-height: 1.04; letter-spacing: 0; }
    h2 { margin: 0 0 12px; font-size: 22px; }
    h3 { margin: 0 0 6px; font-size: 14px; color: var(--muted); text-transform: uppercase; letter-spacing: .07em; }
    p { margin: 0 0 12px; color: var(--muted); }
    a { color: var(--blue); }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; overflow-wrap: anywhere; }
    .lede { max-width: 880px; font-size: 18px; }
    .grid { display: grid; gap: 14px; }
    .cards { grid-template-columns: repeat(4, minmax(0, 1fr)); margin: 22px 0; }
    .two { grid-template-columns: 1fr 1fr; align-items: start; }
    .card, .section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }
    .metric { font-size: 32px; font-weight: 800; line-height: 1; margin: 4px 0 8px; }
    .metric small { display: block; color: var(--muted); font-size: 13px; font-weight: 650; margin-top: 6px; line-height: 1.3; }
    .status { display: inline-block; border-radius: 999px; padding: 4px 9px; font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: .06em; }
    .covered { background: #dcfce7; color: #166534; }
    .partial { background: #fef3c7; color: #92400e; }
    .audit-list { display: grid; gap: 10px; margin-top: 12px; }
    .audit-row {
      display: grid;
      grid-template-columns: minmax(180px, .9fr) minmax(120px, .45fr) minmax(260px, 1.65fr);
      gap: 12px;
      border: 1px solid var(--line);
      border-left: 5px solid var(--green);
      border-radius: 8px;
      padding: 13px;
      background: #fff;
    }
    .audit-row.partial-row { border-left-color: var(--amber); }
    .audit-row strong { display: block; line-height: 1.2; }
    .audit-row p { margin: 4px 0 0; font-size: 14px; }
    .links { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    .links a {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 6px 10px;
      background: #fbfdff;
      text-decoration: none;
      font-size: 13px;
      font-weight: 700;
    }
    table { width: 100%; border-collapse: collapse; table-layout: fixed; margin-top: 8px; font-size: 14px; }
    th, td { text-align: left; border-bottom: 1px solid var(--line); padding: 9px 8px; vertical-align: top; overflow-wrap: anywhere; }
    th { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }
    .footer { margin-top: 24px; color: var(--muted); font-size: 13px; border-top: 1px solid var(--line); padding-top: 14px; }
    @media (max-width: 860px) {
      main { padding: 24px 14px 36px; }
      .cards, .two, .audit-row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
<main>
  <h1>WordPress report goal audit</h1>
  <p class="lede">This page maps the current WordPress Community & Adoption Health report back to the active <code>goal.md</code> file. It is a quick proof map: what is covered directly, what is covered with public proxies or snapshots, and where the refresh metadata lives.</p>

  <section class="grid cards" aria-label="Audit summary">
    <div class="card">
      <h3>Report sections</h3>
      <div class="metric">3 <small>main views</small></div>
      <p>Participation, Project Load, and Market Position.</p>
    </div>
    <div class="card">
      <h3>Decision answers</h3>
      <div class="metric">7 <small>goal questions</small></div>
      <p>Covered in the main report and the decision brief.</p>
    </div>
    <div class="card">
      <h3>SQLite evidence</h3>
      <div class="metric">$table_total <small>tables</small></div>
      <p>Includes $source_file_total hashed source files and fetched public-source tables.</p>
    </div>
    <div class="card">
      <h3>Partial signals</h3>
      <div class="metric">$source_gap_total <small>labeled gaps</small></div>
      <p>Stored in SQLite and shown in the source coverage pages.</p>
    </div>
  </section>

  <section class="section">
    <h2>Requirement Coverage</h2>
    <div class="audit-list">$audit_rows
    </div>
  </section>

  <section class="grid two" style="margin-top:14px">
    <div class="section">
      <h2>Partial Signals Stored In SQLite</h2>
      <table>
        <thead><tr><th>Signal</th><th>Status</th><th>Best next source</th><th>Current note</th></tr></thead>
        <tbody>$gap_rows
        </tbody>
      </table>
    </div>
    <div class="section">
      <h2>Useful Entry Points</h2>
      <p>Use the full report for charts, the decision brief for sharing, market position for adoption decisions, contributor depth for participation shape, ecosystem activity for non-ticket community channels, the data inventory when checking source coverage, and the source gap plan when choosing the next import.</p>
      <div class="links">
        <a href="index.html#decision-questions">Decision Questions</a>
        <a href="index.html#goal-map">Goal Coverage Map</a>
        <a href="index.html#coverage">Source Coverage</a>
        <a href="decision_brief.html">Decision brief</a>
        <a href="progress_summary.html">Progress summary</a>
        <a href="market_position.html">Market position</a>
        <a href="contributor_depth.html">Contributor depth</a>
        <a href="ecosystem_activity.html">Ecosystem activity</a>
        <a href="data_inventory.html">Data inventory</a>
        <a href="source_gap_plan.html">Source gap plan</a>
        <a href="refresh_runbook.html">Refresh runbook</a>
      </div>
    </div>
  </section>

  <p class="footer">Generated as a companion audit for the WordPress Community & Adoption Health report on $generated_at. Source counts come from community_health.sqlite.</p>
</main>
</body>
</html>
"""


if __name__ == "__main__":
    render()
