#!/usr/bin/env python3
import html
import sqlite3
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
OUT = ROOT / "work_so_far.html"


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


def one(conn, sql, params=(), default=0):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else default


def rows(conn, sql, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def table_exists(conn, name):
    return bool(one(conn, "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)))


def table_count(conn, name):
    if not table_exists(conn, name):
        return 0
    return one(conn, f'SELECT COUNT(*) FROM "{name}"')


def metric_card(label, value, note, tone="blue"):
    return f"""
      <article class="metric {esc(tone)}">
        <h3>{esc(label)}</h3>
        <strong>{esc(value)}</strong>
        <p>{esc(note)}</p>
      </article>"""


def status_card(title, text, value, tone="green"):
    return f"""
        <div class="status-card {esc(tone)}">
          <div>
            <strong>{esc(title)}</strong>
            <span>{esc(text)}</span>
          </div>
          <b>{esc(value)}</b>
        </div>"""


def timeline_item(label, title, body):
    return f"""
        <div class="timeline-item">
          <div class="timeline-date">{esc(label)}</div>
          <div>
            <strong>{esc(title)}</strong>
            <p>{esc(body)}</p>
          </div>
        </div>"""


def bar_row(label, value, max_value, tone="green", suffix=""):
    value = num(value)
    max_value = max(1, num(max_value))
    width = max(2, min(100, value / max_value * 100))
    return f"""
        <div class="bar-row">
          <div class="bar-label"><span>{esc(label)}</span><b>{esc(compact(value))}{esc(suffix)}</b></div>
          <div class="bar-track"><i class="{esc(tone)}" style="width:{width:.1f}%"></i></div>
        </div>"""


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        integrity = one(conn, "PRAGMA integrity_check", default="missing")
        table_total = one(conn, "SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        source_file_count = table_count(conn, "source_files")
        source_gaps = rows(conn, "SELECT * FROM source_gaps ORDER BY signal") if table_exists(conn, "source_gaps") else []
        partial_count = sum(1 for row in source_gaps if row.get("status") == "partial")

        key_counts = {
            "Core tickets": table_count(conn, "core_tickets"),
            "Gutenberg issues": table_count(conn, "gutenberg_issues"),
            "wordpress-develop PRs": table_count(conn, "github_prs"),
            "Classified quarter rows": table_count(conn, "classification_trend"),
            "Make/Core comments": table_count(conn, "make_core_comments"),
            "WordCamp records": table_count(conn, "wordcamps"),
            "Support topics sampled": table_count(conn, "support_forum_topics"),
            "Plugin sample rows": table_count(conn, "plugin_directory_activity_sample"),
            "Theme sample rows": table_count(conn, "theme_directory_activity_sample"),
        }
        max_key_count = max(key_counts.values() or [1])

        companion_pages = [
            ("Main report", "index.html", "Three-view decision report: participation, project load, and market position."),
            ("Decision brief", "decision_brief.html", "Short shareable readout for deciding what the evidence says."),
            ("Project load", "project_load.html", "Backlog, closures, category mix, response, and close-time views."),
            ("Market position", "market_position.html", "Installed share, tracked share, new-site proxy, and demand signals."),
            ("New-site choice", "new_site_choice.html", "Builder comparison and newly found-site proxy."),
            ("Ecosystem activity", "ecosystem_activity.html", "Non-ticket activity: releases, Make/Core, events, support, plugins, and themes."),
            ("Developer interest", "developer_interest.html", "Help-seeking, package use, GitHub topic breadth, and code review."),
            ("Source gap plan", "source_gap_plan.html", "What remains partial and which source family would improve it next."),
            ("Data inventory", "data_inventory.html", "SQLite tables, source hashes, row counts, and downloadable database."),
        ]

        partial_rows = [
            status_card(
                (row.get("signal") or "").replace("_", " ").title(),
                row.get("note", ""),
                row.get("status", ""),
                "amber",
            )
            for row in source_gaps
        ]
    finally:
        conn.close()

    evidence_bars = "\n".join(
        bar_row(label, count, max_key_count, "green" if count >= 1000 else "blue", " rows")
        for label, count in key_counts.items()
    )
    page_links = "\n".join(
        f"""
        <a class="page-link" href="{esc(href)}">
          <strong>{esc(title)}</strong>
          <span>{esc(text)}</span>
        </a>"""
        for title, href, text in companion_pages
    )
    timeline = "\n".join(
        [
            timeline_item("Foundation", "Ticket and issue history", "Loaded Core Trac, Gutenberg issues, wordpress-develop PRs, status flow, reporters, labels, and classification tables into SQLite."),
            timeline_item("Participation", "Quarterly community flow", "Built quarterly views for new and closed work, first-time and repeat reporters, newcomer return cohorts, PR authors, maintainer split, contributor depth, and concentration."),
            timeline_item("Project load", "Backlog and maintenance shape", "Added open backlog, age buckets, category mix, response time, close time, reopened events, and closure-flow visuals."),
            timeline_item("Market", "Adoption and builder context", "Added W3Techs, HTTP Archive, BuiltWith, traffic-tier, new-site proxy, WooCommerce, and enterprise-adoption signals."),
            timeline_item("Ecosystem", "Activity outside trackers", "Added release credits, committers, Make/Core posts and comments, WordCamps, Events, Translate, Five for the Future, support, plugin, and theme sources."),
            timeline_item("Demand", "Developer and search proxies", "Added Stack Overflow, Wikimedia, autocomplete query intent, npm, Packagist, GitHub topic search, HN hiring, Remote OK, Remotive, and WordPress Jobs signals."),
            timeline_item("Packaging", "Refreshable report set", "Generated focused companion pages, a data inventory, source gap plan, goal audit, refresh validation, and a compressed SQLite download."),
        ]
    )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress Relevance Report: Work So Far</title>
  <style>
    :root {{
      color-scheme: light;
      --ink:#172033; --muted:#637083; --line:#d9e1ea; --paper:#f6f8fb; --panel:#fff;
      --blue:#2563eb; --green:#159957; --amber:#b7791f; --violet:#7c3aed;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--paper); color:var(--ink); font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    main {{ max-width:1180px; margin:0 auto; padding:34px 20px 48px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(34px,4vw,54px); line-height:1.04; letter-spacing:0; }}
    h2 {{ margin:0 0 12px; font-size:24px; line-height:1.15; letter-spacing:0; }}
    h3 {{ margin:0 0 8px; font-size:12px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); }}
    p {{ margin:0; color:var(--muted); }}
    a {{ color:var(--blue); }}
    code {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:13px; }}
    .lede {{ max-width:880px; font-size:18px; margin-bottom:18px; }}
    .nav {{ display:flex; flex-wrap:wrap; gap:8px; margin:18px 0 22px; }}
    .nav a {{ border:1px solid var(--line); border-radius:999px; padding:7px 11px; background:#fbfdff; text-decoration:none; font-weight:700; font-size:13px; color:var(--muted); }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:22px 0; }}
    .metric, .section {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; box-shadow:0 1px 2px rgba(15,23,42,.04); }}
    .metric {{ border-top:5px solid var(--blue); min-height:132px; }}
    .metric.green {{ border-top-color:var(--green); }}
    .metric.amber {{ border-top-color:var(--amber); }}
    .metric.violet {{ border-top-color:var(--violet); }}
    .metric strong {{ display:block; font-size:33px; line-height:1; margin:6px 0 9px; }}
    .metric p {{ font-size:14px; }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; align-items:start; }}
    .section {{ margin-top:14px; }}
    .timeline {{ display:grid; gap:10px; }}
    .timeline-item {{ display:grid; grid-template-columns:120px 1fr; gap:14px; padding:12px; border:1px solid var(--line); border-radius:8px; background:#fbfdff; }}
    .timeline-date {{ color:var(--muted); font-weight:800; font-size:13px; text-transform:uppercase; letter-spacing:.07em; }}
    .timeline-item strong {{ display:block; margin-bottom:3px; }}
    .bar-list {{ display:grid; gap:10px; }}
    .bar-label {{ display:flex; justify-content:space-between; gap:12px; align-items:baseline; font-size:14px; }}
    .bar-label span {{ color:var(--muted); }}
    .bar-label b {{ white-space:nowrap; }}
    .bar-track {{ height:9px; border-radius:999px; background:#e8eef6; overflow:hidden; }}
    .bar-track i {{ display:block; height:100%; border-radius:inherit; }}
    .bar-track i.green {{ background:var(--green); }}
    .bar-track i.blue {{ background:var(--blue); }}
    .status-grid, .page-grid {{ display:grid; gap:10px; }}
    .status-card, .page-link {{ display:flex; justify-content:space-between; gap:14px; align-items:flex-start; border-left:5px solid var(--green); background:#fbfdff; border-radius:8px; padding:12px; border-top:1px solid var(--line); border-right:1px solid var(--line); border-bottom:1px solid var(--line); text-decoration:none; color:inherit; }}
    .status-card.amber {{ border-left-color:var(--amber); }}
    .status-card strong, .page-link strong {{ display:block; line-height:1.2; }}
    .status-card span, .page-link span {{ display:block; color:var(--muted); font-size:14px; margin-top:3px; }}
    .status-card b {{ color:var(--amber); white-space:nowrap; }}
    .page-link {{ border-left-color:var(--blue); }}
    .footer-note {{ margin-top:16px; border:1px solid #cfe0ff; background:#eef4ff; border-radius:8px; padding:14px; color:#244067; }}
    @media (max-width:900px) {{
      main {{ padding:24px 14px 36px; }}
      .metrics, .grid {{ grid-template-columns:1fr; }}
      .metric {{ min-height:auto; }}
      .timeline-item {{ grid-template-columns:1fr; gap:5px; }}
      .status-card {{ flex-direction:column; }}
      .status-card b {{ white-space:normal; }}
    }}
  </style>
</head>
<body>
<main>
  <h1>WordPress relevance report: work so far</h1>
  <p class="lede">A compact status page for the report package: what has been built, what evidence is now stored in SQLite, and which source areas still need fuller historical exports.</p>
  <nav class="nav">
    <a href="index.html">Main report</a>
    <a href="decision_brief.html">Decision brief</a>
    <a href="progress_summary.html">Progress summary</a>
    <a href="goal_audit.html">Goal audit</a>
    <a href="data_inventory.html">Data inventory</a>
    <a href="source_gap_plan.html">Source gap plan</a>
    <a href="community_health.sqlite.gz">SQLite download</a>
  </nav>

  <section class="metrics" aria-label="Work summary metrics">
    {metric_card("SQLite tables", compact(table_total), "current report database", "green")}
    {metric_card("Imported files", compact(source_file_count), "tracked with SHA-256 hashes", "blue")}
    {metric_card("Partial source areas", compact(partial_count), "explicitly listed in source_gaps", "amber")}
    {metric_card("Integrity", integrity, "SQLite PRAGMA integrity_check", "green" if integrity == "ok" else "amber")}
  </section>

  <section class="grid">
    <article class="section">
      <h2>Built So Far</h2>
      <div class="timeline">
{timeline}
      </div>
    </article>
    <article class="section">
      <h2>Stored Evidence Scale</h2>
      <p>Representative row counts from the SQLite database. The full inventory is in <a href="data_inventory.html">data_inventory.html</a>.</p>
      <div class="bar-list" style="margin-top:12px">
{evidence_bars}
      </div>
    </article>
  </section>

  <section class="grid">
    <article class="section">
      <h2>Report Surfaces</h2>
      <div class="page-grid">
{page_links}
      </div>
    </article>
    <article class="section">
      <h2>Still Partial</h2>
      <p>These are not blockers for the current readout, but they are the areas where a fuller external source would improve the next revision.</p>
      <div class="status-grid" style="margin-top:12px">
{''.join(partial_rows)}
      </div>
    </article>
  </section>

  <p class="footer-note">Generated from <code>community_health.sqlite</code>. Main report: <a href="index.html">index.html</a>. Refresh command: <code>python3 refresh_report_artifacts.py --skip-main-report --allow-low-disk</code>.</p>
</main>
</body>
</html>
"""
    OUT.write_text("\n".join(line.rstrip() for line in html_doc.splitlines()) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
