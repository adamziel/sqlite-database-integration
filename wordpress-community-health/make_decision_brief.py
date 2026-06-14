#!/usr/bin/env python3
import html
import sqlite3
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
OUT = ROOT / "decision_brief.html"


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def num(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def pct(value):
    return f"{num(value):.1f}%"


def pts(value):
    return f"{abs(num(value)):.1f} points"


def signed_pts(value):
    return f"{num(value):+.1f} pts"


def compact(value):
    value = int(round(num(value)))
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{value / 1_000:.1f}k"
    return f"{value:,}"


def rows(conn, sql, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def value(conn, sql, params=(), default=None):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else default


def table_exists(conn, name):
    return bool(value(conn, "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,), 0))


def market_value(conn, metric, technology="WordPress", date=None):
    if date:
        return value(
            conn,
            "SELECT value FROM market_share WHERE metric=? AND technology=? AND date=?",
            (metric, technology, date),
            0,
        )
    return value(
        conn,
        """
        SELECT value
        FROM market_share
        WHERE metric=? AND technology=?
        ORDER BY date DESC
        LIMIT 1
        """,
        (metric, technology),
        0,
    )


def average(conn, table, field, start, end=None):
    if end:
        sql = f"SELECT AVG(CAST({field} AS REAL)) FROM {table} WHERE quarter >= ? AND quarter < ?"
        return num(value(conn, sql, (start, end), 0))
    sql = f"SELECT AVG(CAST({field} AS REAL)) FROM {table} WHERE quarter >= ?"
    return num(value(conn, sql, (start,), 0))


def backlog_share(conn, source, buckets):
    placeholders = ",".join("?" for _ in buckets)
    params = [source, *buckets]
    numerator = num(
        value(
            conn,
            f"""
            SELECT SUM(CAST(open_count AS REAL))
            FROM open_backlog_age_summary
            WHERE source=? AND age_bucket IN ({placeholders})
            """,
            params,
            0,
        )
    )
    total = num(
        value(
            conn,
            "SELECT MAX(CAST(open_total AS REAL)) FROM open_backlog_age_summary WHERE source=?",
            (source,),
            0,
        )
    )
    return numerator / total * 100 if total else 0


def source_top50(conn, source):
    return num(
        value(
            conn,
            """
            SELECT top50_item_share_pct
            FROM contributor_concentration_summary
            WHERE source=? AND window='since_2024'
            """,
            (source,),
            0,
        )
    )


def signal(conn, name):
    row = conn.execute("SELECT * FROM new_site_choice_summary WHERE signal=?", (name,)).fetchone()
    return dict(row) if row else {}


def attention_signal(conn, name):
    row = conn.execute("SELECT * FROM attention_demand_summary WHERE signal=?", (name,)).fetchone()
    return dict(row) if row else {}


def latest_npm(conn):
    latest = value(conn, "SELECT MAX(quarter) FROM npm_wordpress_downloads_quarterly", default="")
    total = value(
        conn,
        "SELECT SUM(CAST(downloads AS REAL)) FROM npm_wordpress_downloads_quarterly WHERE quarter=?",
        (latest,),
        0,
    )
    if str(latest).endswith("-04-01"):
        label = f"Q2 {str(latest)[:4]}"
    elif str(latest).endswith("-01-01"):
        label = f"Q1 {str(latest)[:4]}"
    elif str(latest).endswith("-07-01"):
        label = f"Q3 {str(latest)[:4]}"
    elif str(latest).endswith("-10-01"):
        label = f"Q4 {str(latest)[:4]}"
    else:
        label = str(latest or "latest quarter")
    return label, num(total)


def metric_card(label, metric, note, color, width):
    return f"""
    <div class="card">
      <h3>{esc(label)}</h3>
      <div class="metric">{esc(metric)}<small>{esc(note)}</small></div>
      <div class="bar"><span class="{esc(color)}" style="width:{max(2, min(100, num(width))):.1f}%"></span></div>
    </div>"""


def question_card(tone, heading, answer, body, source):
    return f"""
      <article class="question-card {esc(tone)}">
        <h3>{esc(heading)}</h3>
        <strong>{esc(answer)}</strong>
        <p>{esc(body)}</p>
        <span class="source">{esc(source)}</span>
      </article>"""


def matrix_card(tone, heading, lead, body, metric):
    return f"""
      <article class="matrix-card {esc(tone)}">
        <h3>{esc(heading)}</h3>
        <strong>{esc(lead)}</strong>
        <p>{esc(body)}</p>
        <span>{esc(metric)}</span>
      </article>"""


def ladder_row(tone, label, value, text):
    return f"""
      <div class="ladder-row {esc(tone)}">
        <span>{esc(label)}</span>
        <strong>{esc(value)}</strong>
        <p>{esc(text)}</p>
      </div>""".strip()


def evidence_row(row):
    return f"""
      <div class="evidence-row {esc(row.get('tone') or 'soft')}">
        <div>
          <strong>{esc(row.get('question'))}</strong>
          <p>{esc(row.get('answer'))}</p>
        </div>
        <div>
          <span class="evidence-type">{esc(row.get('evidence_type'))}</span>
          <p>{esc(row.get('primary_sources'))}</p>
        </div>
        <div>
          <b>{esc(row.get('current_read'))}</b>
          <p>{esc(row.get('next_source'))}</p>
        </div>
        <div>
          <a href="{esc(row.get('report_link') or 'index.html')}">{esc(row.get('report_label') or 'Open view')}</a>
        </div>
      </div>""".strip()


def change_pct_label(row):
    if not row:
        return "n/a"
    return f"{num(row.get('change_pct')):+.1f}%"


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        wp_all = num(market_value(conn, "all_sites_usage"))
        wp_cms = num(market_value(conn, "cms_market_share"))
        usage_delta = wp_all - num(market_value(conn, "all_sites_usage", date="2025-01-01"))
        cms_delta = wp_cms - num(market_value(conn, "cms_market_share", date="2025-01-01"))

        builtwith_90 = signal(conn, "builtwith_90_day_pipeline")
        builtwith_30 = signal(conn, "builtwith_30_day_pipeline")
        archive_latest = signal(conn, "http_archive_latest_tracked_share")
        archive_change = signal(conn, "http_archive_tracked_share_change")
        builtwith_90_share = num(builtwith_90.get("wordpress_share_pct"))
        builtwith_30_share = num(builtwith_30.get("wordpress_share_pct"))
        archive_share = num(archive_latest.get("wordpress_share_pct"))
        archive_delta = num(archive_change.get("wordpress_value"))
        wiki_attention = attention_signal(conn, "wikimedia_wordpress_pageviews")
        stack_attention = attention_signal(conn, "stack_overflow_wordpress_questions")
        hn_attention = attention_signal(conn, "hn_wordpress_woocommerce_hiring_rate")
        support_snapshot_rows = rows(conn, "SELECT * FROM support_forum_snapshot_summary")
        support_snapshot = support_snapshot_rows[0] if support_snapshot_rows else {}
        support_older_unresolved = num(
            value(
                conn,
                """
                SELECT SUM(CAST(unresolved AS REAL))
                FROM support_forum_age_buckets
                WHERE age_bucket IN ('91-180 days','181+ days')
                """,
                default=0,
            )
        )
        major_support_threads = num(value(conn, "SELECT SUM(CAST(support_threads AS REAL)) FROM major_plugin_install_snapshot", default=0))
        major_support_resolved = num(value(conn, "SELECT SUM(CAST(support_threads_resolved AS REAL)) FROM major_plugin_install_snapshot", default=0))
        major_support_resolved_pct = major_support_resolved / major_support_threads * 100 if major_support_threads else 0
        evidence_rows = (
            rows(conn, "SELECT * FROM decision_question_evidence ORDER BY CAST(sort_order AS INTEGER)")
            if table_exists(conn, "decision_question_evidence")
            else []
        )

        core_created_recent = average(conn, "core_quarterly", "created", "2024-01-01")
        core_closed_recent = average(conn, "core_quarterly", "closed", "2024-01-01")
        gut_created_recent = average(conn, "gutenberg_quarterly", "created", "2024-01-01")
        gut_closed_recent = average(conn, "gutenberg_quarterly", "closed", "2024-01-01")
        core_closure_ratio = core_closed_recent / core_created_recent * 100 if core_created_recent else 0
        gut_closure_ratio = gut_closed_recent / gut_created_recent * 100 if gut_created_recent else 0

        core_first_prev = average(conn, "core_quarterly", "first_time_reporters", "2021-01-01", "2024-01-01")
        core_first_recent = average(conn, "core_quarterly", "first_time_reporters", "2024-01-01")
        gut_first_prev = average(conn, "gutenberg_quarterly", "first_time_creators", "2021-01-01", "2024-01-01")
        gut_first_recent = average(conn, "gutenberg_quarterly", "first_time_creators", "2024-01-01")
        core_first_retention = core_first_recent / core_first_prev * 100 if core_first_prev else 0
        gut_first_retention = gut_first_recent / gut_first_prev * 100 if gut_first_prev else 0

        stale_buckets = ["1-2 years", "2-5 years", "5+ years"]
        old_buckets = ["2-5 years", "5+ years"]
        core_stale = backlog_share(conn, "Core", stale_buckets)
        gut_stale = backlog_share(conn, "Gutenberg", stale_buckets)
        core_old = backlog_share(conn, "Core", old_buckets)
        gut_old = backlog_share(conn, "Gutenberg", old_buckets)

        core_top50 = source_top50(conn, "Core Trac reporters")
        gut_top50 = source_top50(conn, "Gutenberg issue creators")
        pr_top50 = source_top50(conn, "wordpress-develop PR authors")

        npm_quarter, npm_total = latest_npm(conn)
        theme_count = num(value(conn, "SELECT COUNT(DISTINCT slug) FROM theme_directory_activity_sample", default=0))
    finally:
        conn.close()

    cards = "".join(
        [
            metric_card("Still widely chosen", pct(wp_all), "of all sites, W3Techs", "green", wp_all),
            metric_card("CMS share", pct(wp_cms), "of CMS sites, W3Techs", "green", wp_cms),
            metric_card("Builder pressure", signed_pts(archive_delta), "HTTP Archive tracked share since 2020-01", "amber", 70),
            metric_card("Current pipeline", pct(builtwith_90_share), "tracked BuiltWith 90-day pipeline", "blue", builtwith_90_share),
            metric_card("Package activity", compact(npm_total), f"{npm_quarter} tracked @wordpress npm downloads", "purple", 78),
            metric_card("Theme directory", compact(theme_count), "distinct sampled themes in current browse views", "green", 64),
        ]
    )

    questions = "".join(
        [
            question_card(
                "good",
                "Still widely chosen?",
                "Yes.",
                f"Installed-share evidence has WordPress at {pct(wp_all)} of all sites and {pct(wp_cms)} of CMS sites.",
                "W3Techs + HTTP Archive",
            ),
            question_card(
                "watch",
                "Adoption direction?",
                "Flat-to-down recently.",
                f"W3Techs all-site share is down {pts(usage_delta)} and CMS share is down {pts(cms_delta)} since Jan 2025.",
                "W3Techs yearly trend",
            ),
            question_card(
                "slower",
                "Participation?",
                "Fewer new reporters.",
                f"Core first-time reporter retention is {pct(core_first_retention)} of the 2021-2023 average; Gutenberg is {pct(gut_first_retention)}. PR creation and npm package activity are still visible.",
                "Core Trac + Gutenberg + PRs",
            ),
            question_card(
                "soft",
                "Keeping up?",
                "Mostly.",
                f"Since 2024, closure/new ratios are Core {pct(core_closure_ratio)} and Gutenberg {pct(gut_closure_ratio)}.",
                "Quarterly ticket flow",
            ),
            question_card(
                "watch",
                "Backlog age?",
                "Aged.",
                f"Open stale share is Core {pct(core_stale)} and Gutenberg {pct(gut_stale)}; 2+ year open share is Core {pct(core_old)} and Gutenberg {pct(gut_old)}.",
                "Current open backlog",
            ),
            question_card(
                "soft",
                "Contributor spread?",
                "Broad entry, concentrated work.",
                f"Since 2024, top-50 work share is Core {pct(core_top50)}, Gutenberg {pct(gut_top50)}, and PRs {pct(pr_top50)}.",
                "Contributor concentration",
            ),
            question_card(
                "watch",
                "Builders gaining?",
                "Some share, yes.",
                f"HTTP Archive tracked share has WordPress at {pct(archive_share)}, down {pts(archive_delta)} since 2020-01-01; WordPress still leads the current tracked BuiltWith 90-day pipeline at {pct(builtwith_90_share)}.",
                "HTTP Archive + BuiltWith proxy",
            ),
        ]
    )

    matrix = "".join(
        [
            matrix_card(
                "good",
                "Good default when",
                "Reach, ownership, and ecosystem depth matter.",
                "WordPress still has the largest installed CMS footprint and a broad plugin/theme/community surface.",
                f"{pct(wp_all)} of all sites, {pct(wp_cms)} of CMS sites",
            ),
            matrix_card(
                "soft",
                "Plan for slower entry when",
                "You depend on fresh public contributors or public help-channel growth.",
                "First-time tracker participation and public help-question volume are lower than earlier periods.",
                f"First-time reporter retention: Core {pct(core_first_retention)}, Gutenberg {pct(gut_first_retention)}",
            ),
            matrix_card(
                "watch",
                "Use one more source when",
                "The decision mostly depends on new-site demand, search interest, or hiring demand.",
                "The report has useful public proxies, but the ideal sources are first-seen site cohorts, search-provider exports, and broad hiring-platform exports.",
                f"Current BuiltWith 90-day proxy: {pct(builtwith_90_share)} WordPress share",
            ),
        ]
    )
    evidence_map = "\n".join(evidence_row(row) for row in evidence_rows)

    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress Relevance Decision Brief</title>
  <style>
    :root {{ --ink:#172033; --muted:#637083; --line:#d9e1ea; --paper:#f6f8fb; --panel:#fff; --blue:#2563eb; --green:#159957; --amber:#b7791f; --red:#c2410c; --purple:#7c3aed; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--paper); color:var(--ink); font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    main {{ max-width:1120px; margin:0 auto; padding:36px 20px 48px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(34px,4vw,54px); line-height:1.04; letter-spacing:0; }}
    h2 {{ margin:28px 0 12px; font-size:22px; }}
    h3 {{ margin:0 0 6px; font-size:15px; color:var(--muted); text-transform:uppercase; letter-spacing:.07em; }}
    p {{ margin:0 0 12px; color:var(--muted); }}
    a {{ color:var(--blue); }}
    .lede {{ max-width:900px; font-size:18px; }}
    .hero {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:22px; }}
    .answer {{ display:grid; grid-template-columns:1.2fr .8fr; gap:18px; align-items:start; margin-top:18px; }}
    .verdict {{ border-left:6px solid var(--amber); background:#fffaf0; border-radius:8px; padding:16px; }}
    .verdict strong {{ display:block; color:var(--ink); font-size:28px; line-height:1.12; margin-bottom:8px; }}
    .grid {{ display:grid; gap:14px; }}
    .cards {{ grid-template-columns:repeat(3,minmax(0,1fr)); margin:20px 0; }}
    .two {{ grid-template-columns:1fr 1fr; }}
    .card {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; }}
    .nav {{ display:flex; flex-wrap:wrap; gap:8px; margin:18px 0 0; }}
    .nav a {{ border:1px solid var(--line); border-radius:999px; padding:7px 11px; background:#fbfdff; color:var(--muted); font-size:13px; text-decoration:none; }}
    .lanes {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin:20px 0 6px; }}
    .lane {{ background:var(--panel); border:1px solid var(--line); border-top:5px solid var(--blue); border-radius:8px; padding:15px; }}
    .lane.good {{ border-top-color:var(--green); }}
    .lane.watch {{ border-top-color:var(--amber); }}
    .lane strong {{ display:block; color:var(--ink); margin-bottom:7px; font-size:18px; }}
    .lane p {{ margin-bottom:0; font-size:14px; }}
    .question-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; margin:12px 0 22px; }}
    .question-card {{ background:var(--panel); border:1px solid var(--line); border-left:5px solid var(--blue); border-radius:8px; padding:15px; min-height:172px; }}
    .question-card h3 {{ margin-bottom:6px; }}
    .question-card strong {{ display:block; color:var(--ink); font-size:22px; line-height:1.15; margin-bottom:8px; }}
    .question-card p {{ margin-bottom:0; }}
    .question-card .source {{ display:block; margin-top:11px; color:#475569; font-size:12px; font-weight:800; }}
    .question-card.good {{ border-left-color:var(--green); }}
    .question-card.watch {{ border-left-color:var(--amber); }}
    .question-card.slower {{ border-left-color:var(--red); }}
    .question-card.soft {{ border-left-color:var(--blue); }}
    .matrix-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin:12px 0 22px; }}
    .matrix-card {{ background:var(--panel); border:1px solid var(--line); border-top:5px solid var(--blue); border-radius:8px; padding:16px; min-width:0; }}
    .matrix-card.good {{ border-top-color:var(--green); }}
    .matrix-card.watch {{ border-top-color:var(--amber); }}
    .matrix-card.soft {{ border-top-color:var(--red); }}
    .matrix-card strong {{ display:block; color:var(--ink); font-size:21px; line-height:1.16; margin-bottom:8px; }}
    .matrix-card p {{ margin-bottom:11px; }}
    .matrix-card span {{ display:block; color:#475569; font-size:13px; font-weight:800; }}
    .evidence-map {{ display:grid; gap:10px; margin:12px 0 22px; }}
    .evidence-row {{ display:grid; grid-template-columns:minmax(160px,1fr) minmax(145px,.8fr) minmax(220px,1.35fr) minmax(100px,.55fr); gap:12px; align-items:start; background:var(--panel); border:1px solid var(--line); border-left:6px solid var(--blue); border-radius:8px; padding:13px; }}
    .evidence-row.good {{ border-left-color:var(--green); }}
    .evidence-row.watch {{ border-left-color:var(--amber); }}
    .evidence-row.slower {{ border-left-color:var(--red); }}
    .evidence-row.soft {{ border-left-color:var(--blue); }}
    .evidence-row strong, .evidence-row b {{ display:block; color:var(--ink); line-height:1.2; }}
    .evidence-row p {{ margin:4px 0 0; color:var(--muted); font-size:13px; line-height:1.35; }}
    .evidence-type {{ display:inline-flex; width:max-content; max-width:100%; border-radius:999px; padding:4px 9px; font-size:12px; font-weight:800; background:#eef2ff; color:#3730a3; }}
    .evidence-row.good .evidence-type {{ background:#dcfce7; color:#166534; }}
    .evidence-row.watch .evidence-type {{ background:#fef3c7; color:#92400e; }}
    .evidence-row.slower .evidence-type {{ background:#fee2e2; color:#991b1b; }}
    .evidence-ladder {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px; margin:20px 0; }}
    .evidence-ladder h2 {{ margin-top:0; }}
    .ladder-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }}
    .ladder-row {{ border:1px solid var(--line); border-left:5px solid var(--blue); border-radius:8px; padding:12px; background:#fbfdff; min-width:0; }}
    .ladder-row span {{ display:block; color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; font-weight:800; }}
    .ladder-row strong {{ display:block; color:var(--ink); font-size:24px; line-height:1.1; margin:5px 0; overflow-wrap:anywhere; }}
    .ladder-row p {{ margin:0; color:var(--muted); font-size:13px; line-height:1.35; }}
    .ladder-row.good {{ border-left-color:var(--green); }}
    .ladder-row.watch {{ border-left-color:var(--amber); }}
    .ladder-row.softer {{ border-left-color:var(--red); }}
    .metric {{ font-size:32px; font-weight:800; line-height:1; margin:4px 0 8px; }}
    .metric small {{ display:block; color:var(--muted); font-size:13px; font-weight:650; margin-top:6px; line-height:1.3; }}
    .pill {{ display:inline-block; border-radius:999px; padding:4px 9px; background:#eef4ff; color:var(--blue); font-size:12px; font-weight:750; text-transform:uppercase; letter-spacing:.06em; }}
    .bar {{ height:10px; border-radius:999px; background:#e7edf5; overflow:hidden; margin:10px 0 2px; }}
    .bar span {{ display:block; height:100%; border-radius:inherit; }}
    .green {{ background:var(--green); }}
    .blue {{ background:var(--blue); }}
    .amber {{ background:var(--amber); }}
    .red {{ background:var(--red); }}
    .purple {{ background:var(--purple); }}
    table {{ width:100%; border-collapse:collapse; table-layout:fixed; margin-top:8px; font-size:14px; }}
    th, td {{ text-align:left; border-bottom:1px solid var(--line); padding:10px 8px; vertical-align:top; overflow-wrap:anywhere; }}
    th {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; }}
    .footer {{ margin-top:24px; color:var(--muted); font-size:13px; }}
    @media (max-width:860px) {{ main {{ padding:24px 14px 36px; }} .answer, .cards, .two, .lanes, .matrix-grid, .ladder-grid, .evidence-row {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <span class="pill">Decision brief</span>
    <h1>WordPress is still the default CMS, but the signals are softer.</h1>
    <p class="lede">Use WordPress as a strong default when installed reach, ecosystem depth, and open-source control matter. Treat growth and new-site momentum as slower: the report shows fewer new tracker reporters and more visible builder pressure, while ecosystem and package activity remain broad.</p>
    <nav class="nav" aria-label="Report links">
      <a href="index.html#decision-questions">Full report</a>
      <a href="new_site_choice.html">New-site choice</a>
      <a href="developer_interest.html">Developer interest</a>
      <a href="ecosystem_activity.html">Ecosystem activity</a>
      <a href="project_load.html">Project load</a>
      <a href="source_gap_plan.html">Source gaps</a>
    </nav>
    <div class="answer">
      <div class="verdict">
        <strong>Decision readout: still healthy, with slower entry.</strong>
        <p>WordPress remains dominant on installed-share evidence and has broad ecosystem activity. The work queue is closer to balanced than the backlog size alone suggests. The slower areas are new participant entry, older backlog, and direct evidence for new-site share, search interest, and broad job demand.</p>
      </div>
      <div class="card">
        <h3>Evidence strength</h3>
        <p><b>Strong:</b> installed share, ticket flow, PRs, backlog, release/community activity, plugin/theme directory snapshots.</p>
        <p><b>Useful proxy:</b> BuiltWith pipeline, HTTP Archive tracked share, Stack Overflow, Wikimedia, npm package downloads, HN hiring, Jobs board.</p>
        <p><b>Still partial:</b> true multi-year newly created-site cohorts, search-provider exports, broad hiring-platform exports, long support history.</p>
      </div>
    </div>
  </section>

  <section class="lanes" aria-label="Evidence lanes">
    <article class="lane">
      <strong>Project data says: mostly keeping up.</strong>
      <p>Core and Gutenberg flow is close to balanced since 2024, but open backlog age is still high.</p>
    </article>
    <article class="lane good">
      <strong>Ecosystem data says: still active.</strong>
      <p>Release credits, Make/Core, events, translations, plugin/theme samples, support queues, and npm packages are now in the SQLite-backed report.</p>
    </article>
    <article class="lane watch">
      <strong>Market data says: dominant, slower.</strong>
      <p>Installed share is still large, while recent share direction and first-time tracker participation are weaker than earlier periods.</p>
    </article>
  </section>

  <section class="grid cards">
{cards}
  </section>

  <section class="evidence-ladder">
    <h2>New-site Evidence Ladder</h2>
    <p>Use the first two rows for confidence that WordPress is still widely chosen. Use the last two rows to understand why new-site momentum is labeled as a proxy instead of a complete history.</p>
    <div class="ladder-grid">
      {ladder_row("good", "Installed share", f"{pct(wp_all)} / {pct(wp_cms)}", "Direct all-site and CMS-share evidence.")}
      {ladder_row("soft", "Current pipeline", pct(builtwith_90_share), f"BuiltWith 90-day newly found-site proxy; 30-day share is {pct(builtwith_30_share)}.")}
      {ladder_row("watch", "Recurring crawl trend", signed_pts(archive_delta), "HTTP Archive tracked-share movement since 2020-01.")}
      {ladder_row("softer", "True cohort", "Not yet", "Needs first-seen site cohort or paid BuiltWith historical export.")}
    </div>
  </section>

  <section class="evidence-ladder">
    <h2>Attention and Demand Evidence Ladder</h2>
    <p>Use this to separate public attention, developer help-seeking, and hiring proxies from direct search or labor-market evidence.</p>
    <div class="ladder-grid">
      {ladder_row("watch", "Public attention", change_pct_label(wiki_attention), "Wikimedia WordPress pageviews versus the latest pre-2024 quarter.")}
      {ladder_row("softer", "Developer help", change_pct_label(stack_attention), "Stack Overflow WordPress-tag questions versus the latest pre-2024 quarter.")}
      {ladder_row("watch", "Hiring proxy", change_pct_label(hn_attention), "HN WP/Woo hiring mention rate versus parsed pre-2024 history.")}
      {ladder_row("softer", "Direct search/jobs", "Not yet", "Needs Google Trends or similar plus a broad hiring-platform export.")}
    </div>
  </section>

  <section class="evidence-ladder">
    <h2>Support Evidence Ladder</h2>
    <p>Use this to distinguish the current support queue shape from the still-missing long-term forum history.</p>
    <div class="ladder-grid">
      {ladder_row("watch", "Current queue", compact(support_snapshot.get("topics")), f"{pct(support_snapshot.get('resolved_share_pct'))} resolved, {pct(support_snapshot.get('unresolved_share_pct'))} unresolved in the sampled queue.")}
      {ladder_row("watch", "Older unresolved", compact(support_older_unresolved), "Unresolved topics with last activity 91+ days ago.")}
      {ladder_row("soft", "Plugin support", compact(major_support_threads), f"{pct(major_support_resolved_pct)} resolved across tracked major-plugin support threads.")}
      {ladder_row("softer", "Long history", "Not yet", "Needs a full topic/reply export or recurring all/resolved/unresolved snapshots.")}
    </div>
  </section>

  <section>
    <h2>Decision Matrix</h2>
    <div class="matrix-grid">
{matrix}
    </div>
  </section>

  <section>
    <h2>Evidence Map</h2>
    <p>This separates direct measurements from mixed and proxy-backed answers, so the decision brief is easier to scan without opening every chart.</p>
    <div class="evidence-map">
{evidence_map}
    </div>
  </section>

  <section>
    <h2>Decision Questions</h2>
    <div class="question-grid">
{questions}
    </div>
  </section>

  <p class="footer">Sources and full charts: <a href="index.html#decision-questions">full report decision questions</a>, <a href="progress_summary.html">progress summary</a>, <a href="project_load.html">project load</a>, <a href="market_position.html">market position</a>, <a href="new_site_choice.html">new-site choice</a>, <a href="search_interest.html">search interest</a>, <a href="developer_interest.html">developer interest</a>, <a href="job_demand.html">job demand</a>, <a href="support_load.html">support load</a>, <a href="contributor_depth.html">contributor depth</a>, <a href="ecosystem_activity.html">ecosystem activity</a>, <a href="goal_audit.html">goal audit</a>, <a href="data_inventory.html">data inventory</a>, <a href="source_gap_plan.html">source gap plan</a>, and <a href="refresh_runbook.html">refresh runbook</a>.</p>
</main>
</body>
</html>
"""
    OUT.write_text(html_text, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
