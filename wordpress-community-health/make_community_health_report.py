#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import math
import os
import re
import sqlite3
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"
OUT = ROOT / "final_report.html"

CORE_ROOT = Path("/Users/admin/wordpress_core_issue_analysis")
GUT_ROOT = Path("/Users/admin/gutenberg_issue_analysis")
CLASS_ROOT = Path("/Users/admin/sqlite-database-integration-pages/wordpress-ticket-classification")

END = dt.datetime(2026, 6, 11, 23, 59, 59, tzinfo=dt.timezone.utc)
UA = "codex-wordpress-community-health/1.0"

SOURCE_FILES = {
    "core_quarterly": CORE_ROOT / "quarterly_metrics.csv",
    "core_tickets": CORE_ROOT / "raw" / "trac_tickets.csv",
    "core_events": CORE_ROOT / "raw" / "trac_ticket_events.csv",
    "github_pr_quarterly": CORE_ROOT / "github_pr_quarterly.csv",
    "github_prs": CORE_ROOT / "raw" / "github_wordpress_develop_prs.jsonl",
    "gutenberg_quarterly": GUT_ROOT / "quarterly_metrics.csv",
    "gutenberg_issues": GUT_ROOT / "issues_inventory.csv",
    "gutenberg_issues_jsonl": GUT_ROOT / "raw" / "issues_inventory.jsonl",
    "classification_trend": CLASS_ROOT / "classification_trend_quarterly.csv",
    "classification_summary_core": CLASS_ROOT / "classification_summary_core.csv",
    "classification_summary_gutenberg": CLASS_ROOT / "classification_summary_gutenberg.csv",
}

W3TECHS_USAGE_URL = "https://w3techs.com/technologies/history_overview/content_management/all/y"
W3TECHS_MARKET_SHARE_URL = "https://w3techs.com/technologies/history_overview/content_management/ms/y"
HTTP_ARCHIVE_CMS_URL = "https://almanac.httparchive.org/en/2025/cms"
PLUGIN_API = "https://api.wordpress.org/plugins/info/1.2/?action=query_plugins&request[page]=1&request[per_page]=1"
THEME_API = "https://api.wordpress.org/themes/info/1.2/?action=query_themes&request[page]=1&request[per_page]=1"
WORDCAMP_API = "https://central.wordcamp.org/wp-json/wp/v2/wordcamps"
EVENTS_WORDPRESS_URL = "https://events.wordpress.org/"
MAKE_CORE_API = "https://make.wordpress.org/core/wp-json/wp/v2/posts"
FTTF_PLEDGES_URL = "https://wordpress.org/five-for-the-future/pledges/"
RELEASE_ARCHIVE_URL = "https://wordpress.org/download/releases/"
CREDITS_API = "https://api.wordpress.org/core/credits/1.1/"
GITHUB_COMPARE_API = "https://api.github.com/repos/WordPress/wordpress-develop/compare"
CACHE = ROOT / "cache"

COLORS = {
    "core": "#2563eb",
    "gutenberg": "#16a34a",
    "green": "#16a34a",
    "prs": "#7c3aed",
    "community": "#ea580c",
    "member": "#0891b2",
    "orange": "#ea580c",
    "purple": "#7c3aed",
    "wordpress": "#2563eb",
    "shopify": "#16a34a",
    "wix": "#f59e0b",
    "squarespace": "#7c3aed",
    "neutral": "#64748b",
    "red": "#dc2626",
}


class HistTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_hist = False
        self.in_cell = False
        self.current_row = []
        self.current_cell = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table" and attrs.get("class") == "hist":
            self.in_hist = True
        elif self.in_hist and tag == "tr":
            self.current_row = []
        elif self.in_hist and tag in ("td", "th"):
            self.in_cell = True
            self.current_cell = []
        elif self.in_hist and tag == "br" and self.in_cell:
            self.current_cell.append(" ")

    def handle_endtag(self, tag):
        if self.in_hist and tag in ("td", "th") and self.in_cell:
            cell = re.sub(r"\s+", " ", "".join(self.current_cell)).strip()
            self.current_row.append(cell)
            self.in_cell = False
        elif self.in_hist and tag == "tr":
            if self.current_row:
                self.rows.append(self.current_row)
        elif self.in_hist and tag == "table":
            self.in_hist = False

    def handle_data(self, data):
        if self.in_hist and self.in_cell:
            self.current_cell.append(data)


def eprint(message):
    print(message, file=sys.stderr, flush=True)


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def read_jsonl(path):
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def parse_iso(value):
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    if re.match(r"^\d{9,}$", value):
        try:
            return dt.datetime.fromtimestamp(int(value), tz=dt.timezone.utc)
        except (OverflowError, ValueError):
            return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = dt.datetime.strptime(value[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def quarter_start(value):
    parsed = parse_iso(value)
    if not parsed:
        return None
    month = ((parsed.month - 1) // 3) * 3 + 1
    return f"{parsed.year:04d}-{month:02d}-01"


def quarter_label(value):
    parsed = parse_iso(value)
    if not parsed:
        return ""
    return f"{parsed.year}-Q{((parsed.month - 1) // 3) + 1}"


def quarter_label_to_start(value):
    match = re.match(r"^(\d{4})-Q([1-4])$", str(value or ""))
    if not match:
        return value
    year = int(match.group(1))
    quarter = int(match.group(2))
    month = (quarter - 1) * 3 + 1
    return f"{year:04d}-{month:02d}-01"


def year_start(value):
    parsed = parse_iso(value)
    if not parsed:
        return None
    return f"{parsed.year:04d}-01-01"


def num(value, default=0):
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def pct(value, digits=1):
    if value is None or math.isnan(value):
        return "n/a"
    return f"{value:.{digits}f}%"


def compact(value):
    if value is None:
        return "n/a"
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs(value) >= 10_000:
        return f"{value / 1_000:.1f}k"
    if abs(value) >= 1_000:
        return f"{value:,.0f}"
    if value == int(value):
        return f"{int(value)}"
    return f"{value:.1f}"


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace"), dict(resp.headers.items())


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8")), dict(resp.headers.items())


def credential_from_git():
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    return None


def next_link(headers):
    link = headers.get("Link") or headers.get("link") or ""
    for part in link.split(","):
        part = part.strip()
        if 'rel="next"' in part and part.startswith("<") and ">" in part:
            return part[1 : part.index(">")]
    return None


def github_json(url, token=None, use_cache=True):
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
    cache_path = CACHE / f"github-{cache_key}.json"
    if use_cache and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(cached, dict) and "data" in cached and "headers" in cached:
            headers = dict(cached["headers"])
            headers["X-Cache"] = "HIT"
            return cached["data"], headers
        return cached, {"X-Cache": "HIT"}
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": UA,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        response_headers = dict(resp.headers.items())
    if use_cache:
        cache_path.write_text(
            json.dumps({"data": data, "headers": response_headers}, ensure_ascii=True, sort_keys=True),
            encoding="utf-8",
        )
    return data, response_headers


def date_from_w3_header(cell):
    parts = cell.split()
    if not parts:
        return None
    year = int(parts[0])
    if len(parts) >= 3 and parts[2].isalpha():
        day = int(parts[1])
        month = dt.datetime.strptime(parts[2], "%b").month
        return f"{year:04d}-{month:02d}-{day:02d}"
    return f"{year:04d}-01-01"


def parse_percent(value):
    value = value.strip()
    if not value:
        return None
    if value.startswith("<"):
        return 0.05
    return float(value.rstrip("%"))


def parse_w3techs_hist_rows(body):
    match = re.search(r"<table class=hist>(.*?)</table>", body, re.S)
    if not match:
        return []
    rows = []
    for row_html in re.split(r"<tr>", match.group(1)):
        if not row_html.strip():
            continue
        cells = re.split(r"<t[dh][^>]*>", row_html)[1:]
        cleaned = []
        for cell in cells:
            cell = re.sub(r"<br\s*/?>", " ", cell, flags=re.I)
            cell = re.sub(r"<[^>]+>", "", cell)
            cell = html.unescape(cell)
            cell = re.sub(r"\s+", " ", cell).strip()
            cleaned.append(cell)
        if cleaned:
            rows.append(cleaned)
    return rows


def parse_w3techs_history(url, metric_name, skip_network=False):
    fallback = []
    if skip_network:
        return fallback
    try:
        body, _headers = fetch_text(url)
        hist_rows = parse_w3techs_hist_rows(body)
        if not hist_rows:
            return fallback
        dates = [date_from_w3_header(cell) for cell in hist_rows[0][1:]]
        rows = []
        for row in hist_rows[1:]:
            technology = row[0]
            if technology not in {"WordPress", "Shopify", "Wix", "Squarespace", "Joomla", "Drupal", "Webflow"}:
                continue
            for date_value, cell in zip(dates, row[1:]):
                parsed = parse_percent(cell)
                if parsed is not None:
                    rows.append(
                        {
                            "metric": metric_name,
                            "date": date_value,
                            "technology": technology,
                            "value": parsed,
                            "source_url": url,
                        }
                    )
        return rows
    except Exception as exc:
        eprint(f"w3techs fetch failed for {metric_name}: {exc}")
        return fallback


def fetch_wordpress_directory_snapshots(skip_network=False):
    if skip_network:
        return []
    snapshots = []
    for name, url in [("plugin_directory_plugins", PLUGIN_API), ("theme_directory_themes", THEME_API)]:
        try:
            data, _headers = fetch_json(url)
            info = data.get("info", {})
            snapshots.append(
                {
                    "metric": name,
                    "period": END.date().isoformat(),
                    "value": str(info.get("results", "")),
                    "source_url": url,
                    "raw_json": json.dumps(info, sort_keys=True),
                }
            )
        except Exception as exc:
            eprint(f"WordPress.org directory fetch failed for {name}: {exc}")
    return snapshots


def fetch_wordcamps(skip_network=False):
    if skip_network:
        return []
    rows = []
    page = 1
    total_pages = None
    while True:
        params = urllib.parse.urlencode({"per_page": 100, "page": page})
        try:
            data, headers = fetch_json(f"{WORDCAMP_API}?{params}")
        except urllib.error.HTTPError as exc:
            if exc.code == 400 and page > 1:
                break
            raise
        if total_pages is None:
            total_pages = int(headers.get("X-WP-TotalPages", "1") or 1)
        for item in data:
            start = item.get("Start Date (YYYY-mm-dd)") or item.get("date")
            rows.append(
                {
                    "id": str(item.get("id", "")),
                    "title": html.unescape((item.get("title") or {}).get("rendered", "")),
                    "start_date": str(start or ""),
                    "status": str(item.get("status", "")),
                    "url": str(item.get("URL") or item.get("link") or ""),
                    "raw_json": json.dumps(item, ensure_ascii=True, sort_keys=True),
                }
            )
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.05)
    return rows


def fetch_wordpress_events(skip_network=False):
    if skip_network:
        return [], []
    try:
        body, _headers = fetch_text(EVENTS_WORDPRESS_URL)
    except Exception as exc:
        eprint(f"events.wordpress.org fetch failed: {exc}")
        return [], []
    match = re.search(
        r'wporgGoogleMap\["all-upcoming-map"\]\s*=\s*(\{.*?\});\s*\n//# sourceURL=wporg-google-map-view-script-js-before',
        body,
        re.S,
    )
    if not match:
        eprint("events.wordpress.org payload not found")
        return [], []
    data = json.loads(match.group(1))
    event_rows = []
    for event in data.get("markers", []):
        timestamp = num(event.get("timestamp"))
        event_date = dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).date().isoformat() if timestamp else ""
        event_rows.append(
            {
                "id": str(event.get("id", "")),
                "type": str(event.get("type", "")),
                "title": str(event.get("title", "")),
                "url": str(event.get("url", "")),
                "meetup": str(event.get("meetup", "")),
                "location": str(event.get("location", "")),
                "latitude": str(event.get("latitude", "")),
                "longitude": str(event.get("longitude", "")),
                "tz_offset": str(event.get("tz_offset", "")),
                "timestamp": timestamp,
                "event_date": event_date,
                "source_url": EVENTS_WORDPRESS_URL,
            }
        )
    if not event_rows:
        return [], []
    event_types = Counter(row["type"] for row in event_rows)
    timestamps = [num(row.get("timestamp")) for row in event_rows if num(row.get("timestamp"))]
    snapshot = {
        "snapshot_date": END.date().isoformat(),
        "event_count": len(event_rows),
        "meetup_count": event_types.get("meetup", 0),
        "wordcamp_count": event_types.get("wordcamp", 0),
        "unique_meetup_groups": len({row["meetup"] for row in event_rows if row["meetup"]}),
        "online_count": sum(1 for row in event_rows if row.get("location") == "online"),
        "in_person_count": sum(1 for row in event_rows if row.get("location") != "online"),
        "first_event_date": dt.datetime.fromtimestamp(min(timestamps), tz=dt.timezone.utc).date().isoformat() if timestamps else "",
        "last_event_date": dt.datetime.fromtimestamp(max(timestamps), tz=dt.timezone.utc).date().isoformat() if timestamps else "",
        "source_url": EVENTS_WORDPRESS_URL,
    }
    return [snapshot], sorted(event_rows, key=lambda row: (row["event_date"], row["title"]))


def fetch_make_core_posts(skip_network=False):
    if skip_network:
        return []
    rows = []
    page = 1
    total_pages = None
    fields = "id,date,author,link,title"
    while True:
        params = urllib.parse.urlencode({"per_page": 100, "page": page, "_fields": fields})
        try:
            data, headers = fetch_json(f"{MAKE_CORE_API}?{params}")
        except urllib.error.HTTPError as exc:
            if exc.code == 400 and page > 1:
                break
            raise
        if total_pages is None:
            total_pages = int(headers.get("X-WP-TotalPages", "1") or 1)
        for item in data:
            rows.append(
                {
                    "id": str(item.get("id", "")),
                    "date": str(item.get("date", "")),
                    "author": str(item.get("author", "")),
                    "link": str(item.get("link", "")),
                    "title": html.unescape((item.get("title") or {}).get("rendered", "")),
                    "raw_json": json.dumps(item, ensure_ascii=True, sort_keys=True),
                }
            )
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.05)
    return rows


def parse_fttf_pledges_markdown(body, source_url):
    pledges = []
    contributors = []
    total_match = re.search(r"^(\d[\d,]*)\s+pledges\b", body, re.M)
    listed_total = num(total_match.group(1).replace(",", "")) if total_match else 0
    headings = list(
        re.finditer(
            r"##\s+.*?\[([^\]]+)\]\((https://wordpress\.org/five-for-the-future/pledge/[^)]+)\)",
            body,
        )
    )
    for index, match in enumerate(headings):
        name = re.sub(r"\s+", " ", match.group(1)).strip()
        url = match.group(2)
        slug = url.rstrip("/").split("/")[-1]
        block = body[match.end() : headings[index + 1].start() if index + 1 < len(headings) else len(body)]
        hours_match = re.search(r"pledges\s+([\d,.]+)\s+hours?\s+per week", block)
        hours = float(hours_match.group(1).replace(",", "")) if hours_match else 0.0
        profile_matches = re.findall(
            r"\[\s*⌊?([^\]⌉]+)⌉?\s*\]\(https://profiles\.wordpress\.org/([^/)]+)/\)",
            block,
        )
        plus_matches = [num(value) for value in re.findall(r"^\s*-\s+\+(\d+)\s*$", block, re.M)]
        hidden_count = sum(plus_matches)
        pledges.append(
            {
                "name": name,
                "slug": slug,
                "url": url,
                "hours_per_week": hours,
                "listed_contributors": len(profile_matches),
                "hidden_contributors": hidden_count,
                "known_or_hidden_contributors": len(profile_matches) + hidden_count,
                "source_url": source_url,
                "listed_total": listed_total,
            }
        )
        for contributor_name, contributor_slug in profile_matches:
            contributors.append(
                {
                    "pledge_slug": slug,
                    "pledge_name": name,
                    "contributor_name": re.sub(r"\s+", " ", contributor_name).strip(),
                    "contributor_slug": contributor_slug,
                    "profile_url": f"https://profiles.wordpress.org/{contributor_slug}/",
                    "source_url": source_url,
                }
            )
    return listed_total, pledges, contributors


def fetch_five_for_the_future_pledges(skip_network=False):
    if skip_network:
        return [], [], []
    all_pledges = {}
    all_contributors = {}
    snapshots = []
    listed_total = 0
    page = 1
    while True:
        source_url = FTTF_PLEDGES_URL if page == 1 else f"{FTTF_PLEDGES_URL}page/{page}/"
        url = source_url + "?output_format=md"
        try:
            body, _headers = fetch_text(url)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                break
            raise
        if "This page doesn’t exist" in body or "This page doesn't exist" in body:
            break
        page_total, pledges, contributors = parse_fttf_pledges_markdown(body, source_url)
        if not pledges:
            break
        listed_total = page_total or listed_total
        for pledge in pledges:
            all_pledges[pledge["slug"]] = pledge
        for contributor in contributors:
            all_contributors[(contributor["pledge_slug"], contributor["contributor_slug"])] = contributor
        page += 1
        time.sleep(0.05)
        if listed_total and len(all_pledges) >= listed_total:
            break
    pledge_rows = sorted(all_pledges.values(), key=lambda row: (-float(row["hours_per_week"]), row["name"].lower()))
    contributor_rows = sorted(all_contributors.values(), key=lambda row: (row["pledge_name"].lower(), row["contributor_slug"]))
    if pledge_rows:
        snapshots.append(
            {
                "snapshot_date": END.date().isoformat(),
                "pledges_listed_on_site": listed_total or len(pledge_rows),
                "pledges_fetched": len(pledge_rows),
                "pledged_hours_per_week": round(sum(float(row["hours_per_week"]) for row in pledge_rows), 2),
                "listed_contributor_profiles": len({row["contributor_slug"] for row in contributor_rows}),
                "pledge_pages_fetched": page - 1,
                "source_url": FTTF_PLEDGES_URL,
            }
        )
    return snapshots, pledge_rows, contributor_rows


def parse_release_archive_markdown(body):
    releases = {}
    row_re = re.compile(r"^\|\s*(?:\[)?(\d+\.\d+)(?:\]\([^)]+\))?\s*\|\s*([A-Z][a-z]+ \d{1,2}, \d{4})\s*\|", re.M)
    for version, date_label in row_re.findall(body):
        try:
            release_date = dt.datetime.strptime(date_label, "%B %d, %Y").date().isoformat()
        except ValueError:
            continue
        releases[version] = {
            "version": version,
            "release_date": release_date,
            "source_url": RELEASE_ARCHIVE_URL,
        }
    return sorted(releases.values(), key=lambda row: tuple(int(part) for part in row["version"].split(".")))


def parse_release_archive_html(body):
    releases = {}
    row_re = re.compile(
        r'<th class="wp-block-wporg-release-tables__cell-version"[^>]*>\s*(?:<a [^>]+>)?(\d+\.\d+)(?:</a>)?\s*</th>\s*'
        r'<td class="wp-block-wporg-release-tables__cell-date">([^<]+)</td>',
        re.S,
    )
    for version, date_label in row_re.findall(body):
        try:
            release_date = dt.datetime.strptime(html.unescape(date_label).strip(), "%B %d, %Y").date().isoformat()
        except ValueError:
            continue
        releases[version] = {
            "version": version,
            "release_date": release_date,
            "source_url": RELEASE_ARCHIVE_URL,
        }
    return sorted(releases.values(), key=lambda row: tuple(int(part) for part in row["version"].split(".")))


def fetch_core_release_credits(skip_network=False):
    if skip_network:
        return [], []
    try:
        body, _headers = fetch_text(RELEASE_ARCHIVE_URL)
    except Exception as exc:
        eprint(f"release archive fetch failed: {exc}")
        return [], []
    releases = parse_release_archive_html(body) or parse_release_archive_markdown(body)
    credit_rows = []
    for release in releases:
        version = release["version"]
        params = urllib.parse.urlencode({"version": version, "locale": "en_US"})
        source_url = f"{CREDITS_API}?{params}"
        try:
            data, _headers = fetch_json(source_url)
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 404):
                continue
            eprint(f"credits fetch failed for {version}: HTTP {exc.code}")
            continue
        except Exception as exc:
            eprint(f"credits fetch failed for {version}: {exc}")
            continue
        groups = data.get("groups", {})
        props = groups.get("props", {}).get("data") or {}
        noteworthy = groups.get("core-developers", {}).get("data") or {}
        contributing = groups.get("contributing-developers", {}).get("data") or {}
        props_users = set(props.keys()) if isinstance(props, dict) else set()
        noteworthy_users = set(noteworthy.keys()) if isinstance(noteworthy, dict) else set()
        contributing_users = set(contributing.keys()) if isinstance(contributing, dict) else set()
        credit_rows.append(
            {
                "version": version,
                "release_date": release["release_date"],
                "props_count": len(props_users),
                "noteworthy_count": len(noteworthy_users),
                "contributing_developers_count": len(contributing_users),
                "credited_people_count": len(props_users | noteworthy_users | contributing_users),
                "source_url": source_url,
            }
        )
        time.sleep(0.05)
    return releases, credit_rows


def version_tuple(version):
    return tuple(int(part) for part in str(version).split("."))


def release_tag(version):
    return f"{version}.0"


def commit_person(commit, role):
    user = commit.get(role) or {}
    if user.get("login"):
        return user["login"], user.get("html_url", "")
    raw = (commit.get("commit") or {}).get(role) or {}
    if raw.get("email"):
        return raw["email"].lower(), ""
    return raw.get("name") or "(unknown)", ""


def fetch_compare_commits(base_tag, head_tag, token, skip_network=False):
    if skip_network:
        return []
    url = f"{GITHUB_COMPARE_API}/{urllib.parse.quote(base_tag)}...{urllib.parse.quote(head_tag)}?per_page=100"
    commits = []
    while url:
        try:
            data, headers = github_json(url, token=token)
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 422):
                eprint(f"compare unavailable for {base_tag}...{head_tag}: HTTP {exc.code}")
                return commits
            raise
        commits.extend(data.get("commits", []))
        url = next_link(headers)
        if url:
            time.sleep(0.05)
    unique = {}
    for commit in commits:
        sha = commit.get("sha")
        if sha:
            unique[sha] = commit
    return list(unique.values())


def fetch_core_release_committers(releases, skip_network=False):
    if skip_network or not releases:
        return [], []
    token = credential_from_git()
    sorted_releases = sorted(releases, key=lambda row: version_tuple(row["version"]))
    release_by_version = {row["version"]: row for row in sorted_releases}
    summary_rows = []
    author_rows = []
    for index, release in enumerate(sorted_releases):
        version = release["version"]
        if version_tuple(version) < (3, 2) or index == 0:
            continue
        previous = sorted_releases[index - 1]
        base_tag = release_tag(previous["version"])
        head_tag = release_tag(version)
        commits = fetch_compare_commits(base_tag, head_tag, token, skip_network)
        if not commits:
            continue
        committer_counts = Counter()
        author_counts = Counter()
        commit_dates = []
        for commit in commits:
            committer, committer_url = commit_person(commit, "committer")
            author, _author_url = commit_person(commit, "author")
            committer_counts[(committer, committer_url)] += 1
            author_counts[author] += 1
            raw_date = ((commit.get("commit") or {}).get("committer") or {}).get("date")
            if raw_date:
                commit_dates.append(raw_date)
        total_commits = len(commits)
        top_committer, top_count = committer_counts.most_common(1)[0]
        summary_rows.append(
            {
                "version": version,
                "previous_version": previous["version"],
                "base_tag": base_tag,
                "head_tag": head_tag,
                "release_date": release_by_version[version]["release_date"],
                "commit_count": total_commits,
                "committer_count": len(committer_counts),
                "author_count": len(author_counts),
                "top_committer": top_committer[0],
                "top_committer_url": top_committer[1],
                "top_committer_commits": top_count,
                "top_committer_share": round(top_count / total_commits * 100, 2),
                "first_commit_at": min(commit_dates) if commit_dates else "",
                "last_commit_at": max(commit_dates) if commit_dates else "",
                "source_url": f"{GITHUB_COMPARE_API}/{base_tag}...{head_tag}",
            }
        )
        for (committer, committer_url), count in committer_counts.items():
            author_rows.append(
                {
                    "version": version,
                    "release_date": release_by_version[version]["release_date"],
                    "committer": committer,
                    "committer_url": committer_url,
                    "commit_count": count,
                    "source_url": f"{GITHUB_COMPARE_API}/{base_tag}...{head_tag}",
                }
            )
        eprint(f"committers {base_tag}...{head_tag}: {len(committer_counts)} committers, {total_commits} commits")
    return summary_rows, author_rows


def create_text_table(conn, name, rows):
    conn.execute(f"DROP TABLE IF EXISTS {name}")
    if not rows:
        conn.execute(f"CREATE TABLE {name} (empty TEXT)")
        return
    columns = sorted({key for row in rows for key in row.keys()})
    col_sql = ", ".join(f'"{col}" TEXT' for col in columns)
    conn.execute(f"CREATE TABLE {name} ({col_sql})")
    placeholders = ", ".join("?" for _ in columns)
    quoted = ", ".join(f'"{col}"' for col in columns)
    conn.executemany(
        f"INSERT INTO {name} ({quoted}) VALUES ({placeholders})",
        [[str(row.get(col, "")) for col in columns] for row in rows],
    )


def build_database(data, fetched):
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE source_files (
            table_name TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            rows INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            imported_at TEXT NOT NULL
        )
        """
    )
    imported_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    for table_name, path in SOURCE_FILES.items():
        if path.exists():
            conn.execute(
                "INSERT INTO source_files VALUES (?,?,?,?,?)",
                (table_name, str(path), len(data.get(table_name, [])), sha256_file(path), imported_at),
            )
    for table_name, rows in data.items():
        create_text_table(conn, table_name, rows)
    for table_name, rows in fetched.items():
        create_text_table(conn, table_name, rows)
    conn.execute(
        """
        CREATE TABLE source_gaps (
            signal TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            needed_source TEXT NOT NULL,
            note TEXT NOT NULL
        )
        """
    )
    gaps = [
        ("new_site_share", "missing", "BuiltWith paid trends or HTTP Archive cohort queries", "Current report uses all-site and CMS-share trends, not newly created site cohorts."),
        ("gutenberg_first_response", "missing", "GitHub issue comments/timeline events", "Existing issue export has comment counts but not first comment timestamps."),
        ("gutenberg_reopened_rate", "missing", "GitHub timeline events", "Existing issue export has current state and close date, not reopen transitions."),
        ("core_first_response", "missing", "Trac comments/change history with comment bodies", "Existing Core event export covers status transitions, not first non-reporter response."),
        ("support_forums", "missing", "WordPress.org support forum topic/resolution data", "Needs a dedicated source pull."),
    ]
    if not fetched.get("wp_events"):
        gaps.append(
            (
                "meetups",
                "missing",
                "Meetup or WordPress events source",
                "WordCamp data is included; broader Meetup chapter activity is not.",
            )
        )
    if not fetched.get("fttf_pledges"):
        gaps.append(
            (
                "five_for_the_future",
                "missing",
                "Five for the Future public pledge listing",
                "Needs a successful pledge listing fetch.",
            )
        )
    if not fetched.get("core_release_committers"):
        gaps.append(
            (
                "core_committers_per_release",
                "missing",
                "WordPress git commit history mapped to releases",
                "Core credits are included, but credited contributors are not the same as committers.",
            )
        )
    conn.executemany("INSERT INTO source_gaps VALUES (?,?,?,?)", gaps)
    conn.commit()
    conn.close()


def load_data():
    data = {}
    for table, path in SOURCE_FILES.items():
        if not path.exists():
            data[table] = []
        elif path.suffix == ".jsonl":
            data[table] = read_jsonl(path)
        else:
            data[table] = read_csv(path)
    return data


def point_series(rows, date_col, value_col, start=None):
    out = []
    for row in rows:
        date_value = row.get(date_col)
        if start and date_value < start:
            continue
        out.append((date_value, float(row.get(value_col) or 0)))
    return out


def series_from_counter(counter):
    return sorted((key, value) for key, value in counter.items())


def align_dates(series_list):
    dates = sorted({date for series in series_list for date, _value in series["points"] if date})
    return dates


def nice_ticks(max_value, count=4):
    if max_value <= 0:
        return [0]
    raw_step = max_value / count
    magnitude = 10 ** math.floor(math.log10(raw_step))
    step = min([1, 2, 5, 10], key=lambda x: abs(x * magnitude - raw_step)) * magnitude
    top = math.ceil(max_value / step) * step
    return [i * step for i in range(int(top / step) + 1)]


def svg_line_chart(title, note, series_list, height=330, y_suffix="", start_zero=True):
    width = 980
    left, right, top, bottom = 72, 42, 66, 58
    plot_w = width - left - right
    plot_h = height - top - bottom
    dates = align_dates(series_list)
    if not dates:
        return ""
    parsed_dates = [parse_iso(d) for d in dates]
    valid_dates = [p for p in parsed_dates if p]
    if not valid_dates:
        return ""
    x_min = min(p.timestamp() for p in valid_dates)
    x_max = max(p.timestamp() for p in valid_dates)
    if x_min == x_max:
        x_max = x_min + 1
    values = [value for series in series_list for _date, value in series["points"] if value is not None]
    y_min = 0 if start_zero else min(values)
    y_max = max(values) if values else 1
    if y_max == y_min:
        y_max = y_min + 1
    ticks = nice_ticks(y_max - (0 if start_zero else y_min), 4)
    y_top = ticks[-1] + (0 if start_zero else y_min)

    def x(date_value):
        parsed = parse_iso(date_value)
        return left + ((parsed.timestamp() - x_min) / (x_max - x_min)) * plot_w

    def y(value):
        return top + (1 - ((value - y_min) / (y_top - y_min))) * plot_h

    pieces = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">',
        f'<text x="{left}" y="28" class="chart-title">{html.escape(title)}</text>',
        f'<text x="{left}" y="50" class="chart-note">{html.escape(note)}</text>',
    ]
    for tick in ticks:
        tick_value = tick + (0 if start_zero else y_min)
        yy = y(tick_value)
        pieces.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{width-right}" y2="{yy:.1f}" class="grid" />')
        pieces.append(f'<text x="{left-12}" y="{yy+4:.1f}" class="axis" text-anchor="end">{compact(tick_value)}{y_suffix}</text>')
    is_yearly = all((parse_iso(d) and parse_iso(d).month == 1 and parse_iso(d).day == 1) for d in dates)
    is_quarterly = all((parse_iso(d) and parse_iso(d).month in {1, 4, 7, 10} and parse_iso(d).day == 1) for d in dates)

    def axis_label(date_value):
        parsed = parse_iso(date_value)
        if not parsed:
            return str(date_value)
        if is_yearly:
            return str(parsed.year)
        if is_quarterly:
            return quarter_label(date_value)
        return parsed.strftime("%b '%y")

    x_ticks = dates if len(dates) <= 6 else [dates[round(i * (len(dates) - 1) / 5)] for i in range(6)]
    seen = set()
    for date_value in x_ticks:
        if date_value in seen:
            continue
        seen.add(date_value)
        xx = x(date_value)
        pieces.append(f'<text x="{xx:.1f}" y="{height-22}" class="axis" text-anchor="middle">{html.escape(axis_label(date_value))}</text>')
    pieces.append(f'<line x1="{left}" y1="{top+plot_h}" x2="{width-right}" y2="{top+plot_h}" class="axis-line" />')
    pieces.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" class="axis-line" />')
    legend_x = left
    for series in series_list:
        color = series["color"]
        label = series["label"]
        pieces.append(f'<circle cx="{legend_x}" cy="{height-8}" r="5" fill="{color}" />')
        pieces.append(f'<text x="{legend_x+10}" y="{height-4}" class="legend">{html.escape(label)}</text>')
        legend_x += max(120, len(label) * 8 + 42)
    for series in series_list:
        points = [(d, v) for d, v in series["points"] if d and v is not None]
        if not points:
            continue
        path = " ".join(("M" if i == 0 else "L") + f"{x(d):.1f},{y(v):.1f}" for i, (d, v) in enumerate(points))
        pieces.append(f'<path d="{path}" fill="none" stroke="{series["color"]}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />')
        for d, v in points[-1:]:
            pieces.append(f'<circle cx="{x(d):.1f}" cy="{y(v):.1f}" r="4" fill="{series["color"]}" />')
            pieces.append(f'<text x="{min(width-right-70, x(d)+8):.1f}" y="{y(v)-8:.1f}" class="end-label" fill="{series["color"]}">{compact(v)}{y_suffix}</text>')
    pieces.append("</svg>")
    return "\n".join(pieces)


def stat_card(label, value, note="", tone="neutral"):
    return f"""
    <div class="stat {tone}">
      <div class="stat-label">{html.escape(label)}</div>
      <div class="stat-value">{html.escape(str(value))}</div>
      <div class="stat-note">{html.escape(note)}</div>
    </div>
    """


def signal_card(title, verdict, detail, tone="neutral"):
    return f"""
    <article class="signal {tone}">
      <h3>{html.escape(title)}</h3>
      <strong>{html.escape(verdict)}</strong>
      <p>{html.escape(detail)}</p>
    </article>
    """


def horizontal_metric(label, value, max_value, color):
    width = 100 if max_value <= 0 else max(2, min(100, value / max_value * 100))
    return f"""
    <div class="hmetric">
      <div class="hmetric-top"><span>{html.escape(label)}</span><strong>{pct(value)}</strong></div>
      <div class="bar"><span style="width:{width:.1f}%;background:{color}"></span></div>
    </div>
    """


def horizontal_count_metric(label, value, max_value, color, suffix=""):
    width = 100 if max_value <= 0 else max(2, min(100, value / max_value * 100))
    value_label = f"{compact(value)}{suffix}"
    return f"""
    <div class="hmetric">
      <div class="hmetric-top"><span>{html.escape(label)}</span><strong>{html.escape(value_label)}</strong></div>
      <div class="bar"><span style="width:{width:.1f}%;background:{color}"></span></div>
    </div>
    """


def average(rows, col, start=None, end=None):
    vals = []
    for row in rows:
        q = row.get("quarter")
        if start and q < start:
            continue
        if end and q >= end:
            continue
        vals.append(num(row.get(col)))
    return sum(vals) / len(vals) if vals else 0


def compute_close_age_core(core_tickets, core_events):
    created = {str(row["id"]): parse_iso(row.get("created_at")) for row in core_tickets}
    close_events = defaultdict(list)
    reopened_tickets = set()
    for event in core_events:
        ticket_id = str(event.get("ticket_id"))
        if event.get("event_type") == "closed":
            close_events[ticket_id].append(parse_iso(event.get("event_at")))
        elif event.get("event_type") == "reopened":
            reopened_tickets.add(ticket_id)
    by_quarter = defaultdict(list)
    for ticket_id, closes in close_events.items():
        start = created.get(ticket_id)
        closes = [c for c in closes if c]
        if not start or not closes:
            continue
        final_close = max(closes)
        days = (final_close - start).total_seconds() / 86400
        by_quarter[quarter_start(final_close.isoformat())].append(days)
    points = [(q, median(v)) for q, v in sorted(by_quarter.items()) if median(v) is not None]
    return points, reopened_tickets, set(close_events.keys())


def compute_close_age_gutenberg(gutenberg_jsonl):
    by_quarter = defaultdict(list)
    for issue in gutenberg_jsonl:
        created = parse_iso(issue.get("created_at"))
        closed = parse_iso(issue.get("closed_at"))
        if not created or not closed:
            continue
        days = (closed - created).total_seconds() / 86400
        by_quarter[quarter_start(closed.isoformat())].append(days)
    return [(q, median(v)) for q, v in sorted(by_quarter.items()) if median(v) is not None]


def contributor_concentration(rows, author_key, date_key=None, since=None):
    counts = Counter()
    for row in rows:
        if since and date_key and str(row.get(date_key, "")) < since:
            continue
        author = str(row.get(author_key) or "").strip() or "(unknown)"
        counts[author] += 1
    total = sum(counts.values())
    if not total:
        return {"total": 0, "unique": 0, "one_time_share": 0, "top10": 0, "top25": 0, "top50": 0}
    ordered = [count for _name, count in counts.most_common()]
    return {
        "total": total,
        "unique": len(counts),
        "one_time_share": sum(1 for count in counts.values() if count == 1) / len(counts) * 100,
        "top10": sum(ordered[:10]) / total * 100,
        "top25": sum(ordered[:25]) / total * 100,
        "top50": sum(ordered[:50]) / total * 100,
    }


def stale_open_share_core(core_tickets):
    cutoff = END - dt.timedelta(days=365)
    open_rows = [row for row in core_tickets if (row.get("status") or "").lower() != "closed"]
    stale = [row for row in open_rows if (parse_iso(row.get("modified_at")) or END) < cutoff]
    return len(stale), len(open_rows), len(stale) / len(open_rows) * 100 if open_rows else 0


def stale_open_share_gutenberg(gutenberg_jsonl):
    cutoff = END - dt.timedelta(days=365)
    open_rows = [row for row in gutenberg_jsonl if row.get("state") == "open"]
    stale = [row for row in open_rows if (parse_iso(row.get("updated_at")) or END) < cutoff]
    return len(stale), len(open_rows), len(stale) / len(open_rows) * 100 if open_rows else 0


def count_by_quarter(rows, date_key, value_key=None, distinct_key=None):
    buckets = defaultdict(set if distinct_key else int)
    for row in rows:
        q = quarter_start(row.get(date_key))
        if not q:
            continue
        if distinct_key:
            buckets[q].add(row.get(distinct_key))
        else:
            buckets[q] += num(row.get(value_key), 1) if value_key else 1
    if distinct_key:
        return [(q, len(values)) for q, values in sorted(buckets.items())]
    return [(q, value) for q, value in sorted(buckets.items())]


def count_by_year(rows, date_key, distinct_key=None):
    buckets = defaultdict(set if distinct_key else int)
    for row in rows:
        y = year_start(row.get(date_key))
        if not y:
            continue
        if distinct_key:
            buckets[y].add(row.get(distinct_key))
        else:
            buckets[y] += 1
    if distinct_key:
        return [(y, len(values)) for y, values in sorted(buckets.items())]
    return [(y, value) for y, value in sorted(buckets.items())]


def count_by_month(rows, date_key, type_filter=None):
    buckets = defaultdict(int)
    for row in rows:
        if type_filter and row.get("type") != type_filter:
            continue
        parsed = parse_iso(row.get(date_key))
        if not parsed:
            continue
        buckets[f"{parsed.year:04d}-{parsed.month:02d}-01"] += 1
    return sorted((key, value) for key, value in buckets.items())


def current_latest(rows, date_col="quarter"):
    return max(rows, key=lambda row: row.get(date_col, "")) if rows else {}


def market_latest(rows, metric, tech):
    candidates = [row for row in rows if row["metric"] == metric and row["technology"] == tech]
    if not candidates:
        return None
    return max(candidates, key=lambda row: row["date"])


def source_status_rows(fetched):
    rows = [
        ("Core Trac tickets", "covered", "64k tickets, status history, types, components, reporters"),
        ("Gutenberg GitHub issues", "covered", "32k issues with labels, state, authors, close dates"),
        ("wordpress-develop PRs", "covered", "12k PRs with authors, dates, Trac links"),
        ("Ticket category classification", "covered", "Bug, feature request, enhancement, task, and other categories"),
        ("W3Techs adoption", "covered" if fetched.get("market_share") else "missing", "All-site usage and CMS market-share yearly trends"),
        ("HTTP Archive/Web Almanac", "covered", "2025 CMS adoption snapshot and high-traffic context"),
        ("WordPress.org plugin/theme directories", "covered" if fetched.get("directory_snapshots") else "missing", "Current plugin and theme counts"),
        ("WordCamp Central", "covered" if fetched.get("wordcamps") else "missing", "Historical WordCamp event records"),
        ("WordPress Events", "covered" if fetched.get("wp_events") else "missing", "Current upcoming Meetup and WordCamp events"),
        ("Make/Core posts", "covered" if fetched.get("make_core_posts") else "missing", "Post counts and author IDs"),
        ("Core release credits", "covered" if fetched.get("core_release_credits") else "missing", "WordPress.org credits API props by major release"),
        ("Core committers per release", "covered" if fetched.get("core_release_committers") else "missing", "GitHub tag-to-tag compare ranges by major release"),
        ("Five for the Future", "covered" if fetched.get("fttf_pledges") else "missing", "Current pledge organizations, hours, and listed profiles"),
        ("Newly created sites", "missing", "Needs BuiltWith cohort/trend data or HTTP Archive cohort queries"),
        ("First response time", "missing", "Needs comments/timeline data for Core and Gutenberg"),
        ("Gutenberg reopen rate", "missing", "Needs GitHub issue timeline events"),
        ("Support forums", "missing", "Needs WordPress.org forum topic and resolution data"),
    ]
    return rows


def build_report(data, fetched):
    core_q = data["core_quarterly"]
    gut_q = data["gutenberg_quarterly"]
    core_tickets = data["core_tickets"]
    core_events = data["core_events"]
    gut_issues = data["gutenberg_issues"]
    gut_jsonl = data["gutenberg_issues_jsonl"]
    github_q = data["github_pr_quarterly"]
    github_prs = data["github_prs"]
    classifications = data["classification_trend"]
    market_rows = fetched.get("market_share", [])
    wordcamps = fetched.get("wordcamps", [])
    wp_event_snapshots = fetched.get("wp_event_snapshots", [])
    wp_events = fetched.get("wp_events", [])
    make_posts = fetched.get("make_core_posts", [])
    release_credits = fetched.get("core_release_credits", [])
    release_committers = fetched.get("core_release_committers", [])
    fttf_snapshots = fetched.get("fttf_snapshots", [])
    fttf_pledges = fetched.get("fttf_pledges", [])
    directory = {row["metric"]: row for row in fetched.get("directory_snapshots", [])}

    core_latest = current_latest(core_q)
    gut_latest = current_latest(gut_q)
    pr_latest = current_latest(github_q)

    core_created_prev = average(core_q, "created", "2021-01-01", "2024-01-01")
    core_created_recent = average(core_q, "created", "2024-01-01")
    core_first_prev = average(core_q, "first_time_reporters", "2021-01-01", "2024-01-01")
    core_first_recent = average(core_q, "first_time_reporters", "2024-01-01")
    gut_created_prev = average(gut_q, "created", "2021-01-01", "2024-01-01")
    gut_created_recent = average(gut_q, "created", "2024-01-01")
    gut_first_prev = average(gut_q, "first_time_creators", "2021-01-01", "2024-01-01")
    gut_first_recent = average(gut_q, "first_time_creators", "2024-01-01")
    pr_created_prev = average(github_q, "created", "2021-01-01", "2024-01-01")
    pr_created_recent = average(github_q, "created", "2024-01-01")

    core_close_age, core_reopened, core_closed_ids = compute_close_age_core(core_tickets, core_events)
    gut_close_age = compute_close_age_gutenberg(gut_jsonl)
    core_stale, core_open, core_stale_pct = stale_open_share_core(core_tickets)
    gut_stale, gut_open, gut_stale_pct = stale_open_share_gutenberg(gut_jsonl)
    reopened_pct = len(core_reopened) / len(core_closed_ids) * 100 if core_closed_ids else 0

    core_conc_all = contributor_concentration(core_tickets, "reporter", "created_at")
    core_conc_recent = contributor_concentration(core_tickets, "reporter", "created_at", "2024-01-01")
    gut_conc_all = contributor_concentration(gut_issues, "author_login", "created_at")
    gut_conc_recent = contributor_concentration(gut_issues, "author_login", "created_at", "2024-01-01")
    pr_conc_recent = contributor_concentration(github_prs, "author_login", "created_at", "2024-01-01")

    wp_usage_latest = market_latest(market_rows, "all_sites_usage", "WordPress")
    wp_usage_2025 = next((r for r in market_rows if r["metric"] == "all_sites_usage" and r["technology"] == "WordPress" and r["date"] == "2025-01-01"), None)
    wp_cms_latest = market_latest(market_rows, "cms_market_share", "WordPress")
    wp_cms_2025 = next((r for r in market_rows if r["metric"] == "cms_market_share" and r["technology"] == "WordPress" and r["date"] == "2025-01-01"), None)
    usage_delta = (wp_usage_latest["value"] - wp_usage_2025["value"]) if wp_usage_latest and wp_usage_2025 else None
    cms_delta = (wp_cms_latest["value"] - wp_cms_2025["value"]) if wp_cms_latest and wp_cms_2025 else None

    member_points = point_series(gut_q, "quarter", "member_created", "2021-01-01")
    community_points = point_series(gut_q, "quarter", "community_created", "2021-01-01")
    core_make_posts = count_by_quarter(make_posts, "date")
    core_make_authors = count_by_quarter(make_posts, "date", distinct_key="author")
    wordcamp_years = count_by_year(wordcamps, "start_date")
    release_credit_points = [(row["release_date"], num(row.get("props_count"))) for row in release_credits]
    release_noteworthy_points = [(row["release_date"], num(row.get("noteworthy_count"))) for row in release_credits]
    latest_release_credit = max(release_credits, key=lambda row: row.get("release_date", "")) if release_credits else {}
    release_committer_points = [(row["release_date"], num(row.get("committer_count"))) for row in release_committers]
    latest_release_committer = max(release_committers, key=lambda row: row.get("release_date", "")) if release_committers else {}
    fttf_snapshot = fttf_snapshots[0] if fttf_snapshots else {}
    top_fttf_pledges = sorted(fttf_pledges, key=lambda row: float(row.get("hours_per_week") or 0), reverse=True)[:8]
    max_fttf_hours = max([float(row.get("hours_per_week") or 0) for row in top_fttf_pledges] or [0])
    wp_event_snapshot = wp_event_snapshots[0] if wp_event_snapshots else {}
    event_group_counts = Counter(row.get("meetup") for row in wp_events if row.get("meetup"))
    top_event_groups = event_group_counts.most_common(8)
    max_event_group_count = max([count for _group, count in top_event_groups] or [0])
    event_month_points = count_by_month(wp_events, "event_date")
    meetup_month_points = count_by_month(wp_events, "event_date", "meetup")
    wordcamp_month_points = count_by_month(wp_events, "event_date", "wordcamp")

    classification_by_source_cat = defaultdict(int)
    for row in classifications:
        q = row.get("quarter", "")
        if not q:
            continue
        date_value = quarter_label_to_start(q)
        key = (row.get("source"), row.get("category"), date_value)
        classification_by_source_cat[key] += num(row.get("count"))
    combined_cat = defaultdict(int)
    for (_source, category, date_value), value in classification_by_source_cat.items():
        if date_value >= "2021-01-01":
            combined_cat[(category, date_value)] += value
    cat_series = []
    for category, color, label in [
        ("bug", COLORS["red"], "Bugs"),
        ("feature_request", COLORS["core"], "Feature requests"),
        ("enhancement", COLORS["community"], "Enhancements"),
        ("task_maintenance", COLORS["neutral"], "Tasks"),
    ]:
        points = sorted((date_value, value) for (cat, date_value), value in combined_cat.items() if cat == category)
        cat_series.append({"label": label, "color": color, "points": points})

    market_usage_series = []
    market_cms_series = []
    for tech, color in [("WordPress", COLORS["wordpress"]), ("Shopify", COLORS["shopify"]), ("Wix", COLORS["wix"]), ("Squarespace", COLORS["squarespace"])]:
        market_usage_series.append(
            {
                "label": tech,
                "color": color,
                "points": sorted((r["date"], r["value"]) for r in market_rows if r["metric"] == "all_sites_usage" and r["technology"] == tech),
            }
        )
        market_cms_series.append(
            {
                "label": tech,
                "color": color,
                "points": sorted((r["date"], r["value"]) for r in market_rows if r["metric"] == "cms_market_share" and r["technology"] == tech),
            }
        )

    plugin_count = num(directory.get("plugin_directory_plugins", {}).get("value"))
    theme_count = num(directory.get("theme_directory_themes", {}).get("value"))

    adoption_detail = "Still dominant"
    if usage_delta is not None and cms_delta is not None:
        adoption_detail = f"W3Techs has WordPress at {pct(wp_usage_latest['value'])} of all sites and {pct(wp_cms_latest['value'])} of CMS sites, down {abs(usage_delta):.1f} and {abs(cms_delta):.1f} points since Jan 2025."

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WordPress Community & Adoption Health</title>
<style>
:root {{
  --ink:#172033;
  --muted:#5b6475;
  --line:#d9e0ea;
  --soft:#f4f7fb;
  --blue:#2563eb;
  --green:#16a34a;
  --orange:#ea580c;
  --purple:#7c3aed;
  --red:#dc2626;
  --slate:#334155;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0;
  color:var(--ink);
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  background:#ffffff;
}}
a {{ color:var(--blue); }}
.page {{ max-width:1180px; margin:0 auto; padding:32px 24px 60px; }}
.eyebrow {{ color:var(--muted); text-transform:uppercase; letter-spacing:.08em; font-size:12px; font-weight:700; }}
h1 {{ margin:6px 0 8px; font-size:42px; line-height:1.05; letter-spacing:0; }}
h2 {{ margin:34px 0 12px; font-size:26px; letter-spacing:0; }}
h3 {{ margin:0 0 8px; font-size:17px; letter-spacing:0; }}
p {{ margin:0 0 12px; }}
.lede {{ max-width:820px; color:#344054; font-size:18px; }}
.nav {{ display:flex; flex-wrap:wrap; gap:10px; margin:24px 0 18px; }}
.nav a {{ text-decoration:none; color:var(--ink); border:1px solid var(--line); padding:8px 12px; border-radius:999px; background:#fff; }}
.answer-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin:24px 0 26px; }}
.signal {{ border:1px solid var(--line); border-top:5px solid var(--slate); padding:16px; border-radius:8px; min-height:178px; background:#fff; }}
.signal strong {{ display:block; font-size:21px; line-height:1.15; margin-bottom:8px; }}
.signal p {{ color:var(--muted); margin:0; }}
.signal.good {{ border-top-color:var(--green); }}
.signal.watch {{ border-top-color:var(--orange); }}
.signal.soft {{ border-top-color:var(--blue); }}
.signal.slower {{ border-top-color:var(--red); }}
.section {{ margin-top:22px; padding-top:8px; }}
.grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; align-items:start; }}
.stats {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:14px 0 18px; }}
.stat {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:var(--soft); }}
.stat-label {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; font-weight:700; }}
.stat-value {{ font-size:28px; font-weight:800; margin:4px 0; }}
.stat-note {{ color:var(--muted); font-size:13px; }}
.card {{ border:1px solid var(--line); border-radius:8px; padding:16px; background:#fff; }}
.chart {{ width:100%; height:auto; display:block; border:1px solid var(--line); border-radius:8px; background:#fff; margin:14px 0; }}
.chart-title {{ font-size:20px; font-weight:800; fill:var(--ink); }}
.chart-note {{ font-size:13px; fill:var(--muted); }}
.axis, .legend, .end-label {{ font-size:12px; fill:var(--muted); }}
.end-label {{ font-weight:800; }}
.grid {{ stroke:#e8edf4; stroke-width:1; }}
.axis-line {{ stroke:#b8c2d1; stroke-width:1; }}
.hmetric {{ margin:11px 0; }}
.hmetric-top {{ display:flex; justify-content:space-between; gap:12px; font-size:13px; }}
.hmetric-top span {{ color:var(--muted); }}
.bar {{ height:9px; border-radius:999px; background:#eef2f7; overflow:hidden; margin-top:5px; }}
.bar span {{ display:block; height:100%; border-radius:999px; }}
.callout {{ border-left:5px solid var(--blue); background:#f7fbff; padding:14px 16px; border-radius:8px; color:#334155; }}
.status-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }}
.status {{ border:1px solid var(--line); border-radius:8px; padding:13px; background:#fff; }}
.status b {{ display:block; }}
.status span {{ color:var(--muted); font-size:13px; }}
.pill {{ display:inline-block; border-radius:999px; padding:2px 8px; font-size:12px; font-weight:800; margin-bottom:7px; }}
.covered .pill {{ background:#dcfce7; color:#166534; }}
.missing .pill {{ background:#fee2e2; color:#991b1b; }}
.footer {{ color:var(--muted); font-size:13px; margin-top:32px; border-top:1px solid var(--line); padding-top:18px; }}
@media (max-width:900px) {{
  h1 {{ font-size:34px; }}
  .answer-grid, .grid-2, .stats, .status-grid {{ grid-template-columns:1fr; }}
  .page {{ padding:24px 16px 48px; }}
}}
</style>
</head>
<body>
<main class="page">
  <div class="eyebrow">WordPress community and adoption health</div>
  <h1>WordPress is still the default CMS, but the signals are softer.</h1>
  <p class="lede">This report combines Core Trac, Gutenberg GitHub issues, wordpress-develop PRs, WordPress.org ecosystem data, WordCamp records, Make/Core posts, W3Techs market-share trends, and HTTP Archive context. Ticket data explains project load. Market data explains whether people still choose WordPress.</p>

  <nav class="nav">
    <a href="#participation">Participation</a>
    <a href="#load">Project Load</a>
    <a href="#market">Market Position</a>
    <a href="#coverage">Source Coverage</a>
  </nav>

  <section class="answer-grid">
    {signal_card("Adoption", "Dominant, softer recently", adoption_detail, "watch")}
    {signal_card("Participation", "Fewer new reporters", f"Core first-time reporters averaged {compact(core_first_prev)} per quarter in 2021-2023 and {compact(core_first_recent)} since 2024. Gutenberg moved from {compact(gut_first_prev)} to {compact(gut_first_recent)}.", "slower")}
    {signal_card("Project load", "Closer to balanced", f"Since 2024, Core closures slightly exceed new tickets on average. Gutenberg is close to flat, with the latest sampled quarter closing {compact(num(gut_latest.get('closed')))} against {compact(num(gut_latest.get('created')))} new issues.", "soft")}
    {signal_card("Code review", "PR flow is higher", f"wordpress-develop PR creation averaged {compact(pr_created_prev)} per quarter in 2021-2023 and {compact(pr_created_recent)} since 2024.", "good")}
  </section>

  <section class="stats">
    {stat_card("Core open tickets", compact(num(core_latest.get("open_at_end"))), f"latest quarter {core_latest.get('label','')}", "soft")}
    {stat_card("Gutenberg open issues", compact(num(gut_latest.get("open_at_end"))), f"latest quarter {quarter_label(gut_latest.get('quarter',''))}", "soft")}
    {stat_card("Open Core stale share", pct(core_stale_pct), f"{compact(core_stale)} of {compact(core_open)} open tickets", "watch")}
    {stat_card("Open Gutenberg stale share", pct(gut_stale_pct), f"{compact(gut_stale)} of {compact(gut_open)} open issues", "watch")}
  </section>

  <section id="participation" class="section">
    <h2>Participation</h2>
    <p class="callout">The main participation change is not a collapse. It is fewer first-time and unique reporters in the trackers, while PR authorship is steadier and recent PR volume is higher.</p>
    {svg_line_chart("People opening issues and PRs by quarter", "Unique Core ticket reporters, Gutenberg issue creators, and wordpress-develop PR authors.", [
        {"label": "Core reporters", "color": COLORS["core"], "points": point_series(core_q, "quarter", "unique_reporters", "2021-01-01")},
        {"label": "Gutenberg creators", "color": COLORS["gutenberg"], "points": point_series(gut_q, "quarter", "unique_creators", "2021-01-01")},
        {"label": "PR authors", "color": COLORS["prs"], "points": point_series(github_q, "quarter", "unique_authors", "2021-01-01")},
    ])}
    {svg_line_chart("First-time participation by quarter", "New people are still arriving, but first-time tracker participation is lower than the 2021-2023 baseline.", [
        {"label": "Core first-time reporters", "color": COLORS["core"], "points": point_series(core_q, "quarter", "first_time_reporters", "2021-01-01")},
        {"label": "Gutenberg first-time creators", "color": COLORS["gutenberg"], "points": point_series(gut_q, "quarter", "first_time_creators", "2021-01-01")},
        {"label": "PR first-time authors", "color": COLORS["prs"], "points": point_series(github_q, "quarter", "first_time_authors", "2021-01-01")},
    ])}
    <div class="grid-2">
      <div>
        {svg_line_chart("Gutenberg issue origin", "GitHub exposes author association, so this can split member and community-created issues.", [
            {"label": "Member-created", "color": COLORS["member"], "points": member_points},
            {"label": "Community-created", "color": COLORS["community"], "points": community_points},
        ])}
      </div>
      <div class="card">
        <h3>Contributor concentration</h3>
        <p>Opening work is broad, but a meaningful share still comes from the most active people. The recent window starts in 2024.</p>
        {horizontal_metric("Core top 10 reporters, all time", core_conc_all["top10"], 100, COLORS["core"])}
        {horizontal_metric("Core top 10 reporters, since 2024", core_conc_recent["top10"], 100, COLORS["core"])}
        {horizontal_metric("Gutenberg top 10 creators, all time", gut_conc_all["top10"], 100, COLORS["gutenberg"])}
        {horizontal_metric("Gutenberg top 10 creators, since 2024", gut_conc_recent["top10"], 100, COLORS["gutenberg"])}
        {horizontal_metric("wordpress-develop top 10 PR authors, since 2024", pr_conc_recent["top10"], 100, COLORS["prs"])}
      </div>
    </div>
    <div class="grid-2">
      {svg_line_chart("Make/Core publishing activity", "Posts and unique author IDs per quarter from make.wordpress.org/core.", [
          {"label": "Posts", "color": COLORS["core"], "points": core_make_posts},
          {"label": "Authors", "color": COLORS["community"], "points": core_make_authors},
      ])}
      {svg_line_chart("WordCamp records by year", "WordCamp Central event records by start year. Recent future/scheduled records may be incomplete.", [
          {"label": "WordCamps", "color": COLORS["gutenberg"], "points": wordcamp_years},
      ])}
    </div>
    <div class="grid-2">
      {svg_line_chart("Upcoming WordPress events by month", "Current events.wordpress.org listing, including Meetups and WordCamps.", [
          {"label": "All events", "color": COLORS["core"], "points": event_month_points},
          {"label": "Meetups", "color": COLORS["gutenberg"], "points": meetup_month_points},
          {"label": "WordCamps", "color": COLORS["community"], "points": wordcamp_month_points},
      ])}
      <div class="card">
        <h3>Upcoming event snapshot</h3>
        <p>Current events.wordpress.org map payload. This captures scheduled upcoming activity, not historical attendance.</p>
        <div class="stats">
          {stat_card("Upcoming events", compact(num(wp_event_snapshot.get("event_count"))), f"{wp_event_snapshot.get('first_event_date', '')} to {wp_event_snapshot.get('last_event_date', '')}", "good")}
          {stat_card("Meetups", compact(num(wp_event_snapshot.get("meetup_count"))), "scheduled meetup events", "good")}
          {stat_card("Groups", compact(num(wp_event_snapshot.get("unique_meetup_groups"))), "unique meetup groups", "good")}
          {stat_card("Online", compact(num(wp_event_snapshot.get("online_count"))), "online events", "soft")}
        </div>
      </div>
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>Most active upcoming Meetup groups</h3>
        <p>Groups with the most scheduled upcoming events in the current Events listing.</p>
        {''.join(horizontal_count_metric(group, count, max_event_group_count, COLORS["gutenberg"], " events") for group, count in top_event_groups)}
      </div>
      <div class="card">
        <h3>Event mix</h3>
        <p>Meetups dominate the upcoming event calendar; WordCamps remain visible as larger scheduled events.</p>
        {horizontal_count_metric("Meetups", num(wp_event_snapshot.get("meetup_count")), max(1, num(wp_event_snapshot.get("event_count"))), COLORS["gutenberg"], "")}
        {horizontal_count_metric("WordCamps", num(wp_event_snapshot.get("wordcamp_count")), max(1, num(wp_event_snapshot.get("event_count"))), COLORS["community"], "")}
        {horizontal_count_metric("In-person or location-listed", num(wp_event_snapshot.get("in_person_count")), max(1, num(wp_event_snapshot.get("event_count"))), COLORS["core"], "")}
        {horizontal_count_metric("Online", num(wp_event_snapshot.get("online_count")), max(1, num(wp_event_snapshot.get("event_count"))), COLORS["prs"], "")}
      </div>
    </div>
    <div class="grid-2">
      {svg_line_chart("Core credited contributors by release", "WordPress.org credits API props count by major release. This is credited contributors, not unique committers.", [
          {"label": "Props", "color": COLORS["core"], "points": release_credit_points},
          {"label": "Noteworthy contributors", "color": COLORS["community"], "points": release_noteworthy_points},
      ])}
      <div class="card">
        <h3>Release credits</h3>
        <p>Credits are a broader community signal than commit access. They include people credited in release props, including non-committers.</p>
        {stat_card("Latest credited release", latest_release_credit.get("version", "n/a"), latest_release_credit.get("release_date", ""), "soft")}
        {stat_card("Props on latest release", compact(num(latest_release_credit.get("props_count"))), "WordPress.org credits API", "good")}
      </div>
    </div>
    <div class="grid-2">
      {svg_line_chart("Core committers by release", "Unique git committers in wordpress-develop tag-to-tag release ranges.", [
          {"label": "Committers", "color": COLORS["prs"], "points": release_committer_points},
      ])}
      <div class="card">
        <h3>Commit windows</h3>
        <p>This uses exact GitHub compare ranges between release tags, so it is narrower than credits and closer to commit access/activity.</p>
        {stat_card("Latest release committers", compact(num(latest_release_committer.get("committer_count"))), latest_release_committer.get("version", ""), "good")}
        {stat_card("Latest release commits", compact(num(latest_release_committer.get("commit_count"))), f"{latest_release_committer.get('base_tag', '')} to {latest_release_committer.get('head_tag', '')}", "soft")}
      </div>
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>Five for the Future pledge snapshot</h3>
        <p>Current pledge listing from WordPress.org. This is a present-day ecosystem signal, not a historical trend.</p>
        <div class="stats">
          {stat_card("Pledges", compact(num(fttf_snapshot.get("pledges_fetched"))), "organizations fetched", "good")}
          {stat_card("Pledged hours", compact(num(fttf_snapshot.get("pledged_hours_per_week"))), "hours per week", "good")}
          {stat_card("Listed profiles", compact(num(fttf_snapshot.get("listed_contributor_profiles"))), "unique contributor profiles", "good")}
          {stat_card("Pages fetched", compact(num(fttf_snapshot.get("pledge_pages_fetched"))), "pledge directory pages", "soft")}
        </div>
      </div>
      <div class="card">
        <h3>Largest current pledges</h3>
        <p>Top listed organizations by pledged hours per week.</p>
        {''.join(horizontal_count_metric(str(row.get("name", "")), float(row.get("hours_per_week") or 0), max_fttf_hours, COLORS["community"], "h/wk") for row in top_fttf_pledges)}
      </div>
    </div>
  </section>

  <section id="load" class="section">
    <h2>Project Load</h2>
    <p class="callout">The workload picture is healthier than the reporter trend alone suggests: Core has been near or below net-zero since 2024, and Gutenberg had a clear cleanup quarter in 2026-Q2. The backlog is still large.</p>
    <div class="grid-2">
      {svg_line_chart("Core new and closed tickets by quarter", "Created and closed Trac tickets since 2004.", [
          {"label": "Created", "color": COLORS["core"], "points": point_series(core_q, "quarter", "created")},
          {"label": "Closed", "color": COLORS["green"], "points": point_series(core_q, "quarter", "closed")},
      ])}
      {svg_line_chart("Gutenberg new and closed issues by quarter", "Created and closed GitHub issues since the available inventory begins.", [
          {"label": "Created", "color": COLORS["core"], "points": point_series(gut_q, "quarter", "created")},
          {"label": "Closed", "color": COLORS["green"], "points": point_series(gut_q, "quarter", "closed")},
      ])}
    </div>
    {svg_line_chart("Open backlog by quarter", "Core and Gutenberg both carry large open backlogs; Gutenberg has started declining from its sampled peak.", [
        {"label": "Core open tickets", "color": COLORS["core"], "points": point_series(core_q, "quarter", "open_at_end")},
        {"label": "Gutenberg open issues", "color": COLORS["gutenberg"], "points": point_series(gut_q, "quarter", "open_at_end")},
    ])}
    <div class="grid-2">
      {svg_line_chart("Median days to close", "Final closure age by closure quarter. This uses status history for Core and closed_at for Gutenberg.", [
          {"label": "Core", "color": COLORS["core"], "points": core_close_age},
          {"label": "Gutenberg", "color": COLORS["gutenberg"], "points": gut_close_age},
      ])}
      <div class="card">
        <h3>Backlog and reopen readout</h3>
        <p>These are direct tracker-derived signals, not adoption signals.</p>
        {horizontal_metric("Core open stale share", core_stale_pct, 100, COLORS["orange"])}
        {horizontal_metric("Gutenberg open stale share", gut_stale_pct, 100, COLORS["orange"])}
        {horizontal_metric("Core tickets ever reopened", reopened_pct, 100, COLORS["red"])}
        <p class="stat-note">Gutenberg reopen rate needs GitHub timeline events, which are not in the current export.</p>
      </div>
    </div>
    {svg_line_chart("Large ticket categories by quarter", "Combined Core plus Gutenberg classified issue/ticket categories since 2021.", cat_series)}
  </section>

  <section id="market" class="section">
    <h2>Market Position</h2>
    <p class="callout">The market signal is: WordPress is still far ahead, but its share has flattened and recently declined while hosted builders gained small, distributed share. This does not measure newly created sites yet.</p>
    <div class="stats">
      {stat_card("W3Techs all-site share", pct(wp_usage_latest["value"]) if wp_usage_latest else "n/a", f"{wp_usage_latest['date'] if wp_usage_latest else 'not fetched'}", "soft")}
      {stat_card("W3Techs CMS share", pct(wp_cms_latest["value"]) if wp_cms_latest else "n/a", f"{wp_cms_latest['date'] if wp_cms_latest else 'not fetched'}", "soft")}
      {stat_card("HTTP Archive mobile CMS share", "64.3%", "WordPress in 2025 Web Almanac", "soft")}
      {stat_card("Top 10k CMS usage", "about 58%", "HTTP Archive 2025", "soft")}
    </div>
    <div class="grid-2">
      {svg_line_chart("Share of all websites", "W3Techs yearly usage trend. This includes sites with no known CMS.", market_usage_series, y_suffix="%")}
      {svg_line_chart("Share among CMS sites", "W3Techs yearly CMS market-share trend.", market_cms_series, y_suffix="%")}
    </div>
    <div class="stats">
      {stat_card("Plugin directory", compact(plugin_count), "current WordPress.org API result", "good")}
      {stat_card("Theme directory", compact(theme_count), "current WordPress.org API result", "good")}
      {stat_card("WordCamp records", compact(len(wordcamps)), "WordCamp Central records fetched", "good")}
      {stat_card("Five for the Future", compact(num(fttf_snapshot.get("pledges_fetched"))), "current pledges fetched", "good")}
    </div>
  </section>

  <section id="coverage" class="section">
    <h2>Source Coverage</h2>
    <p class="callout">The SQLite database stores imported source tables, fetched ecosystem/adoption records, file hashes, and explicit source gaps. Download: <a href="community_health.sqlite.gz">community_health.sqlite.gz</a>.</p>
    <div class="status-grid">
      {''.join(f'<div class="status {status}"><span class="pill">{html.escape(status)}</span><b>{html.escape(name)}</b><span>{html.escape(note)}</span></div>' for name, status, note in source_status_rows(fetched))}
    </div>
  </section>

  <section class="footer">
    <p>Generated {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from local Core/Gutenberg exports and public sources.</p>
    <p>Sources: <a href="{W3TECHS_USAGE_URL}">W3Techs usage trend</a>, <a href="{W3TECHS_MARKET_SHARE_URL}">W3Techs CMS market-share trend</a>, <a href="{HTTP_ARCHIVE_CMS_URL}">HTTP Archive Web Almanac CMS 2025</a>, <a href="https://api.wordpress.org/">WordPress.org APIs</a>, <a href="https://central.wordcamp.org/wp-json/wp/v2/wordcamps">WordCamp Central API</a>, <a href="{EVENTS_WORDPRESS_URL}">WordPress Events</a>, <a href="https://make.wordpress.org/core/wp-json/wp/v2/posts">Make/Core REST API</a>, <a href="{FTTF_PLEDGES_URL}">Five for the Future pledges</a>, <a href="{RELEASE_ARCHIVE_URL}">WordPress release archive</a>, and <a href="{CREDITS_API}">Core credits API</a>.</p>
  </section>
</main>
</body>
</html>
"""
    OUT.write_text(html_doc, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-network", action="store_true", help="Use only local exports and skip public source fetches.")
    args = parser.parse_args()

    ROOT.mkdir(parents=True, exist_ok=True)
    data = load_data()
    fetched = {}
    fetched["market_share"] = []
    fetched["market_share"].extend(parse_w3techs_history(W3TECHS_USAGE_URL, "all_sites_usage", args.skip_network))
    fetched["market_share"].extend(parse_w3techs_history(W3TECHS_MARKET_SHARE_URL, "cms_market_share", args.skip_network))
    fetched["directory_snapshots"] = fetch_wordpress_directory_snapshots(args.skip_network)
    fetched["wordcamps"] = fetch_wordcamps(args.skip_network)
    fetched["wp_event_snapshots"], fetched["wp_events"] = fetch_wordpress_events(args.skip_network)
    fetched["make_core_posts"] = fetch_make_core_posts(args.skip_network)
    fetched["fttf_snapshots"], fetched["fttf_pledges"], fetched["fttf_contributors"] = fetch_five_for_the_future_pledges(
        args.skip_network
    )
    fetched["core_releases"], fetched["core_release_credits"] = fetch_core_release_credits(args.skip_network)
    fetched["core_release_committers"], fetched["core_release_committer_counts"] = fetch_core_release_committers(
        fetched["core_releases"], args.skip_network
    )

    build_database(data, fetched)
    build_report(data, fetched)
    eprint(f"wrote {DB_PATH}")
    eprint(f"wrote {OUT}")


if __name__ == "__main__":
    main()
