#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from fetch_support_forum_snapshot import VIEWS, int_text, parse_page


ROOT = Path("/Users/admin/wordpress_community_health")
OUT = ROOT / "support_forum_archive_snapshots.csv"
UA = "codex-wordpress-community-health/1.0"
CDX_API = "https://web.archive.org/cdx"
COLLECTED_AT = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def eprint(message):
    print(message, file=sys.stderr, flush=True)


def fetch_text(url, timeout=45):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json,text/html,*/*",
        },
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 + attempt * 3)
    raise RuntimeError(f"failed to fetch {url}")


def cdx_url(view_url, from_year, to_year):
    query = urllib.parse.urlencode(
        {
            "url": urllib.parse.urlparse(view_url).netloc + urllib.parse.urlparse(view_url).path,
            "from": str(from_year),
            "to": str(to_year),
            "output": "json",
            "fl": "timestamp,original,statuscode,mimetype,digest",
            "filter": "statuscode:200",
            "collapse": "timestamp:6",
        }
    )
    return f"{CDX_API}?{query}"


def read_cdx(view_url, from_year, to_year):
    body = fetch_text(cdx_url(view_url, from_year, to_year))
    data = json.loads(body)
    if not data or len(data) < 2:
        return []
    header = data[0]
    return [dict(zip(header, row)) for row in data[1:]]


def quarter_starts(from_year, to_year):
    current = dt.date(from_year, 1, 1)
    end = dt.date(to_year, 12, 31)
    while current <= end:
        yield current
        month = current.month + 3
        year = current.year
        if month > 12:
            month -= 12
            year += 1
        current = dt.date(year, month, 1)


def quarter_end(start):
    month = start.month + 3
    year = start.year
    if month > 12:
        month -= 12
        year += 1
    return dt.date(year, month, 1)


def quarter_label(start):
    return f"{start.year}-Q{((start.month - 1) // 3) + 1}"


def timestamp_date(timestamp):
    return dt.datetime.strptime(timestamp[:8], "%Y%m%d").date()


def select_snapshot(cdx_rows, start):
    end = quarter_end(start)
    in_quarter = [
        row
        for row in cdx_rows
        if row.get("timestamp") and start <= timestamp_date(row["timestamp"]) < end
    ]
    if not in_quarter:
        return None
    return min(in_quarter, key=lambda row: abs((timestamp_date(row["timestamp"]) - start).days))


def archive_url(timestamp, original):
    original = original or ""
    return f"https://web.archive.org/web/{timestamp}id_/{original}"


def row_from_snapshot(view_name, view, quarter_start, cdx_row):
    source_url = archive_url(cdx_row["timestamp"], cdx_row["original"])
    body = fetch_text(source_url, timeout=60)
    max_page, topics = parse_page(body)
    topic_count = len(topics)
    estimated_total = max_page * topic_count if topic_count else 0
    activity_dates = sorted(row.get("last_activity_at", "") for row in topics if row.get("last_activity_at"))
    forums = {row.get("forum_name") for row in topics if row.get("forum_name")}
    starters = {row.get("starter_slug") for row in topics if row.get("starter_slug")}
    replies = sum(int_text(row.get("replies")) for row in topics)
    participants = sum(int_text(row.get("participants")) for row in topics)
    no_reply = sum(1 for row in topics if int_text(row.get("replies")) == 0)
    resolved = sum(1 for row in topics if row.get("resolved_badge") == "1")
    return {
        "quarter": quarter_start.isoformat(),
        "label": quarter_label(quarter_start),
        "snapshot_date": timestamp_date(cdx_row["timestamp"]).isoformat(),
        "archive_timestamp": cdx_row["timestamp"],
        "view": view_name,
        "queue": view["queue"],
        "view_label": view["label"],
        "pages_discovered": max_page,
        "topics_on_first_page": topic_count,
        "estimated_total_topics": estimated_total,
        "first_page_replies": replies,
        "first_page_participants": participants,
        "first_page_no_reply_topics": no_reply,
        "first_page_resolved_badges": resolved,
        "first_page_forums": len(forums),
        "first_page_starters": len(starters),
        "latest_activity_at": activity_dates[-1] if activity_dates else "",
        "oldest_activity_at": activity_dates[0] if activity_dates else "",
        "archive_original_url": cdx_row.get("original", ""),
        "archive_digest": cdx_row.get("digest", ""),
        "source": "Internet Archive Wayback first-page snapshot of WordPress.org support view",
        "source_url": source_url,
        "source_note": "Estimated total topics equals pagination pages times first-page topic count; this is a queue-size estimate, not a full topic export.",
        "collected_at": COLLECTED_AT,
    }


def write_csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def collect(from_year, to_year, sleep):
    rows = []
    for view_name, view in VIEWS.items():
        cdx_rows = read_cdx(view["url"], from_year, to_year)
        eprint(f"{view_name}: {len(cdx_rows)} archived months")
        for quarter_start in quarter_starts(from_year, to_year):
            snapshot = select_snapshot(cdx_rows, quarter_start)
            if not snapshot:
                continue
            try:
                rows.append(row_from_snapshot(view_name, view, quarter_start, snapshot))
                eprint(f"{view_name} {quarter_label(quarter_start)}: {rows[-1]['estimated_total_topics']} estimated topics")
            except Exception as exc:
                eprint(f"{view_name} {quarter_label(quarter_start)} skipped: {type(exc).__name__}: {exc}")
            time.sleep(sleep)
    rows.sort(key=lambda row: (row["quarter"], row["view"]))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-year", type=int, default=2018)
    parser.add_argument("--to-year", type=int, default=2026)
    parser.add_argument("--sleep", type=float, default=0.4)
    args = parser.parse_args()

    rows = collect(args.from_year, args.to_year, args.sleep)
    write_csv(OUT, rows)
    eprint(f"wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()
