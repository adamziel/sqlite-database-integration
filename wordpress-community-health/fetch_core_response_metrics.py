#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


sys.path.insert(0, "/Users/admin/wordpress_core_issue_analysis")
import make_core_report as core_report  # noqa: E402


ROOT = Path("/Users/admin/wordpress_community_health")
CORE_ROOT = Path("/Users/admin/wordpress_core_issue_analysis")
TICKETS_CSV = CORE_ROOT / "raw" / "trac_tickets.csv"
CACHE = ROOT / "cache" / "core_trac_response_rss"
OUT_JSONL = ROOT / "core_response_metrics.jsonl"
OUT_QUARTERLY = ROOT / "core_response_quarterly.csv"

START = dt.datetime(2021, 1, 1, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 6, 11, 23, 59, 59, tzinfo=dt.timezone.utc)
BOT_CREATORS = {"slackbot", "prbot", "github", "commitbot"}


def eprint(message):
    print(message, file=sys.stderr, flush=True)


def parse_iso(value):
    if not value:
        return None
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def iso(value):
    if not value:
        return ""
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def quarter_start(value):
    if isinstance(value, str):
        value = parse_iso(value)
    month = ((value.month - 1) // 3) * 3 + 1
    return f"{value.year:04d}-{month:02d}-01"


def strip_html(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def cache_path(ticket_id):
    return CACHE / f"ticket-{int(ticket_id):06d}.json"


def load_tickets():
    rows = []
    with TICKETS_CSV.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            created = parse_iso(row.get("created_at"))
            if created and START <= created <= END:
                rows.append(row)
    return sorted(rows, key=lambda row: int(row["id"]))


def parse_rss(ticket_id, data):
    root = ET.fromstring(data)
    ns = {"dc": "http://purl.org/dc/elements/1.1/"}
    items = []
    for item in root.findall("./channel/item"):
        date = core_report.parse_rss_dt(item.findtext("pubDate") or "")
        creator = item.findtext("dc:creator", default="", namespaces=ns) or ""
        title = (item.findtext("title") or "").strip()
        description = strip_html(item.findtext("description") or "")
        link = item.findtext("link") or ""
        items.append(
            {
                "ticket_id": str(ticket_id),
                "creator": creator,
                "created_at": iso(date),
                "title": title,
                "description": description,
                "link": link,
            }
        )
    return items


def fetch_one(ticket, client, force=False):
    ticket_id = ticket["id"]
    path = cache_path(ticket_id)
    if path.exists() and not force:
        return ticket_id, "cached", ""
    headers = {
        "User-Agent": core_report.UA,
        "Accept": "application/rss+xml,text/xml,*/*",
    }
    url = f"{core_report.TRAC}/ticket/{ticket_id}?format=rss"
    for attempt in range(6):
        headers["Cookie"] = client.cookie_header()
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=75) as resp:
                data = resp.read()
            items = parse_rss(ticket_id, data)
            payload = {
                "ticket_id": str(ticket_id),
                "source_url": url,
                "item_count": len(items),
                "items": items,
            }
            path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            return ticket_id, "fetched", ""
        except urllib.error.HTTPError as exc:
            exc.read(500)
            if exc.code == 403 and attempt < 5:
                client.solve_challenge(url, force=True)
                time.sleep(1)
                continue
            if exc.code == 429 and attempt < 5:
                retry_after = exc.headers.get("Retry-After")
                sleep_for = int(retry_after) if retry_after and retry_after.isdigit() else min(60, 5 * (attempt + 1))
                time.sleep(sleep_for)
                continue
            return ticket_id, "error", f"HTTP {exc.code}"
        except Exception as exc:
            if attempt < 5:
                time.sleep(1 + attempt)
                continue
            return ticket_id, "error", repr(exc)[:300]
    return ticket_id, "error", "exhausted retries"


def fetch_all(tickets, force=False, workers=3, limit=None):
    CACHE.mkdir(parents=True, exist_ok=True)
    selected = tickets[:limit] if limit else tickets
    client = core_report.TracClient()
    if selected:
        client.request(
            f"{core_report.TRAC}/ticket/{selected[0]['id']}?format=rss",
            accept="application/rss+xml,text/xml,*/*",
            timeout=90,
        )
    completed = 0
    counts = defaultdict(int)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_one, ticket, client, force): ticket for ticket in selected}
        for future in as_completed(futures):
            ticket = futures[future]
            ticket_id, status, error = future.result()
            counts[status] += 1
            completed += 1
            if error:
                eprint(f"ticket {ticket_id} {status}: {error}")
            if completed % 250 == 0 or completed == len(selected):
                eprint(
                    f"Core RSS {completed:,}/{len(selected):,}; "
                    f"fetched {counts['fetched']:,}, cached {counts['cached']:,}, errors {counts['error']:,}"
                )


def load_cached_items(ticket_id):
    path = cache_path(ticket_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def is_human_response(item, reporter):
    creator = (item.get("creator") or "").strip().lower()
    if not creator or creator in BOT_CREATORS:
        return False
    if reporter and creator == reporter:
        return False
    return True


def metric_for_ticket(ticket):
    ticket_id = ticket["id"]
    created = parse_iso(ticket.get("created_at"))
    reporter = (ticket.get("reporter") or "").strip().lower()
    payload = load_cached_items(ticket_id)
    if not payload:
        return {
            "ticket_id": ticket_id,
            "created_at": ticket.get("created_at", ""),
            "reporter": ticket.get("reporter", ""),
            "status": ticket.get("status", ""),
            "rss_fetched": 0,
            "rss_item_count": 0,
            "first_non_reporter_activity_at": "",
            "first_non_reporter_activity_hours": "",
            "first_non_reporter_activity_creator": "",
            "source_url": f"{core_report.TRAC}/ticket/{ticket_id}?format=rss",
        }
    first = None
    for item in sorted(payload.get("items") or [], key=lambda row: row.get("created_at") or ""):
        item_at = parse_iso(item.get("created_at"))
        if not item_at or not created or item_at < created:
            continue
        if is_human_response(item, reporter):
            first = item
            break
    first_at = parse_iso(first.get("created_at")) if first else None
    return {
        "ticket_id": ticket_id,
        "created_at": ticket.get("created_at", ""),
        "reporter": ticket.get("reporter", ""),
        "status": ticket.get("status", ""),
        "rss_fetched": 1,
        "rss_item_count": len(payload.get("items") or []),
        "first_non_reporter_activity_at": iso(first_at),
        "first_non_reporter_activity_hours": round((first_at - created).total_seconds() / 3600, 2) if first_at and created else "",
        "first_non_reporter_activity_creator": first.get("creator", "") if first else "",
        "source_url": payload.get("source_url") or f"{core_report.TRAC}/ticket/{ticket_id}?format=rss",
    }


def median(values):
    values = sorted(float(v) for v in values if v not in ("", None))
    if not values:
        return ""
    mid = len(values) // 2
    if len(values) % 2:
        return round(values[mid], 2)
    return round((values[mid - 1] + values[mid]) / 2, 2)


def build_quarterly(metrics):
    buckets = defaultdict(list)
    for row in metrics:
        created = parse_iso(row.get("created_at"))
        if created:
            buckets[quarter_start(created)].append(row)
    rows = []
    for quarter in sorted(buckets):
        entries = buckets[quarter]
        fetched = [row for row in entries if int(row.get("rss_fetched") or 0)]
        response_hours = [row.get("first_non_reporter_activity_hours") for row in fetched if row.get("first_non_reporter_activity_hours") != ""]
        rows.append(
            {
                "quarter": quarter,
                "tickets_created": len(entries),
                "rss_fetched": len(fetched),
                "rss_missing": len(entries) - len(fetched),
                "tickets_with_first_non_reporter_activity": len(response_hours),
                "tickets_without_first_non_reporter_activity": len(fetched) - len(response_hours),
                "median_first_non_reporter_activity_hours": median(response_hours),
                "coverage_percent": round(len(fetched) / len(entries) * 100, 2) if entries else 0,
            }
        )
    return rows


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()

    tickets = load_tickets()
    eprint(f"Core tickets created {START.date()} to {END.date()}: {len(tickets):,}")
    if not args.skip_fetch:
        fetch_all(tickets, force=args.force, workers=args.workers, limit=args.limit)
    selected = tickets[: args.limit] if args.limit else tickets
    metrics = [metric_for_ticket(ticket) for ticket in selected]
    quarterly = build_quarterly(metrics)
    write_jsonl(OUT_JSONL, metrics)
    write_csv(OUT_QUARTERLY, quarterly)
    eprint(f"wrote {len(metrics):,} ticket metrics to {OUT_JSONL}")
    eprint(f"wrote {len(quarterly):,} quarterly rows to {OUT_QUARTERLY}")


if __name__ == "__main__":
    main()
