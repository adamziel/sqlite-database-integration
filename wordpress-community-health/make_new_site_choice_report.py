#!/usr/bin/env python3
import html
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
if not DB_PATH.exists():
    DB_PATH = SOURCE_ROOT / "community_health.sqlite"
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


def table_exists(conn, table):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


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


def multi_line_chart(title, note, series, value_decimals=1, y_suffix="%", start_zero=True):
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
    y_min = 0 if start_zero else min(values or [0])
    y_max = max(values or [1])
    if y_min == y_max:
        y_max = y_min + 1
    span = y_max - y_min
    y_bottom = y_min - (0 if start_zero else span * 0.08)
    y_top = y_max + max(1 if start_zero else span * 0.08, abs(y_max) * 0.05)
    if y_bottom == y_top:
        y_top = y_bottom + 1
    max_points = max(len(item["points"]) for item in clean)

    def x(index):
        if max_points <= 1:
            return left + plot_w
        return left + index / (max_points - 1) * plot_w

    def y(value):
        return top + (1 - ((value - y_bottom) / (y_top - y_bottom))) * plot_h

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
    if start_zero:
        ticks = [0, y_top / 2, y_top]
    else:
        ticks = [y_bottom, 0, y_top] if y_bottom < 0 < y_top else [y_bottom, (y_bottom + y_top) / 2, y_top]
    for tick in ticks:
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


def stacked_area_chart(title, note, layers):
    clean = []
    for layer in layers:
        points = [(str(label), num(value)) for label, value in layer.get("points", []) if label]
        if points:
            clean.append(
                {
                    "name": layer["name"],
                    "color": layer["color"],
                    "points": dict(points),
                }
            )
    labels = sorted({label for layer in clean for label in layer["points"]})
    if not clean or not labels:
        return ""
    width, height = 760, 330
    left, right, top, bottom = 58, 28, 46, 72
    plot_w = width - left - right
    plot_h = height - top - bottom

    def x(index):
        if len(labels) <= 1:
            return left + plot_w
        return left + index / (len(labels) - 1) * plot_w

    def y(value):
        return top + (1 - max(0, min(100, value)) / 100) * plot_h

    pieces = [
        '<article class="chart-card">',
        f'<h2>{esc(title)}</h2>',
        f'<p>{esc(note)}</p>',
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
    ]
    for tick in [0, 25, 50, 75, 100]:
        yy = y(tick)
        pieces.append(f'<line x1="{left}" x2="{width - right}" y1="{yy:.1f}" y2="{yy:.1f}" class="gridline" />')
        pieces.append(f'<text x="{left - 9}" y="{yy + 4:.1f}" class="axis" text-anchor="end">{tick}%</text>')
    x_ticks = labels if len(labels) <= 6 else [labels[round(i * (len(labels) - 1) / 5)] for i in range(6)]
    seen = set()
    for label in x_ticks:
        if label in seen:
            continue
        seen.add(label)
        pieces.append(f'<text x="{x(labels.index(label)):.1f}" y="{height - 34}" class="axis" text-anchor="middle">{esc(label[:7])}</text>')
    cumulative = {label: 0.0 for label in labels}
    latest_values = []
    for layer in clean:
        top_points = []
        bottom_points = []
        for index, label in enumerate(labels):
            bottom_value = cumulative[label]
            value = layer["points"].get(label, 0)
            top_value = bottom_value + value
            cumulative[label] = top_value
            top_points.append((x(index), y(top_value)))
            bottom_points.append((x(index), y(bottom_value)))
        top_path = " ".join(
            ("M" if index == 0 else "L") + f"{xx:.1f},{yy:.1f}"
            for index, (xx, yy) in enumerate(top_points)
        )
        bottom_path = " ".join(f"L{xx:.1f},{yy:.1f}" for xx, yy in reversed(bottom_points))
        pieces.append(f'<path d="{top_path} {bottom_path} Z" fill="{esc(layer["color"])}" opacity="0.78" />')
        pieces.append(
            f'<path d="{top_path}" fill="none" stroke="{esc(layer["color"])}" stroke-width="1.5" '
            'stroke-linejoin="round" />'
        )
        latest_values.append((layer["name"], layer["color"], layer["points"].get(labels[-1], 0)))
    pieces.append("</svg>")
    pieces.append('<div class="legend">')
    for name, color, latest in latest_values:
        pieces.append(
            f'<span><i style="background:{esc(color)}"></i>{esc(name)} '
            f'<b>{pct(latest)}</b></span>'
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


def derive_quarterly_change_rows(rows_):
    by_technology = {}
    for row in rows_:
        technology = row.get("technology")
        if not technology:
            continue
        by_technology.setdefault(technology, []).append(row)

    changes = []
    for technology, tech_rows in sorted(by_technology.items()):
        previous = None
        for row in sorted(tech_rows, key=lambda item: item.get("date", "")):
            if previous is None:
                previous = row
                continue
            origin_delta = num(row.get("mobile_origins")) - num(previous.get("mobile_origins"))
            share_delta = num(row.get("mobile_tracked_share_pct")) - num(previous.get("mobile_tracked_share_pct"))
            changes.append(
                {
                    "date": row.get("date", ""),
                    "label": row.get("label", ""),
                    "technology": technology,
                    "months": row.get("months", ""),
                    "mobile_origins": row.get("mobile_origins", ""),
                    "mobile_origin_delta": origin_delta,
                    "mobile_tracked_share_pct": row.get("mobile_tracked_share_pct", ""),
                    "mobile_tracked_share_delta_pts": share_delta,
                    "positive_mobile_origin_delta": max(0, origin_delta),
                }
            )
            previous = row

    totals = {}
    for row in changes:
        totals[row["date"]] = totals.get(row["date"], 0) + row["positive_mobile_origin_delta"]
    for row in changes:
        total = totals.get(row["date"], 0)
        row["tracked_positive_mobile_origin_delta"] = total
        row["positive_delta_tracked_share_pct"] = (
            row["positive_mobile_origin_delta"] / total * 100 if total else 0
        )
    return changes


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


def rank_mix_panel(rows_):
    if not rows_:
        return ""
    by_rank = {}
    for row in rows_:
        rank = row.get("rank")
        if not rank:
            continue
        by_rank.setdefault(
            rank,
            {
                "order": num(row.get("rank_order")),
                "rows": [],
                "total": 0,
            },
        )
        by_rank[rank]["rows"].append(row)
        by_rank[rank]["total"] += num(row.get("mobile_origins"))
    rank_blocks = []
    for rank, data in sorted(by_rank.items(), key=lambda item: item[1]["order"]):
        bars = []
        for row in sorted(data["rows"], key=lambda item: num(item.get("mobile_origins")), reverse=True):
            technology = row.get("technology")
            share = num(row.get("mobile_origins")) / data["total"] * 100 if data["total"] else 0
            bars.append(
                bar_row(
                    technology,
                    share,
                    100,
                    COLORS.get(technology, COLORS["blue"]),
                    suffix="%",
                )
            )
        rank_blocks.append(
            f"""
        <div class="rank-block">
          <h3>{esc(rank)}</h3>
          <div class="bar-stack">{''.join(bars)}</div>
        </div>"""
        )
    return f"""
      <article class="panel full">
        <h2>HTTP Archive rank-tier peer mix</h2>
        <p>Latest mobile-crawl detected-origin share within each HTTP Archive rank tier across WordPress, Shopify, Wix, Squarespace, and Webflow.</p>
        <div class="rank-grid">{''.join(rank_blocks)}</div>
      </article>"""


def momentum_panel(rows_):
    if not rows_:
        return ""
    ordered = [row for row in rows_ if row.get("technology")]
    max_abs = max([abs(num(row.get("tracked_share_change_pts"))) for row in ordered] or [1])
    items = []
    for row in ordered:
        change = num(row.get("tracked_share_change_pts"))
        width = 0 if max_abs <= 0 or change == 0 else max(2, min(100, abs(change) / max_abs * 100))
        tone = "gain" if change > 0 else "loss" if change < 0 else "flat"
        items.append(
            f"""
        <div class="momentum-row {esc(tone)}">
          <div>
            <strong>{esc(row.get("technology"))}</strong>
            <span>{esc(pct(row.get("latest_mobile_tracked_share_pct")))} latest tracked share</span>
          </div>
          <div class="momentum-track"><span style="width:{width:.1f}%"></span></div>
          <b>{esc(signed_pts(change))}</b>
        </div>"""
        )
    first = ordered[0].get("first_label", "") if ordered else ""
    latest = ordered[0].get("latest_label", "") if ordered else ""
    return f"""
      <article class="panel">
        <h2>Tracked-share momentum</h2>
        <p>HTTP Archive quarterly tracked-share change from {esc(first)} to {esc(latest)}. This is a recurring crawl proxy, not first-seen site creation.</p>
        <div class="momentum-stack">{''.join(items)}</div>
      </article>"""


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
        momentum = (
            rows(
                conn,
                """
                SELECT *
                FROM builder_momentum_summary
                WHERE technology IN ('WordPress','Shopify','Wix','Squarespace','Webflow')
                ORDER BY CAST(latest_mobile_tracked_share_pct AS REAL) DESC
                """,
            )
            if table_exists(conn, "builder_momentum_summary")
            else []
        )
        gap = rows(conn, "SELECT * FROM source_gaps WHERE signal='new_site_share_history'")
        site_creation = (
            rows(
                conn,
                """
                SELECT *
                FROM http_archive_site_creation_adoption_monthly
                ORDER BY date, technology
                """,
            )
            if table_exists(conn, "http_archive_site_creation_adoption_monthly")
            else []
        )
        market_share = (
            rows(
                conn,
                """
                SELECT date, metric, technology, value
                FROM market_share
                WHERE technology='WordPress'
                  AND metric IN ('all_sites_usage','cms_market_share')
                ORDER BY date, metric
                """,
            )
            if table_exists(conn, "market_share")
            else []
        )
    finally:
        conn.close()

    by_signal = {row.get("signal"): row for row in summary}
    builtwith_90 = by_signal.get("builtwith_90_day_pipeline", {})
    builtwith_30 = by_signal.get("builtwith_30_day_pipeline", {})
    http_latest = by_signal.get("http_archive_latest_tracked_share", {})
    http_change = by_signal.get("http_archive_tracked_share_change", {})
    top_1m = by_signal.get("builtwith_top_1m_tracked_share", {})
    long_tail = by_signal.get("builtwith_long_tail_tracked_share", {})
    http_change_rows = derive_quarterly_change_rows(http_share)
    wp_change_rows = sorted(
        [row for row in http_change_rows if row.get("technology") == "WordPress"],
        key=lambda row: row.get("date", ""),
    )
    wp_latest_change = wp_change_rows[-1] if wp_change_rows else {}
    wp_latest_change_label = wp_latest_change.get("label", "")
    wp_latest_change_months = int(num(wp_latest_change.get("months"))) if wp_latest_change else 0
    wp_latest_change_note = (
        f"{wp_latest_change_label}; {wp_latest_change_months}/3 months"
        if wp_latest_change_label and wp_latest_change_months and wp_latest_change_months < 3
        else wp_latest_change_label
    )
    site_all_by_date = {
        row.get("date"): row for row in site_creation if row.get("technology") == "ALL" and row.get("date")
    }
    site_rows = []
    for row in site_creation:
        technology = row.get("technology") or ""
        date_value = row.get("date") or ""
        if not technology or technology == "ALL" or date_value not in site_all_by_date:
            continue
        all_mobile = num(site_all_by_date[date_value].get("mobile_origins"))
        mobile = num(row.get("mobile_origins"))
        row = dict(row)
        row["mobile_all_origin_share_pct"] = mobile / all_mobile * 100 if all_mobile else 0
        row["label"] = date_value[:7]
        site_rows.append(row)
    site_dates = sorted(site_all_by_date)
    site_latest_date = site_dates[-1] if site_dates else ""
    site_latest_all = num(site_all_by_date.get(site_latest_date, {}).get("mobile_origins"))
    site_latest_rows = [row for row in site_rows if row.get("date") == site_latest_date]
    site_latest_by_tech = {row.get("technology"): row for row in site_latest_rows}
    site_by_date_tech = {
        (row.get("date"), row.get("technology")): row
        for row in site_rows
    }
    bucket_defs = [
        ("all_other", "All other sites/tools", [], COLORS["ink"]),
        ("wordpress", "WordPress", ["WordPress"], COLORS["WordPress"]),
        ("shopify", "Shopify", ["Shopify"], COLORS["Shopify"]),
        (
            "other_builders",
            "Other CMS/builders",
            ["Wix", "Squarespace", "Webflow", "Duda", "Tilda"],
            COLORS["Wix"],
        ),
        ("nextjs", "Next.js", ["Next.js"], "#111827"),
        (
            "static_generators",
            "Static/app generators",
            ["Nuxt.js", "Astro", "Gatsby", "Hugo", "Jekyll", "Eleventy"],
            COLORS["violet"],
        ),
        ("ai_builders", "AI/visual builders", ["Framer Sites", "Lovable", "Base44"], "#dc2626"),
    ]
    bucket_points = {key: [] for key, _label, _technologies, _color in bucket_defs}
    latest_buckets = {}
    for date_value in site_dates:
        all_mobile = num(site_all_by_date.get(date_value, {}).get("mobile_origins"))
        if not all_mobile:
            continue
        selected = 0
        counts = {}
        for key, _label, technologies, _color in bucket_defs:
            if key == "all_other":
                continue
            count = sum(
                num(site_by_date_tech.get((date_value, technology), {}).get("mobile_origins"))
                for technology in technologies
            )
            counts[key] = count
            selected += count
        counts["all_other"] = max(0, all_mobile - selected)
        for key, label, technologies, color in bucket_defs:
            count = counts.get(key, 0)
            share = count / all_mobile * 100 if all_mobile else 0
            bucket_points[key].append((date_value, share))
            if date_value == site_latest_date:
                latest_buckets[key] = {
                    "label": label,
                    "technologies": technologies,
                    "color": color,
                    "mobile_origins": count,
                    "share": share,
                }
    split_layers = [
        {
            "name": label,
            "color": color,
            "points": bucket_points.get(key, []),
        }
        for key, label, _technologies, color in bucket_defs
    ]
    latest_bucket_max = max([row.get("share", 0) for row in latest_buckets.values()] or [1])
    wp_all_site = {
        row.get("date"): num(row.get("value"))
        for row in market_share
        if row.get("metric") == "all_sites_usage"
    }
    wp_cms_share = {
        row.get("date"): num(row.get("value"))
        for row in market_share
        if row.get("metric") == "cms_market_share"
    }
    no_cms_points = []
    for date_value in sorted(set(wp_all_site) & set(wp_cms_share)):
        cms_share = wp_cms_share.get(date_value, 0)
        all_site = wp_all_site.get(date_value, 0)
        if cms_share <= 0:
            continue
        inferred_known_cms = all_site / (cms_share / 100)
        no_cms_points.append((date_value, max(0, min(100, 100 - inferred_known_cms))))
    no_cms_latest = no_cms_points[-1][1] if no_cms_points else 0

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
            metric_card(
                "Latest q/q share change",
                signed_pts(wp_latest_change.get("mobile_tracked_share_delta_pts")),
                wp_latest_change_note or "HTTP Archive quarter change",
                "amber",
            ),
            metric_card(
                "Latest net origin change",
                compact(wp_latest_change.get("mobile_origin_delta")),
                "WordPress detected mobile origins",
                "amber" if num(wp_latest_change.get("mobile_origin_delta")) < 0 else "blue",
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
    positive_delta_share_chart = multi_line_chart(
        "WordPress share of positive net additions",
        "Share of positive quarter-over-quarter mobile-origin additions within the tracked set. Quarters where WordPress lost detected origins are shown as 0%.",
        [
            {
                "name": "WordPress positive net-addition share",
                "color": COLORS["WordPress"],
                "points": points_for(http_change_rows, "WordPress", "positive_delta_tracked_share_pct"),
            }
        ],
        value_decimals=1,
        y_suffix="%",
    )
    share_change_chart = multi_line_chart(
        "WordPress tracked-share change by quarter",
        "Quarter-over-quarter change in WordPress mobile tracked share, in percentage points. This is crawl-share movement, not literal first-published-site share.",
        [
            {
                "name": "WordPress q/q share change",
                "color": COLORS["amber"],
                "points": points_for(http_change_rows, "WordPress", "mobile_tracked_share_delta_pts"),
            }
        ],
        value_decimals=1,
        y_suffix=" pts",
        start_zero=False,
    )
    origin_change_chart = multi_line_chart(
        "Net detected mobile-origin change",
        "Quarter-over-quarter change in average mobile detected origins. Use this as a noisy proxy for newly observed presence, not as a count of newly published websites.",
        [
            {
                "name": tech,
                "color": COLORS[tech],
                "points": points_for(http_change_rows, tech, "mobile_origin_delta"),
            }
            for tech in tech_order
        ],
        value_decimals=0,
        y_suffix="",
        start_zero=False,
    )
    all_sites_split_chart = stacked_area_chart(
        "All sites by selected site-creation signal",
        "Stacked share of all HTTP Archive mobile origins. Buckets use aggregate technology detections and all other sites/tools is the residual after selected buckets.",
        split_layers,
    )
    latest_split_bars = "".join(
        bar_row(
            row.get("label"),
            row.get("share"),
            latest_bucket_max,
            row.get("color") or COLORS["ink"],
            suffix="%",
        )
        for row in latest_buckets.values()
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
      --red:#c2410c;
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
    .full {{ grid-column:1 / -1; }}
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
    .momentum-stack {{ display:grid; gap:11px; margin-top:14px; }}
    .momentum-row {{ display:grid; grid-template-columns:minmax(120px,.8fr) minmax(110px,1fr) 88px; gap:10px; align-items:center; }}
    .momentum-row strong, .momentum-row span {{ display:block; }}
    .momentum-row span {{ color:var(--muted); font-size:13px; }}
    .momentum-row b {{ text-align:right; white-space:nowrap; }}
    .momentum-track {{ height:10px; border-radius:999px; background:#e8eef5; overflow:hidden; }}
    .momentum-track span {{ display:block; height:100%; border-radius:inherit; background:var(--green); }}
    .momentum-row.loss .momentum-track span {{ background:var(--amber); }}
    .momentum-row.flat .momentum-track span {{ background:var(--muted); }}
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
    .rank-grid {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; margin-top:14px; }}
    .rank-block {{ border:1px solid var(--line); border-radius:8px; padding:12px; background:#fbfdff; min-width:0; }}
    .rank-block .bar-label {{ display:block; }}
    .rank-block .bar-label strong {{ display:block; margin-top:2px; }}
    .footer-note {{ margin-top:14px; background:#eef4ff; border:1px solid #cfe0ff; border-radius:8px; padding:14px 16px; color:#244067; }}
    @media (max-width:980px) {{
      .metrics {{ grid-template-columns:1fr 1fr; }}
      .grid, .readout, .rank-grid {{ grid-template-columns:1fr; }}
    }}
    @media (max-width:640px) {{
      main {{ padding:24px 14px 36px; }}
      .metrics {{ grid-template-columns:1fr; }}
      .signal-row {{ display:block; }}
      .signal-row b {{ display:block; margin-top:5px; }}
      .momentum-row {{ grid-template-columns:1fr; gap:5px; }}
      .momentum-row b {{ text-align:left; }}
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
      <article class="panel">
        <h2>Source limit</h2>
        <p>No public source found in this pass exposes a historical first-published-site cohort by CMS or site-creation mode. The five-name chart is only a CMS/builder peer view; broader site creation also includes static/app frameworks, deployment platforms, AI-era builders, and custom or plain HTML sites.</p>
        <div class="readout">
          <div><strong>Closest current signal</strong><span>BuiltWith Net New Pipeline gives current 30/90-day newly found counts where public pages expose them.</span></div>
          <div><strong>Closest historical signal</strong><span>HTTP Archive gives recurring monthly technology adoption counts by detected origin.</span></div>
          <div><strong>Pure HTML need</strong><span>Requires origin-level BigQuery because aggregate technology counts overlap and cannot be subtracted from all sites.</span></div>
        </div>
        <p class="footer-note">Checked sources: <a href="https://trends.builtwith.com/cms/WordPress">BuiltWith Net New Pipeline</a>, <a href="https://github.com/HTTPArchive/tech-report-apis">HTTP Archive Technology Report API</a>, <a href="https://har.fyi/guides/getting-started/">HTTP Archive BigQuery guide</a>, and <a href="https://w3techs.com/technologies">W3Techs methodology</a>.</p>
      </article>
    </section>

    <section class="grid" style="margin-top:14px">
      {all_sites_split_chart}
      <article class="panel">
        <h2>Latest all-sites bucket split</h2>
        <p>Latest selected-bucket split from the same area chart. All other sites/tools includes pure HTML, custom apps, unknown/no detected tool, deployment-only signals, and tools outside the selected buckets.</p>
        <div class="bar-stack">{latest_split_bars}</div>
        <p class="footer-note">Latest all-origin denominator: {compact(site_latest_all)} mobile origins on {esc(site_latest_date)}. Buckets use aggregate detections, so this is directional rather than origin-level deduplicated.</p>
      </article>
    </section>

    <section class="grid" style="margin-top:14px">
      {positive_delta_share_chart}
      {share_change_chart}
    </section>

    <section class="grid" style="margin-top:14px">
      {origin_change_chart}
      {origin_chart}
    </section>

    <section class="grid" style="margin-top:14px">
      {grouped_snapshot("BuiltWith 90-day newly found sites", "Current Net New Pipeline counts where the public page exposes them. Squarespace is omitted because the fetched page did not expose comparable counts.", builtwith, "new_last_3_months")}
      {grouped_snapshot("BuiltWith 30-day newly found sites", "A shorter current window from the same public BuiltWith pages.", builtwith, "new_last_month")}
    </section>

    <section class="grid" style="margin-top:14px">
      {tier_chart}
      {momentum_panel(momentum)}
    </section>

    <section class="grid" style="margin-top:14px">
      <article class="panel full">
        <h2>HTTP Archive current rank tiers</h2>
        <p>Latest mobile-crawl WordPress share among the five tracked technologies within each HTTP Archive rank tier.</p>
        <div class="bar-stack">{rank_snapshot(rank_rows)}</div>
      </article>
      {rank_mix_panel(rank_rows)}
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
