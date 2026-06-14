#!/usr/bin/env python3
import html
import sqlite3
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
OUT = ROOT / "contributor_depth.html"


SOURCES = [
    ("Core Trac reporters", "Core Trac", "#2563eb"),
    ("Gutenberg issue creators", "Gutenberg", "#8b5cf6"),
    ("wordpress-develop PR authors", "Core PRs", "#159957"),
]

BUCKETS = [
    ("1 item", "One time"),
    ("2-4 items", "Returning"),
    ("5-19 items", "Regular"),
    ("20+ items", "Sustained"),
]


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def pct(value):
    return f"{float(value or 0):.1f}%"


def compact(value):
    value = int(float(value or 0))
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{value / 1_000:.1f}k"
    return f"{value:,}"


def one(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else 0


def contributor_rows(conn):
    return conn.execute(
        """
        SELECT source, window, bucket, bucket_order, contributor_share_pct, contributors,
               item_share_pct, items, total_contributors, total_items
        FROM contributor_depth_buckets
        ORDER BY source, window, CAST(bucket_order AS INTEGER)
        """
    ).fetchall()


def nav_html():
    return "\n".join(
        [
            '    <nav class="nav">',
            '      <a href="index.html#participation">Participation</a>',
            '      <a href="index.html#decision-questions">Decision Questions</a>',
            '      <a href="project_load.html">Project load</a>',
            '      <a href="market_position.html">Market position</a>',
            '      <a href="developer_interest.html">Developer interest</a>',
            '      <a href="support_load.html">Support load</a>',
            '      <a href="ecosystem_activity.html">Ecosystem activity</a>',
            '      <a href="progress_summary.html">Progress summary</a>',
            '      <a href="decision_brief.html">Decision brief</a>',
            '      <a href="goal_audit.html">Goal audit</a>',
            '      <a href="data_inventory.html">Data inventory</a>',
            '      <a href="source_gap_plan.html">Source gap plan</a>',
            '      <a href="refresh_runbook.html">Refresh runbook</a>',
            "    </nav>",
        ]
    )


def row_map(rows):
    return {
        (row["source"], row["window"], row["bucket"]): dict(row)
        for row in rows
    }


def get_value(rows_by_key, source, window, bucket, field):
    row = rows_by_key.get((source, window, bucket), {})
    return float(row.get(field) or 0)


def get_count(rows_by_key, source, window, bucket, field):
    row = rows_by_key.get((source, window, bucket), {})
    return compact(row.get(field) or 0)


def source_total(rows_by_key, source, window, field):
    row = rows_by_key.get((source, window, "1 item"), {})
    return compact(row.get(field) or 0)


def bar(label, value, color):
    width = max(2, min(100, float(value or 0)))
    return f"""
        <div class="barline">
          <div class="bar-label"><span>{esc(label)}</span><strong>{pct(value)}</strong></div>
          <div class="bar"><span style="width:{width:.1f}%;background:{esc(color)}"></span></div>
        </div>"""


def depth_ladder(rows_by_key, source, label, color, window):
    rows = []
    for bucket, bucket_label in BUCKETS:
        contributor_share = get_value(rows_by_key, source, window, bucket, "contributor_share_pct")
        item_share = get_value(rows_by_key, source, window, bucket, "item_share_pct")
        contributor_count = get_count(rows_by_key, source, window, bucket, "contributors")
        item_count = get_count(rows_by_key, source, window, bucket, "items")
        rows.append(
            f"""
        <div class="depth-row">
          <div class="bucket">
            <strong>{esc(bucket_label)}</strong>
            <span>{esc(bucket)} · {contributor_count} people · {item_count} items</span>
          </div>
          <div class="bars">
            {bar("people", contributor_share, color)}
            {bar("work", item_share, "#172033")}
          </div>
        </div>"""
        )
    return f"""
      <article class="source-card">
        <div class="source-head">
          <span style="background:{esc(color)}"></span>
          <div>
            <h2>{esc(label)}</h2>
            <p>{esc(source)} · {source_total(rows_by_key, source, window, "total_contributors")} contributors · {source_total(rows_by_key, source, window, "total_items")} items since 2024</p>
          </div>
        </div>
        <div class="depth-rows">{''.join(rows)}</div>
      </article>"""


def summary_card(rows_by_key, source, label, color):
    one_time_now = get_value(rows_by_key, source, "since_2024", "1 item", "contributor_share_pct")
    sustained_work_now = get_value(rows_by_key, source, "since_2024", "20+ items", "item_share_pct")
    sustained_people_now = get_value(rows_by_key, source, "since_2024", "20+ items", "contributor_share_pct")
    one_time_all = get_value(rows_by_key, source, "all_time", "1 item", "contributor_share_pct")
    sustained_work_all = get_value(rows_by_key, source, "all_time", "20+ items", "item_share_pct")
    one_time_delta = one_time_now - one_time_all
    sustained_delta = sustained_work_now - sustained_work_all
    return f"""
      <article class="summary-card">
        <div class="source-dot" style="background:{esc(color)}"></div>
        <h2>{esc(label)}</h2>
        <div class="big">{pct(one_time_now)}</div>
        <p>one-time contributors since 2024</p>
        <div class="mini-grid">
          <div><strong>{pct(sustained_work_now)}</strong><span>work from sustained contributors</span></div>
          <div><strong>{pct(sustained_people_now)}</strong><span>contributors in sustained bucket</span></div>
        </div>
        <div class="delta">
          <span>One-time share vs all-time: {one_time_delta:+.1f} pts</span>
          <span>Sustained work vs all-time: {sustained_delta:+.1f} pts</span>
        </div>
      </article>"""


def render():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = contributor_rows(conn)
        integrity = one(conn, "PRAGMA integrity_check")
    finally:
        conn.close()

    rows_by_key = row_map(rows)
    summaries = "\n".join(summary_card(rows_by_key, source, label, color) for source, label, color in SOURCES)
    ladders = "\n".join(depth_ladder(rows_by_key, source, label, color, "since_2024") for source, label, color in SOURCES)

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress Contributor Depth</title>
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
    h2 {{ margin: 0; font-size: 22px; line-height: 1.15; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 12px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }}
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
    .summary-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin: 22px 0; }}
    .summary-card, .source-card, .readout {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
    }}
    .summary-card {{ padding: 16px; position: relative; overflow: hidden; }}
    .source-dot {{ width: 36px; height: 5px; border-radius: 999px; margin-bottom: 12px; }}
    .big {{ font-size: 42px; line-height: 1; font-weight: 850; margin: 12px 0 4px; }}
    .summary-card p, .delta, .source-head p, .note {{ color: var(--muted); font-size: 14px; }}
    .mini-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 14px 0; }}
    .mini-grid div {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: #fbfdff;
    }}
    .mini-grid strong {{ display: block; font-size: 23px; line-height: 1; margin-bottom: 5px; }}
    .mini-grid span {{ color: var(--muted); font-size: 12px; line-height: 1.25; display: block; }}
    .delta {{ display: grid; gap: 4px; border-top: 1px solid var(--line); padding-top: 10px; }}
    .readout {{ padding: 18px; margin: 16px 0; }}
    .readout-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 12px; }}
    .readout-grid div {{ border-left: 5px solid var(--blue); background: #fbfdff; border-radius: 8px; padding: 12px; }}
    .readout-grid div:nth-child(2) {{ border-left-color: var(--amber); }}
    .readout-grid div:nth-child(3) {{ border-left-color: var(--green); }}
    .readout-grid strong {{ display: block; margin-bottom: 5px; }}
    .readout-grid span {{ color: var(--muted); font-size: 14px; }}
    .source-stack {{ display: grid; gap: 14px; margin-top: 16px; }}
    .source-card {{ padding: 18px; }}
    .source-head {{ display: flex; gap: 12px; align-items: flex-start; margin-bottom: 14px; }}
    .source-head > span {{ width: 6px; min-height: 48px; border-radius: 999px; flex: 0 0 auto; }}
    .depth-rows {{ display: grid; gap: 10px; }}
    .depth-row {{
      display: grid;
      grid-template-columns: 210px minmax(0, 1fr);
      gap: 14px;
      align-items: center;
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }}
    .depth-row:first-child {{ border-top: 0; padding-top: 0; }}
    .bucket strong {{ display: block; font-size: 16px; }}
    .bucket span {{ display: block; color: var(--muted); font-size: 13px; }}
    .bars {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .barline {{ min-width: 0; }}
    .bar-label {{ display: flex; justify-content: space-between; gap: 8px; font-size: 13px; margin-bottom: 4px; }}
    .bar-label span {{ color: var(--muted); }}
    .bar-label strong {{ white-space: nowrap; }}
    .bar {{ height: 9px; border-radius: 999px; background: #e8eef5; overflow: hidden; }}
    .bar span {{ display: block; height: 100%; border-radius: inherit; }}
    .footer-note {{
      background: #eef4ff;
      border: 1px solid #cfe0ff;
      border-radius: 8px;
      padding: 14px 16px;
      margin-top: 16px;
      color: #244067;
    }}
    @media (max-width: 920px) {{
      .summary-grid, .readout-grid {{ grid-template-columns: 1fr; }}
      .depth-row {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 620px) {{
      main {{ padding: 24px 14px 36px; }}
      .bars, .mini-grid {{ grid-template-columns: 1fr; }}
      .big {{ font-size: 36px; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>WordPress contributor depth</h1>
    <p class="lede">A focused view of drive-by, returning, regular, and sustained participation across Core Trac tickets, Gutenberg issues, and wordpress-develop pull requests.</p>
{nav_html()}

    <section class="summary-grid" aria-label="Contributor depth summary">
{summaries}
    </section>

    <section class="readout">
      <h2>What this says</h2>
      <div class="readout-grid">
        <div><strong>Broad entry is real.</strong><span>Each stream still has many people who only appear once, especially Core Trac.</span></div>
        <div><strong>Repeat work is concentrated.</strong><span>Gutenberg and Core PRs depend more heavily on the sustained-contributor bucket.</span></div>
        <div><strong>PRs are the most concentrated stream.</strong><span>Since 2024, 8.4% of PR authors account for 69.1% of wordpress-develop PRs.</span></div>
      </div>
    </section>

    <section>
      <h2>Depth ladders since 2024</h2>
      <p class="note">Each row compares share of people with share of work. A wide people bar with a smaller work bar means broad entry; a small people bar with a wider work bar means concentrated repeat work.</p>
      <div class="source-stack">
{ladders}
      </div>
    </section>

    <p class="footer-note">Rows come from the SQLite <code>contributor_depth_buckets</code> table. Integrity check: <code>{esc(integrity)}</code>. The main report summarizes this as broad entry with concentrated sustained work.</p>
  </main>
</body>
</html>
"""
    clean_doc = "\n".join(line.rstrip() for line in html_doc.splitlines()) + "\n"
    OUT.write_text(clean_doc, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    render()
