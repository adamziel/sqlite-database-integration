#!/usr/bin/env python3
import argparse
import base64
import concurrent.futures
import csv
import datetime as dt
import email.utils
import hashlib
import html
import io
import json
import math
import os
import random
import re
import sqlite3
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_core_issue_analysis")
RAW = ROOT / "raw"
OUT = ROOT / "final_report.html"

START = dt.datetime(2003, 1, 1, 0, 0, 0, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 6, 11, 23, 59, 59, tzinfo=dt.timezone.utc)

TRAC = "https://core.trac.wordpress.org"
TRAC_COLS = [
    "id",
    "summary",
    "reporter",
    "owner",
    "type",
    "status",
    "priority",
    "milestone",
    "component",
    "version",
    "severity",
    "resolution",
    "keywords",
    "cc",
    "time",
    "changetime",
]

TRAC_TICKETS = RAW / "trac_tickets.csv"
TRAC_OPEN = RAW / "trac_open_tickets.csv"
TRAC_CLOSED = RAW / "trac_closed_tickets.csv"
TRAC_EVENTS = RAW / "trac_ticket_events.csv"
TRAC_FETCHED = RAW / "trac_rss_fetched.csv"
GITHUB_PRS = RAW / "github_wordpress_develop_prs.jsonl"

QUARTERLY = ROOT / "quarterly_metrics.csv"
MONTHLY = ROOT / "monthly_metrics.csv"
COMPONENTS = ROOT / "component_summary.csv"
RESOLUTIONS = ROOT / "resolution_summary.csv"
GITHUB_QUARTERLY = ROOT / "github_pr_quarterly.csv"
SUMMARY = ROOT / "analysis_summary.json"
CLASSIFICATION_DB = Path("/Users/admin/wordpress_ticket_classification/wordpress_tickets.sqlite")

VIEW_SPECS = [
    {"slug": "all", "label": "All tickets", "category": None, "noun": "Core tickets", "chart": "Core Trac tickets"},
    {"slug": "bugs", "label": "Bugs", "category": "bug", "noun": "Core bugs", "chart": "Core Trac bugs"},
    {
        "slug": "feature_requests",
        "label": "Feature requests",
        "category": "feature_request",
        "noun": "Core feature requests",
        "chart": "Core Trac feature requests",
    },
]

UA = "codex-wordpress-core-analysis/1.0"
OPEN_STATUSES = {"new", "assigned", "accepted", "reopened", "reviewing"}

LINE_COLORS = {
    "open": "#0f766e",
    "created": "#2563eb",
    "closed": "#dc2626",
    "reporters": "#7c3aed",
    "first": "#ea580c",
    "prs": "#0891b2",
    "pr_closed": "#be123c",
}


def ensure_dirs():
    RAW.mkdir(parents=True, exist_ok=True)


def eprint(message):
    print(message, file=sys.stderr, flush=True)


def parse_trac_dt(value):
    value = (value or "").strip()
    if not value:
        return None
    parsed = dt.datetime.strptime(value, "%m/%d/%Y %I:%M:%S %p")
    return parsed.replace(tzinfo=dt.timezone.utc)


def parse_iso_dt(value):
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_rss_dt(value):
    if not value:
        return None
    parsed = email.utils.parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def iso(value):
    if not value:
        return ""
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def date_label(value):
    if isinstance(value, str):
        value = parse_iso_dt(value)
    return value.date().isoformat()


def quarter_start(value):
    if isinstance(value, str):
        value = parse_iso_dt(value)
    month = ((value.month - 1) // 3) * 3 + 1
    return dt.datetime(value.year, month, 1, tzinfo=dt.timezone.utc)


def add_months(value, months):
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    return dt.datetime(year, month, 1, tzinfo=dt.timezone.utc)


def quarter_label(value):
    return f"{value.year}-Q{((value.month - 1) // 3) + 1}"


def month_start(value):
    return dt.datetime(value.year, value.month, 1, tzinfo=dt.timezone.utc)


def esc(value):
    return html.escape(str(value))


def fmt_int(value):
    return f"{int(round(value)):,}"


def pct(value, total):
    return 100 * value / total if total else 0


def scale(value, old_min, old_max, new_min, new_max):
    if old_max == old_min:
        return (new_min + new_max) / 2
    return new_min + (value - old_min) * (new_max - new_min) / (old_max - old_min)


def axis_ticks(min_value, max_value, steps=4):
    if max_value <= min_value:
        return [min_value]
    span = max_value - min_value
    raw = span / steps
    magnitude = 10 ** math.floor(math.log10(max(raw, 1)))
    candidates = [1, 2, 5, 10]
    step = min((c * magnitude for c in candidates), key=lambda x: abs(x - raw))
    start = math.floor(min_value / step) * step
    end = math.ceil(max_value / step) * step
    ticks = []
    current = start
    while current <= end + 0.0001:
        ticks.append(int(current))
        current += step
    return ticks


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TracClient:
    def __init__(self):
        self.jar = urllib.request.HTTPCookieProcessor()
        self.cookiejar = self.jar.cookiejar
        self.opener = urllib.request.build_opener(self.jar)
        self.lock = threading.Lock()

    def request(self, url, accept="text/csv,text/html;q=0.9,*/*;q=0.8", timeout=180):
        headers = {"User-Agent": UA, "Accept": accept}
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers=headers)
                with self.opener.open(req, timeout=timeout) as resp:
                    return resp.read()
            except urllib.error.HTTPError as exc:
                body = exc.read(500)
                if exc.code == 403 and (b"Checking your browser" in body or self._hcc_cookie()):
                    self.solve_challenge(url)
                    continue
                raise
        raise RuntimeError(f"Could not fetch {url}")

    def solve_challenge(self, trigger_url, force=False):
        with self.lock:
            if force:
                self._clear_cookie("_hcp")
                self._clear_cookie("_hcc")
            if self._hcp_cookie():
                return
            headers = {"User-Agent": UA, "Accept": "text/html,*/*"}
            if not self._hcc_cookie():
                try:
                    self.opener.open(urllib.request.Request(trigger_url, headers=headers), timeout=60).read()
                except urllib.error.HTTPError as exc:
                    exc.read(500)
                    if exc.code != 403:
                        raise
            hcc = self._hcc_cookie()
            if not hcc:
                raise RuntimeError("Core Trac challenge did not set _hcc cookie.")
            payload = base64.b64decode(hcc.split(":", 1)[1]).decode("utf-8")
            solution = None
            for nonce in range(30_000_000):
                candidate = payload + str(nonce)
                if hashlib.sha256(candidate.encode("utf-8")).hexdigest().startswith("0000"):
                    solution = candidate
                    break
            if solution is None:
                raise RuntimeError("Could not solve Core Trac challenge.")
            time.sleep(4.05)
            post_headers = {
                "User-Agent": UA,
                "Accept": "*/*",
                "X-Hashcash-Solution": base64.b64encode(solution.encode("utf-8")).decode("ascii"),
                "X-Interactive": "",
            }
            req = urllib.request.Request(
                f"{TRAC}/__challenge",
                data=b"",
                headers=post_headers,
                method="POST",
            )
            with self.opener.open(req, timeout=60) as resp:
                resp.read()
            if not self._hcp_cookie():
                raise RuntimeError("Core Trac challenge succeeded but no _hcp cookie was set.")

    def _hcc_cookie(self):
        for cookie in self.cookiejar:
            if cookie.name == "_hcc":
                return cookie.value
        return None

    def _hcp_cookie(self):
        now = time.time()
        for cookie in self.cookiejar:
            if cookie.name == "_hcp" and (cookie.expires is None or cookie.expires > now + 30):
                return cookie.value
        return None

    def _clear_cookie(self, name):
        for cookie in list(self.cookiejar):
            if cookie.name == name:
                try:
                    self.cookiejar.clear(cookie.domain, cookie.path, cookie.name)
                except KeyError:
                    pass

    def cookie_header(self):
        if not self._hcp_cookie():
            self.solve_challenge(f"{TRAC}/")
        parts = []
        for cookie in self.cookiejar:
            if cookie.name in {"_hcp", "_hcc"}:
                parts.append(f"{cookie.name}={cookie.value}")
        return "; ".join(parts)


def trac_query_url(status_filter):
    params = []
    if isinstance(status_filter, str):
        params.append(("status", status_filter))
    else:
        for status in status_filter:
            params.append(("status", status))
    params.extend([("max", "0"), ("format", "csv")])
    for col in TRAC_COLS:
        params.append(("col", col))
    return f"{TRAC}/query?{urllib.parse.urlencode(params)}"


def normalize_trac_row(row):
    return {
        "id": row.get("id") or row.get("\ufeffid") or "",
        "summary": row.get("Summary") or row.get("summary") or "",
        "reporter": row.get("Reporter") or row.get("reporter") or "",
        "owner": row.get("Owner") or row.get("owner") or "",
        "type": row.get("Type") or row.get("type") or "",
        "status": row.get("Status") or row.get("status") or "",
        "priority": row.get("Priority") or row.get("priority") or "",
        "milestone": row.get("Milestone") or row.get("milestone") or "",
        "component": row.get("Component") or row.get("component") or "",
        "version": row.get("Version") or row.get("version") or "",
        "severity": row.get("Severity") or row.get("severity") or "",
        "resolution": row.get("Resolution") or row.get("resolution") or "",
        "keywords": row.get("Keywords") or row.get("keywords") or "",
        "cc": row.get("Cc") or row.get("cc") or "",
        "created_at": iso(parse_trac_dt(row.get("Created") or row.get("time") or "")),
        "modified_at": iso(parse_trac_dt(row.get("Modified") or row.get("changetime") or "")),
    }


def fetch_trac_inventory(force=False):
    ensure_dirs()
    if TRAC_TICKETS.exists() and not force:
        eprint(f"using cached {TRAC_TICKETS}")
        return
    client = TracClient()
    outputs = [
        (TRAC_OPEN, trac_query_url("!closed")),
        (TRAC_CLOSED, trac_query_url("closed")),
    ]
    rows_by_id = {}
    for path, url in outputs:
        eprint(f"fetching {url}")
        data = client.request(url)
        path.write_bytes(data)
        text = data.decode("utf-8-sig", errors="replace")
        count = 0
        for row in csv.DictReader(io.StringIO(text)):
            normalized = normalize_trac_row(row)
            if normalized["id"]:
                rows_by_id[normalized["id"]] = normalized
                count += 1
        eprint(f"fetched {count:,} rows to {path}")
    rows = [rows_by_id[key] for key in sorted(rows_by_id, key=lambda x: int(x))]
    write_csv(
        TRAC_TICKETS,
        rows,
        [
            "id",
            "summary",
            "reporter",
            "owner",
            "type",
            "status",
            "priority",
            "milestone",
            "component",
            "version",
            "severity",
            "resolution",
            "keywords",
            "cc",
            "created_at",
            "modified_at",
        ],
    )
    eprint(f"wrote {len(rows):,} normalized tickets to {TRAC_TICKETS}")


def strip_html(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def parse_rss_events(ticket_id, data):
    events = []
    root = ET.fromstring(data)
    ns = {"dc": "http://purl.org/dc/elements/1.1/"}
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        date = parse_rss_dt(item.findtext("pubDate") or "")
        creator = item.findtext("dc:creator", default="", namespaces=ns) or ""
        description = strip_html(item.findtext("description") or "")
        haystack = f"{title} {description}".lower()
        event_type = None
        from_status = ""
        to_status = ""
        close_match = re.search(r"status changed from ([a-z]+) to closed", haystack)
        reopen_match = re.search(r"status changed from closed to ([a-z]+)", haystack)
        if close_match:
            event_type = "closed"
            from_status = close_match.group(1)
            to_status = "closed"
        elif reopen_match:
            event_type = "reopened"
            from_status = "closed"
            to_status = reopen_match.group(1)
        if event_type and date:
            events.append(
                {
                    "ticket_id": str(ticket_id),
                    "event_type": event_type,
                    "event_at": iso(date),
                    "from_status": from_status,
                    "to_status": to_status,
                    "title": title,
                    "creator": creator,
                }
            )
    return events, len(root.findall("./channel/item"))


def rss_url(ticket_id):
    return f"{TRAC}/ticket/{ticket_id}?format=rss"


def fetch_rss_with_session(ticket_id, session):
    headers = {
        "User-Agent": UA,
        "Accept": "application/rss+xml,text/xml,*/*",
    }
    for attempt in range(6):
        headers["Cookie"] = session.cookie_header()
        req = urllib.request.Request(rss_url(ticket_id), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            events, item_count = parse_rss_events(ticket_id, data)
            return ticket_id, events, item_count, ""
        except urllib.error.HTTPError as exc:
            exc.read(500)
            if exc.code == 403 and attempt < 5:
                session.solve_challenge(rss_url(ticket_id), force=True)
                time.sleep(1 + random.random())
                continue
            if exc.code == 429 and attempt < 5:
                retry_after = exc.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    sleep_for = int(retry_after)
                else:
                    sleep_for = min(45, 4 * (attempt + 1))
                time.sleep(sleep_for + random.random())
                continue
            raise

def load_fetched_ids():
    if not TRAC_FETCHED.exists():
        return set()
    fetched = set()
    with TRAC_FETCHED.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("ok") == "1":
                fetched.add(row["ticket_id"])
    return fetched


def fetch_trac_events(force=False, workers=10, limit=None):
    tickets = read_csv(TRAC_TICKETS)
    if force:
        for path in [TRAC_EVENTS, TRAC_FETCHED]:
            if path.exists():
                path.unlink()
    existing = load_fetched_ids()
    candidates = []
    for ticket in tickets:
        modified = parse_iso_dt(ticket["modified_at"])
        status = ticket["status"].lower()
        if status == "closed" and modified and modified >= START:
            candidates.append(ticket["id"])
        elif status == "reopened":
            candidates.append(ticket["id"])
    candidates = sorted(set(candidates), key=lambda x: int(x))
    if limit:
        candidates = candidates[:limit]
    pending = [ticket_id for ticket_id in candidates if ticket_id not in existing]
    if not pending:
        eprint(f"using cached RSS events for {len(existing):,} tickets")
        return

    client = TracClient()
    client.request(f"{TRAC}/ticket/{pending[0]}?format=rss", accept="application/rss+xml,text/xml,*/*")
    cookie_header = client.cookie_header()
    if not cookie_header:
        raise RuntimeError("No Core Trac session cookie available for RSS fetches.")

    event_exists = TRAC_EVENTS.exists()
    fetched_exists = TRAC_FETCHED.exists()
    event_fields = ["ticket_id", "event_type", "event_at", "from_status", "to_status", "title", "creator"]
    fetched_fields = ["ticket_id", "ok", "item_count", "event_count", "error"]

    with TRAC_EVENTS.open("a", newline="", encoding="utf-8") as events_file, TRAC_FETCHED.open(
        "a", newline="", encoding="utf-8"
    ) as fetched_file:
        event_writer = csv.DictWriter(events_file, fieldnames=event_fields)
        fetched_writer = csv.DictWriter(fetched_file, fieldnames=fetched_fields)
        if not event_exists:
            event_writer.writeheader()
        if not fetched_exists:
            fetched_writer.writeheader()

        completed = 0
        errors = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(fetch_rss_with_session, ticket_id, client): ticket_id for ticket_id in pending}
            for future in concurrent.futures.as_completed(futures):
                ticket_id = futures[future]
                try:
                    _ticket_id, events, item_count, error = future.result()
                    for event in events:
                        event_writer.writerow(event)
                    fetched_writer.writerow(
                        {
                            "ticket_id": ticket_id,
                            "ok": "1",
                            "item_count": item_count,
                            "event_count": len(events),
                            "error": error,
                        }
                    )
                except Exception as exc:
                    errors += 1
                    fetched_writer.writerow(
                        {
                            "ticket_id": ticket_id,
                            "ok": "0",
                            "item_count": 0,
                            "event_count": 0,
                            "error": repr(exc)[:500],
                        }
                    )
                completed += 1
                if completed % 250 == 0 or completed == len(pending):
                    events_file.flush()
                    fetched_file.flush()
                    eprint(f"RSS events {completed:,}/{len(pending):,}; errors {errors:,}")


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
    token = None
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            token = line.split("=", 1)[1]
    return token


class GitHubClient:
    def __init__(self):
        self.token = credential_from_git()

    def request_with_headers(self, url):
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": UA,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        while True:
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.load(resp)
                    remaining = int(resp.headers.get("X-RateLimit-Remaining", "1"))
                    reset = int(resp.headers.get("X-RateLimit-Reset", "0") or 0)
                    if remaining <= 10:
                        sleep_for = max(5, reset - int(time.time()) + 5)
                        eprint(f"GitHub rate-limit pause {sleep_for}s")
                        time.sleep(sleep_for)
                    return data, dict(resp.headers.items())
            except urllib.error.HTTPError as exc:
                if exc.code in (403, 429):
                    reset = int(exc.headers.get("X-RateLimit-Reset", "0") or 0)
                    sleep_for = max(30, reset - int(time.time()) + 5)
                    eprint(f"GitHub throttle pause {sleep_for}s")
                    time.sleep(sleep_for)
                    continue
                body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"GitHub HTTP {exc.code}: {body}") from exc


def next_link(headers):
    link = headers.get("Link") or headers.get("link") or ""
    for part in link.split(","):
        part = part.strip()
        if 'rel="next"' in part and part.startswith("<") and ">" in part:
            return part[1 : part.index(">")]
    return None


TRAC_ID_PATTERNS = [
    re.compile(r"core[-\s:#]*(\d{4,6})", re.I),
    re.compile(r"core\.trac\.wordpress\.org/ticket/(\d{4,6})", re.I),
    re.compile(r"\btrac ticket:?\s*(?:#|core-)?(\d{4,6})", re.I),
]


def linked_trac_ids(text):
    ids = set()
    for pattern in TRAC_ID_PATTERNS:
        for match in pattern.findall(text or ""):
            ids.add(str(int(match)))
    return sorted(ids, key=lambda x: int(x))


def normalize_pr(item):
    user = item.get("user") or {}
    pull = item.get("pull_request") or {}
    body = item.get("body") or ""
    text = "\n".join([item.get("title") or "", body, pull.get("html_url") or ""])
    return {
        "number": item["number"],
        "html_url": item["html_url"],
        "title": item.get("title") or "",
        "state": item.get("state") or "",
        "created_at": item.get("created_at") or "",
        "updated_at": item.get("updated_at") or "",
        "closed_at": item.get("closed_at") or "",
        "author_login": user.get("login") or "",
        "author_type": user.get("type") or "",
        "author_association": item.get("author_association") or "",
        "draft": bool(item.get("draft")),
        "comments": item.get("comments") or 0,
        "trac_ticket_ids": linked_trac_ids(text),
    }


def fetch_github_prs(force=False):
    if GITHUB_PRS.exists() and not force:
        eprint(f"using cached {GITHUB_PRS}")
        return
    client = GitHubClient()
    tmp = GITHUB_PRS.with_suffix(".jsonl.tmp")
    url = "https://api.github.com/repos/WordPress/wordpress-develop/issues?" + urllib.parse.urlencode(
        {
            "state": "all",
            "sort": "created",
            "direction": "asc",
            "per_page": "100",
        }
    )
    count = 0
    page = 1
    with tmp.open("w", encoding="utf-8") as out:
        while url:
            items, headers = client.request_with_headers(url)
            stop = False
            for item in items:
                if "pull_request" not in item:
                    continue
                created = parse_iso_dt(item["created_at"])
                if created and created > END:
                    stop = True
                    continue
                out.write(json.dumps(normalize_pr(item), sort_keys=True) + "\n")
                count += 1
            if page % 25 == 0:
                eprint(f"fetched GitHub PR page {page}; PRs {count:,}")
            if stop:
                break
            url = next_link(headers)
            page += 1
    tmp.replace(GITHUB_PRS)
    eprint(f"wrote {count:,} GitHub PRs to {GITHUB_PRS}")


def load_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_events():
    events = defaultdict(list)
    if not TRAC_EVENTS.exists():
        return events
    for row in read_csv(TRAC_EVENTS):
        if row.get("event_at"):
            events[row["ticket_id"]].append(row)
    for rows in events.values():
        rows.sort(key=lambda r: parse_iso_dt(r["event_at"]))
    return events


def category_from_trac_type(ticket):
    ticket_type = (ticket.get("type") or "").lower()
    if "defect" in ticket_type or "bug" in ticket_type:
        return "bug"
    if "feature" in ticket_type:
        return "feature_request"
    if "enhancement" in ticket_type:
        return "enhancement"
    if "task" in ticket_type:
        return "task_maintenance"
    return "other"


def load_core_category_map(tickets):
    categories = {ticket["id"]: category_from_trac_type(ticket) for ticket in tickets}
    if not CLASSIFICATION_DB.exists():
        return categories
    try:
        conn = sqlite3.connect(CLASSIFICATION_DB)
        rows = conn.execute(
            """
            SELECT ticket_id, primary_category
            FROM ticket_classifications
            WHERE source='core'
            """
        ).fetchall()
        conn.close()
    except sqlite3.Error as exc:
        eprint(f"could not read {CLASSIFICATION_DB}: {exc}; falling back to Trac type")
        return categories
    for ticket_id, category in rows:
        categories[str(ticket_id)] = category
    return categories


def selected_for_view(tickets, category_map, category):
    if category is None:
        return list(tickets)
    return [ticket for ticket in tickets if category_map.get(ticket["id"]) == category]


def event_close_dates(events_by_ticket, ticket, created, modified):
    rows = events_by_ticket.get(ticket["id"], [])
    close_dates = [parse_iso_dt(r["event_at"]) for r in rows if r["event_type"] == "closed"]
    reopen_dates = [parse_iso_dt(r["event_at"]) for r in rows if r["event_type"] == "reopened"]
    if ticket["status"].lower() == "closed":
        if close_dates:
            return max(close_dates), "rss"
        return modified, "modified_fallback"
    return None, "open"


def open_intervals_for_ticket(ticket, events_by_ticket):
    created = parse_iso_dt(ticket["created_at"])
    modified = parse_iso_dt(ticket["modified_at"])
    if not created:
        return []
    events = events_by_ticket.get(ticket["id"], [])
    intervals = []
    open_start = created
    state = "open"
    if events:
        for event in events:
            event_at = parse_iso_dt(event["event_at"])
            if not event_at:
                continue
            if event["event_type"] == "closed":
                if state == "open" and event_at >= open_start:
                    intervals.append((open_start, event_at))
                state = "closed"
            elif event["event_type"] == "reopened":
                if state == "closed":
                    open_start = event_at
                state = "open"
        if ticket["status"].lower() == "closed":
            if state == "open":
                close_at = modified or END
                if close_at >= open_start:
                    intervals.append((open_start, close_at))
        else:
            if state == "open":
                intervals.append((open_start, None))
            else:
                intervals.append((modified or created, None))
        return intervals
    if ticket["status"].lower() == "closed":
        close_at = modified or created
        if close_at >= created:
            return [(created, close_at)]
        return []
    return [(created, None)]


def is_open_at(intervals, point):
    for start, end in intervals:
        if start <= point and (end is None or end > point):
            return True
    return False


def in_range(value, start, end):
    return value and start <= value < end


def make_periods():
    quarters = []
    current = quarter_start(START)
    end_q = quarter_start(END)
    while current <= end_q:
        quarters.append(current)
        current = add_months(current, 3)
    months = []
    current = month_start(START)
    end_m = month_start(END)
    while current <= end_m:
        months.append(current)
        current = add_months(current, 1)
    return quarters, months


def pr_matches_tickets(pr, selected_ids):
    if selected_ids is None:
        return True
    return any(str(ticket_id) in selected_ids for ticket_id in (pr.get("trac_ticket_ids") or []))


def build_pr_quarter_rows(prs, quarters, selected_ids=None):
    view_prs = [pr for pr in prs if pr_matches_tickets(pr, selected_ids)]
    pr_quarter_rows = []
    first_pr_author = {}
    for pr in sorted(view_prs, key=lambda p: parse_iso_dt(p["created_at"]) or dt.datetime.max.replace(tzinfo=dt.timezone.utc)):
        author = (pr.get("author_login") or "").lower()
        created = parse_iso_dt(pr.get("created_at"))
        if author and created and author not in first_pr_author:
            first_pr_author[author] = created
    for q in quarters:
        q_next = add_months(q, 3)
        effective_start = max(q, START)
        effective_end = min(q_next, END + dt.timedelta(seconds=1))
        created_prs = [p for p in view_prs if in_range(parse_iso_dt(p.get("created_at")), effective_start, effective_end)]
        closed_prs = [p for p in view_prs if in_range(parse_iso_dt(p.get("closed_at")), effective_start, effective_end)]
        linked_prs = [p for p in created_prs if p.get("trac_ticket_ids")]
        authors = {(p.get("author_login") or "").lower() for p in created_prs if p.get("author_login")}
        first_authors = {
            a for a in authors if first_pr_author.get(a) and in_range(first_pr_author[a], effective_start, effective_end)
        }
        pr_quarter_rows.append(
            {
                "quarter": q.date().isoformat(),
                "label": quarter_label(q),
                "created": len(created_prs),
                "closed": len(closed_prs),
                "linked_to_trac": len(linked_prs),
                "unique_authors": len(authors),
                "first_time_authors": len(first_authors),
            }
        )
    return pr_quarter_rows, view_prs


def view_path(base_path, slug):
    if slug == "all":
        return base_path
    return base_path.with_name(f"{base_path.stem}_{slug}{base_path.suffix}")


def analyze_ticket_view(spec, tickets, events_by_ticket, prs, quarters, months, intervals_by_ticket, close_info, close_sources):
    selected_tickets = selected_for_view(tickets, spec["category_map"], spec["category"])
    selected_ids = {ticket["id"] for ticket in selected_tickets}

    first_reporter_seen = {}
    for ticket in sorted(selected_tickets, key=lambda t: parse_iso_dt(t["created_at"]) or dt.datetime.max.replace(tzinfo=dt.timezone.utc)):
        reporter = (ticket["reporter"] or "").strip().lower()
        created = parse_iso_dt(ticket["created_at"])
        if reporter and created and reporter not in first_reporter_seen:
            first_reporter_seen[reporter] = created

    quarterly_rows = []
    for q in quarters:
        q_next = add_months(q, 3)
        effective_start = max(q, START)
        effective_end = min(q_next, END + dt.timedelta(seconds=1))
        point = min(q_next - dt.timedelta(seconds=1), END)
        created_tickets = [t for t in selected_tickets if in_range(parse_iso_dt(t["created_at"]), effective_start, effective_end)]
        closed_tickets = [
            t for t in selected_tickets
            if t["status"].lower() == "closed" and in_range(close_info.get(t["id"]), effective_start, effective_end)
        ]
        reporters = {(t["reporter"] or "").strip().lower() for t in created_tickets if t.get("reporter")}
        first_time = {
            r
            for r in reporters
            if first_reporter_seen.get(r) and in_range(first_reporter_seen[r], effective_start, effective_end)
        }
        open_count = sum(1 for ticket_id in selected_ids if is_open_at(intervals_by_ticket[ticket_id], point))
        defect_created = sum(1 for t in created_tickets if "defect" in t["type"].lower())
        enhancement_created = sum(1 for t in created_tickets if "enhancement" in t["type"].lower())
        feature_created = sum(1 for t in created_tickets if "feature" in t["type"].lower())
        task_created = sum(1 for t in created_tickets if "task" in t["type"].lower())
        quarterly_rows.append(
            {
                "quarter": q.date().isoformat(),
                "label": quarter_label(q),
                "created": len(created_tickets),
                "closed": len(closed_tickets),
                "net": len(created_tickets) - len(closed_tickets),
                "open_at_end": open_count,
                "unique_reporters": len(reporters),
                "first_time_reporters": len(first_time),
                "defect_created": defect_created,
                "enhancement_created": enhancement_created,
                "feature_created": feature_created,
                "task_created": task_created,
            }
        )

    monthly_rows = []
    for m in months:
        m_next = add_months(m, 1)
        effective_start = max(m, START)
        effective_end = min(m_next, END + dt.timedelta(seconds=1))
        created = sum(1 for t in selected_tickets if in_range(parse_iso_dt(t["created_at"]), effective_start, effective_end))
        closed = sum(
            1
            for t in selected_tickets
            if t["status"].lower() == "closed" and in_range(close_info.get(t["id"]), effective_start, effective_end)
        )
        monthly_rows.append({"month": m.date().isoformat(), "created": created, "closed": closed, "net": created - closed})

    current_open = [t for t in selected_tickets if t["status"].lower() != "closed"]
    window_created = [
        t for t in selected_tickets
        if START <= (parse_iso_dt(t["created_at"]) or START - dt.timedelta(days=1)) <= END
    ]
    window_closed = [
        t
        for t in selected_tickets
        if t["status"].lower() == "closed" and close_info.get(t["id"]) and START <= close_info[t["id"]] <= END
    ]

    component_rows = []
    open_components = Counter(t["component"] or "Unknown" for t in current_open)
    created_components = Counter(t["component"] or "Unknown" for t in window_created)
    for component, count in open_components.most_common(12):
        component_rows.append({"component": component, "current_open": count, "created_in_window": created_components.get(component, 0)})

    resolution_counts = Counter(t["resolution"] or "none" for t in window_closed)
    resolution_rows = [
        {"resolution": resolution, "closed_in_window": count}
        for resolution, count in resolution_counts.most_common(12)
    ]

    pr_selected_ids = None if spec["slug"] == "all" else selected_ids
    pr_quarter_rows, view_prs = build_pr_quarter_rows(prs, quarters, selected_ids=pr_selected_ids)
    github_window_created = sum(
        1 for p in view_prs if START <= (parse_iso_dt(p.get("created_at")) or START - dt.timedelta(days=1)) <= END
    )
    github_window_linked = sum(
        1
        for p in view_prs
        if p.get("trac_ticket_ids") and START <= (parse_iso_dt(p.get("created_at")) or START - dt.timedelta(days=1)) <= END
    )

    filtered_close_sources = Counter()
    for ticket in selected_tickets:
        filtered_close_sources[close_sources.get(ticket["id"], "open")] += 1

    summary = {
        "slug": spec["slug"],
        "view_label": spec["label"],
        "view_noun": spec["noun"],
        "chart_label": spec["chart"],
        "generated_at": iso(dt.datetime.now(dt.timezone.utc)),
        "start": iso(START),
        "end": iso(END),
        "ticket_count": len(selected_tickets),
        "current_open": len(current_open),
        "current_closed": len(selected_tickets) - len(current_open),
        "window_created": len(window_created),
        "window_closed": len(window_closed),
        "close_sources": dict(filtered_close_sources),
        "rss_event_tickets": sum(1 for ticket_id in selected_ids if events_by_ticket.get(ticket_id)),
        "github_pr_count": len(view_prs),
        "github_window_created": github_window_created,
        "github_window_linked": github_window_linked,
    }

    write_csv(view_path(QUARTERLY, spec["slug"]), quarterly_rows, list(quarterly_rows[0].keys()))
    write_csv(view_path(MONTHLY, spec["slug"]), monthly_rows, list(monthly_rows[0].keys()))
    write_csv(view_path(COMPONENTS, spec["slug"]), component_rows, ["component", "current_open", "created_in_window"])
    write_csv(view_path(RESOLUTIONS, spec["slug"]), resolution_rows, ["resolution", "closed_in_window"])
    write_csv(view_path(GITHUB_QUARTERLY, spec["slug"]), pr_quarter_rows, list(pr_quarter_rows[0].keys()))

    return {
        "quarterly": quarterly_rows,
        "monthly": monthly_rows,
        "components": component_rows,
        "resolutions": resolution_rows,
        "github_quarterly": pr_quarter_rows,
        "summary": summary,
    }


def analyze():
    tickets = read_csv(TRAC_TICKETS)
    events_by_ticket = load_events()
    prs = load_jsonl(GITHUB_PRS)
    category_map = load_core_category_map(tickets)

    intervals_by_ticket = {
        ticket["id"]: open_intervals_for_ticket(ticket, events_by_ticket)
        for ticket in tickets
    }
    close_info = {}
    close_sources = {}
    for ticket in tickets:
        close_at, source = event_close_dates(
            events_by_ticket,
            ticket,
            parse_iso_dt(ticket["created_at"]),
            parse_iso_dt(ticket["modified_at"]),
        )
        close_info[ticket["id"]] = close_at
        close_sources[ticket["id"]] = source

    quarters, months = make_periods()
    views = {}
    for raw_spec in VIEW_SPECS:
        spec = dict(raw_spec)
        spec["category_map"] = category_map
        views[spec["slug"]] = analyze_ticket_view(
            spec, tickets, events_by_ticket, prs, quarters, months, intervals_by_ticket, close_info, close_sources
        )

    summary = {
        "generated_at": iso(dt.datetime.now(dt.timezone.utc)),
        "start": iso(START),
        "end": iso(END),
        "classification_db": str(CLASSIFICATION_DB),
        "views": {slug: view["summary"] for slug, view in views.items()},
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return {"views": views, "view_order": [spec["slug"] for spec in VIEW_SPECS], "summary": summary}


def numeric(row, key):
    return int(row[key])


def line_chart_svg(rows, series, title, note, aria, height=365, x_key="quarter"):
    width = 1120
    left, right, top, bottom = 76, 34, 88, 58
    plot_w = width - left - right
    plot_h = height - top - bottom
    all_values = [numeric(row, key) for row in rows for key, _label, _color in series]
    min_v = min(0, min(all_values))
    max_v = max(all_values)
    if max_v > 1000:
        max_v = int(math.ceil(max_v / 500) * 500)
    else:
        max_v = int(math.ceil(max_v / 100) * 100)

    def x_for(idx):
        if len(rows) == 1:
            return left + plot_w / 2
        return left + idx * plot_w / (len(rows) - 1)

    def y_for(value):
        return scale(value, min_v, max_v, top + plot_h, top)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(aria)}">',
        f'<text x="{left}" y="24" class="chart-title">{esc(title)}</text>',
        f'<text x="{left}" y="46" class="chart-note">{esc(note)}</text>',
    ]
    legend_x = left
    for _key, label, color in series:
        parts.append(f'<rect x="{legend_x}" y="60" width="12" height="12" rx="2" fill="{color}"/>')
        parts.append(f'<text x="{legend_x + 18}" y="71" class="legend-text">{esc(label)}</text>')
        legend_x += max(96, len(label) * 7 + 42)
    for tick in axis_ticks(min_v, max_v, 4):
        y = y_for(tick)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" class="axis">{tick:,}</text>')
    for key, label, color in series:
        points = " ".join(
            f'{x_for(idx):.1f},{y_for(numeric(row, key)):.1f}'
            for idx, row in enumerate(rows)
        )
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="4" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )
        for idx, row in enumerate(rows):
            x = x_for(idx)
            y = y_for(numeric(row, key))
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}">'
                f'<title>{esc(row.get("label", row.get(x_key, "")))} {esc(label)}: {numeric(row, key):,}</title></circle>'
            )
    for idx, row in enumerate(rows):
        if x_key == "quarter":
            show_label = idx == 0 or row["quarter"][5:10] == "01-01"
            label_text = row["quarter"][:4]
        else:
            show_label = idx == 0 or idx == len(rows) - 1 or idx % 2 == 0
            label_text = row.get("label", row.get(x_key, ""))
        if show_label:
            x = x_for(idx)
            parts.append(f'<text x="{x:.1f}" y="{height - 24}" text-anchor="middle" class="axis">{esc(label_text)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def annual_sum_rows(rows, keys, date_key="quarter"):
    buckets = defaultdict(lambda: {key: 0 for key in keys})
    for row in rows:
        year = row[date_key][:4]
        buckets[year]["label"] = year
        for key in keys:
            buckets[year][key] += numeric(row, key)
    return [dict({"year": year}, **buckets[year]) for year in sorted(buckets)]


def annual_reporter_rows(rows):
    by_year = defaultdict(list)
    for row in rows:
        by_year[row["quarter"][:4]].append(row)
    annual = []
    for year in sorted(by_year):
        q_rows = by_year[year]
        annual.append(
            {
                "year": year,
                "label": year,
                "unique_reporters": round(statistics.mean(numeric(row, "unique_reporters") for row in q_rows)),
                "first_time_reporters": sum(numeric(row, "first_time_reporters") for row in q_rows),
            }
        )
    return annual


def grouped_bars_svg(rows, series, title, note, aria, height=365):
    width = 1120
    left, right, top, bottom = 76, 34, 92, 58
    plot_w = width - left - right
    plot_h = height - top - bottom
    all_values = [numeric(row, key) for row in rows for key, _label, _color in series]
    max_v = max(all_values) if all_values else 1
    if max_v > 1000:
        max_v = int(math.ceil(max_v / 500) * 500)
    elif max_v > 100:
        max_v = int(math.ceil(max_v / 100) * 100)
    else:
        max_v = max(10, int(math.ceil(max_v / 10) * 10))
    group_w = plot_w / max(len(rows), 1)
    bar_gap = 2
    bar_w = min(14, max(3, (group_w - 8) / max(len(series), 1) - bar_gap))
    series_w = len(series) * bar_w + (len(series) - 1) * bar_gap

    def y_for(value):
        return scale(value, 0, max_v, top + plot_h, top)

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(aria)}">',
        f'<text x="{left}" y="24" class="chart-title">{esc(title)}</text>',
        f'<text x="{left}" y="46" class="chart-note">{esc(note)}</text>',
    ]
    legend_x = left
    for _key, label, color in series:
        parts.append(f'<rect x="{legend_x}" y="62" width="12" height="12" rx="2" fill="{color}"/>')
        parts.append(f'<text x="{legend_x + 18}" y="73" class="legend-text">{esc(label)}</text>')
        legend_x += max(120, len(label) * 7 + 42)
    for tick in axis_ticks(0, max_v, 4):
        y = y_for(tick)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" class="axis">{tick:,}</text>')
    for idx, row in enumerate(rows):
        group_x = left + idx * group_w + (group_w - series_w) / 2
        for s_idx, (key, label, color) in enumerate(series):
            value = numeric(row, key)
            x = group_x + s_idx * (bar_w + bar_gap)
            y = y_for(value)
            h = max(1, top + plot_h - y)
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{color}" rx="2">'
                f'<title>{esc(row["label"])} {esc(label)}: {value:,}</title></rect>'
            )
        if idx == 0 or idx == len(rows) - 1 or idx % 2 == 0:
            parts.append(f'<text x="{left + idx * group_w + group_w / 2:.1f}" y="{height - 24}" text-anchor="middle" class="axis">{esc(row["label"])}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def monthly_net_svg(rows, noun="Core Trac tickets"):
    recent = [row for row in rows if row["month"] >= "2024-01-01"]
    width, height = 1120, 310
    left, right, top, bottom = 70, 34, 82, 54
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [numeric(row, "net") for row in recent]
    max_abs = max(abs(v) for v in values) if values else 1
    max_abs = int(math.ceil((max_abs + 20) / 50) * 50)
    group_w = plot_w / max(len(recent), 1)
    bar_w = group_w * 0.62

    def y_for(value):
        return scale(value, -max_abs, max_abs, top + plot_h, top)

    zero = y_for(0)
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Monthly net flow for {esc(noun)}">',
        f'<text x="{left}" y="24" class="chart-title">Monthly net flow around the turn</text>',
        f'<text x="{left}" y="46" class="chart-note">The line below zero means closures exceeded new {esc(noun)}.</text>',
    ]
    for tick in axis_ticks(-max_abs, max_abs, 4):
        y = y_for(tick)
        cls = "zero-line" if tick == 0 else "grid"
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="{cls}"/>')
        if tick != 0:
            parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" class="axis">{tick:+,}</text>')
    points = []
    for idx, row in enumerate(recent):
        x = left + idx * group_w + group_w / 2
        y = y_for(numeric(row, "net"))
        points.append(f"{x:.1f},{y:.1f}")
    if points:
        parts.append(
            f'<polyline points="{" ".join(points)}" fill="none" stroke="#2563eb" stroke-width="4" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )
    for idx, row in enumerate(recent):
        value = numeric(row, "net")
        x = left + idx * group_w + group_w / 2
        y = y_for(value)
        color = "#2563eb" if value >= 0 else "#dc2626"
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}">'
            f'<title>{esc(row["month"])} net: {value:+,}</title></circle>'
        )
        if idx == 0 or row["month"][5:7] == "01":
            parts.append(f'<text x="{x:.1f}" y="{height - 22}" text-anchor="middle" class="axis">{esc(row["month"][:4])}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def horizontal_bars_svg(rows, value_key, label_key, title, note, color, aria):
    rows = rows[:10]
    width = 1120
    row_h = 30
    height = 112 + row_h * len(rows)
    left, right, top = 220, 52, 82
    plot_w = width - left - right
    max_v = max((numeric(row, value_key) for row in rows), default=1)
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(aria)}">',
        f'<text x="40" y="24" class="chart-title">{esc(title)}</text>',
        f'<text x="40" y="46" class="chart-note">{esc(note)}</text>',
    ]
    for idx, row in enumerate(rows):
        y = top + idx * row_h
        value = numeric(row, value_key)
        bar_w = value * plot_w / max_v
        parts.append(f'<text x="{left - 16}" y="{y + 17}" text-anchor="end" class="bar-label">{esc(row[label_key])}</text>')
        parts.append(f'<rect x="{left}" y="{y}" width="{plot_w}" height="18" fill="#e5e7eb" rx="3"/>')
        parts.append(f'<rect x="{left}" y="{y}" width="{bar_w:.1f}" height="18" fill="{color}" rx="3"/>')
        parts.append(f'<text x="{left + bar_w + 10:.1f}" y="{y + 14}" class="axis">{value:,}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def metric_strip(summary, q_rows, gh_rows):
    latest = q_rows[-1]
    current_open = summary["current_open"]
    window_created = summary["window_created"]
    window_closed = summary["window_closed"]
    linked = summary["github_window_linked"]
    noun = summary["view_noun"]
    pr_note = "wordpress-develop PRs created since the GitHub mirror started"
    if summary["slug"] != "all":
        pr_note = f'wordpress-develop PRs linked to {noun.lower()}'
    items = [
        (f"Current open {noun}", fmt_int(current_open), f"{summary['chart_label']} not closed today"),
        ("Since 2003 ticket flow", f'{fmt_int(window_created)} new / {fmt_int(window_closed)} closed', "January 1, 2003 through June 11, 2026"),
        ("Reporter flow", f'{fmt_int(latest["first_time_reporters"])} first-time in latest quarter', "Latest quarter is partial"),
        ("GitHub PRs linked to Trac", fmt_int(linked), pr_note),
    ]
    parts = ['<div class="metric-grid">']
    for label, value, note in items:
        parts.append(
            '<div class="metric">'
            f'<div class="metric-label">{esc(label)}</div>'
            f'<div class="metric-value">{esc(value)}</div>'
            f'<div class="metric-note">{esc(note)}</div>'
            '</div>'
        )
    parts.append("</div>")
    return "\n".join(parts)


def report_stats_for_view(view):
    q_rows = view["quarterly"]
    full_q = [r for r in q_rows if r["quarter"] != "2026-04-01"]
    nonzero_full_q = [r for r in full_q if numeric(r, "created") > 0]
    if nonzero_full_q:
        early = nonzero_full_q[:4]
        recent = nonzero_full_q[-4:]
    else:
        early = q_rows[:4]
        recent = q_rows[-4:]
    early_created = statistics.mean(numeric(r, "created") for r in early)
    recent_created = statistics.mean(numeric(r, "created") for r in recent)
    early_reporters = statistics.mean(numeric(r, "unique_reporters") for r in early)
    recent_reporters = statistics.mean(numeric(r, "unique_reporters") for r in recent)
    latest_open = numeric(q_rows[-1], "open_at_end")
    peak = max(q_rows, key=lambda r: numeric(r, "open_at_end"))
    peak_open = numeric(peak, "open_at_end")
    peak_label = peak["label"]
    return {
        "early_created": early_created,
        "recent_created": recent_created,
        "early_reporters": early_reporters,
        "recent_reporters": recent_reporters,
        "latest_open": latest_open,
        "peak_open": peak_open,
        "peak_label": peak_label,
    }


def render_view_panel(slug, view, active=False):
    q_rows = view["quarterly"]
    m_rows = view["monthly"]
    components = view["components"]
    resolutions = view["resolutions"]
    gh_rows = view["github_quarterly"]
    summary = view["summary"]
    stats = report_stats_for_view(view)
    noun = summary["view_noun"]
    chart_label = summary["chart_label"]
    hidden = "" if active else " hidden"
    active_class = " is-active" if active else ""
    if summary["slug"] == "all":
        gh_series = [
            ("created", "PRs opened", LINE_COLORS["prs"]),
            ("closed", "PRs closed", LINE_COLORS["pr_closed"]),
            ("linked_to_trac", "Linked to Trac", LINE_COLORS["first"]),
        ]
        gh_note = "Quarterly wordpress-develop PR activity. Trac remains the authoritative issue tracker."
        gh_aria = "WordPress develop GitHub PR activity by quarter"
    else:
        gh_series = [
            ("created", "Linked PRs opened", LINE_COLORS["prs"]),
            ("closed", "Linked PRs closed", LINE_COLORS["pr_closed"]),
        ]
        gh_note = f"Quarterly wordpress-develop PRs that reference {noun.lower()}."
        gh_aria = f"WordPress develop GitHub PR activity by quarter for {noun}"

    return f"""
  <section class="view-panel{active_class}" data-view-panel="{esc(slug)}"{hidden}>
    {metric_strip(summary, q_rows, gh_rows)}

    <section class="chart-band">
      {line_chart_svg(q_rows, [("open_at_end", "Open tickets", LINE_COLORS["open"])], f"Open {chart_label} over time", f"Backlog peaked at {fmt_int(stats['peak_open'])} in {stats['peak_label']}; latest sampled count is {fmt_int(stats['latest_open'])}.", f"Open {chart_label} over time")}
    </section>

    <section class="chart-band">
      {line_chart_svg(q_rows, [("created", "New tickets", LINE_COLORS["created"]), ("closed", "Closed tickets", LINE_COLORS["closed"])], f"New and closed {noun} by quarter", "Quarterly flow: blue is newly opened and red is closed.", f"New and closed {noun} by quarter")}
    </section>

    <section class="chart-band">
      {monthly_net_svg(m_rows, noun.lower())}
    </section>

    <section class="chart-band">
      {line_chart_svg(q_rows, [("unique_reporters", "Unique reporters", LINE_COLORS["reporters"]), ("first_time_reporters", "First-time reporters", LINE_COLORS["first"])], f"People opening {noun}", f"Purple is unique reporters per quarter; orange is first-time reporters per quarter.", f"People opening {noun}")}
    </section>

    <section class="chart-band">
      {horizontal_bars_svg(components, "current_open", "component", "Where the open backlog sits", f"Current open {noun.lower()} by component.", "#0f766e", f"Current open {noun} by component")}
    </section>

    <section class="chart-band">
      {horizontal_bars_svg(resolutions, "closed_in_window", "resolution", "How tickets closed", f"Resolution mix for {noun.lower()} closed since 2003.", "#7c3aed", f"{noun} closure resolution mix")}
    </section>

    <section class="chart-band">
      {line_chart_svg(gh_rows, gh_series, "GitHub code-review activity by quarter", gh_note, gh_aria)}
    </section>

    <section class="discussion">
      <article class="point">
        <h2>{esc(summary["view_label"])} backlog today.</h2>
        <p>{esc(chart_label)} have {fmt_int(summary["current_open"])} open tickets today out of {fmt_int(summary["ticket_count"])} total tickets in this view.</p>
      </article>
      <article class="point">
        <h2>Ticket flow is the main story.</h2>
        <p>New tickets averaged {stats['early_created']:.0f} per quarter in the first active year of this view and {stats['recent_created']:.0f} recently. When closures rise above new tickets, the open backlog bends down.</p>
      </article>
      <article class="point">
        <h2>GitHub is review traffic, not the issue source.</h2>
        <p>wordpress-develop has {fmt_int(summary["github_window_linked"])} PRs linked to this view. It helps explain implementation activity without replacing Trac ticket flow.</p>
      </article>
    </section>
  </section>
"""


def render_report(data):
    views = data["views"]
    view_order = data["view_order"]
    panels = "\n".join(render_view_panel(slug, views[slug], active=(idx == 0)) for idx, slug in enumerate(view_order))
    buttons = "\n".join(
        f'<button class="view-button{" is-active" if idx == 0 else ""}" type="button" data-view-button="{esc(slug)}" aria-pressed="{"true" if idx == 0 else "false"}">{esc(views[slug]["summary"]["view_label"])}</button>'
        for idx, slug in enumerate(view_order)
    )

    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress Core Ticket Flow Since 2003</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f8fafc;
      --text: #172033;
      --muted: #64748b;
      --rule: #d8dee8;
      --panel: #ffffff;
      --ink: #0f172a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      max-width: 1220px;
      margin: 0 auto;
      padding: 44px 24px 64px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: clamp(32px, 4vw, 56px);
      line-height: 1.02;
      letter-spacing: 0;
      color: var(--ink);
    }}
    .deck {{
      margin: 0;
      max-width: 880px;
      color: #475569;
      font-size: 18px;
    }}
    .view-switch {{
      display: inline-flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 24px;
      padding: 5px;
      border: 1px solid var(--rule);
      border-radius: 8px;
      background: #ffffff;
    }}
    .view-button {{
      appearance: none;
      border: 0;
      border-radius: 6px;
      background: transparent;
      color: #475569;
      cursor: pointer;
      font: inherit;
      font-weight: 800;
      padding: 9px 12px;
    }}
    .view-button.is-active {{
      background: #172033;
      color: #ffffff;
    }}
    .view-panel[hidden] {{
      display: none;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin: 30px 0 28px;
    }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--rule);
      border-radius: 8px;
      padding: 16px;
      min-height: 126px;
    }}
    .metric-label {{
      color: var(--muted);
      font-weight: 700;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    .metric-value {{
      margin-top: 8px;
      color: var(--ink);
      font-size: 25px;
      line-height: 1.16;
      font-weight: 800;
    }}
    .metric-note {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
    }}
    .chart-band {{
      margin-top: 18px;
      padding: 18px 18px 10px;
      border: 1px solid var(--rule);
      border-radius: 8px;
      background: var(--panel);
      overflow-x: auto;
      overflow-y: hidden;
    }}
    .split {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      margin-top: 18px;
    }}
    svg {{
      display: block;
      width: 100%;
      height: auto;
      overflow: visible;
    }}
    .chart-title {{
      font-size: 23px;
      font-weight: 800;
      fill: var(--ink);
    }}
    .chart-note {{
      font-size: 14px;
      fill: var(--muted);
    }}
    .legend-text, .axis, .bar-label {{
      font-size: 12px;
      fill: #475569;
    }}
    .bar-label {{
      font-weight: 650;
    }}
    .grid {{
      stroke: #e2e8f0;
      stroke-width: 1;
    }}
    .zero-line {{
      stroke: #334155;
      stroke-width: 1.3;
    }}
    .discussion {{
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 18px;
      margin-top: 28px;
    }}
    .point {{
      border-top: 4px solid #0f766e;
      background: #ffffff;
      border-radius: 8px;
      padding: 18px;
      min-height: 168px;
    }}
    .point:nth-child(2) {{ border-top-color: #2563eb; }}
    .point:nth-child(3) {{ border-top-color: #ea580c; }}
    .point h2 {{
      margin: 0 0 8px;
      font-size: 18px;
      line-height: 1.25;
      color: var(--ink);
    }}
    .point p {{
      margin: 0;
      color: #475569;
    }}
    details {{
      margin-top: 24px;
      border: 1px solid var(--rule);
      border-radius: 8px;
      background: #fff;
      padding: 14px 16px;
    }}
    summary {{
      cursor: pointer;
      font-weight: 750;
      color: var(--ink);
    }}
    .method {{
      color: #475569;
      max-width: 920px;
    }}
    a {{ color: #2563eb; }}
    @media (max-width: 860px) {{
      main {{ padding: 30px 14px 48px; }}
      .metric-grid, .split, .discussion {{ grid-template-columns: 1fr; }}
      .metric {{ min-height: auto; }}
      .chart-band {{ padding: 12px 8px 6px; overflow: visible; }}
      .chart-band svg {{
        width: 100%;
        max-width: 100%;
      }}
      .deck {{ font-size: 16px; }}
    }}
  </style>
</head>
<body>
<main>
  <h1>WordPress Core ticket flow since 2003</h1>
  <p class="deck">A long-run view of Core Trac backlog, ticket flow, reporter activity, closure mix, and GitHub code-review activity linked to Trac.</p>

  <nav class="view-switch" aria-label="Ticket category view">
    {buttons}
  </nav>

  {panels}

  <details>
    <summary>Method and source files</summary>
    <div class="method">
      <p>Data window: January 1, 2003 through June 11, 2026. Core ticket inventory comes from Core Trac CSV exports; the first ticket in the export was created on June 10, 2004. Closure and reopen timing comes from public ticket RSS feeds for closed and reopened tickets. GitHub activity comes from the GitHub API for <code>WordPress/wordpress-develop</code> pull requests.</p>
      <p>Generated files: <code>quarterly_metrics.csv</code>, <code>monthly_metrics.csv</code>, <code>component_summary.csv</code>, <code>resolution_summary.csv</code>, and <code>github_pr_quarterly.csv</code>.</p>
      <p>Filtered CSVs add <code>_bugs</code> or <code>_feature_requests</code> before the extension. Category filters come from <code>{esc(CLASSIFICATION_DB)}</code>.</p>
      <p>Most closure dates are parsed from RSS status-change events. Tickets without a public close event in the parsed feed use the Trac modified timestamp as a fallback.</p>
    </div>
  </details>
  <script>
    const buttons = [...document.querySelectorAll("[data-view-button]")];
    const panels = [...document.querySelectorAll("[data-view-panel]")];
    function setView(slug) {{
      buttons.forEach((button) => {{
        const active = button.dataset.viewButton === slug;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      }});
      panels.forEach((panel) => {{
        panel.hidden = panel.dataset.viewPanel !== slug;
        panel.classList.toggle("is-active", panel.dataset.viewPanel === slug);
      }});
      try {{ localStorage.setItem("core-ticket-flow-view", slug); }} catch (_error) {{}}
    }}
    buttons.forEach((button) => button.addEventListener("click", () => setView(button.dataset.viewButton)));
    const initial = (() => {{
      try {{ return localStorage.getItem("core-ticket-flow-view"); }} catch (_error) {{ return null; }}
    }})();
    if (initial && buttons.some((button) => button.dataset.viewButton === initial)) {{
      setView(initial);
    }}
  </script>
</main>
</body>
</html>
"""
    OUT.write_text(html_text, encoding="utf-8")
    eprint(f"wrote {OUT}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-trac", action="store_true")
    parser.add_argument("--force-rss", action="store_true")
    parser.add_argument("--force-github", action="store_true")
    parser.add_argument("--skip-rss", action="store_true")
    parser.add_argument("--rss-workers", type=int, default=4)
    parser.add_argument("--rss-limit", type=int)
    args = parser.parse_args()

    ensure_dirs()
    fetch_trac_inventory(force=args.force_trac)
    if not args.skip_rss:
        fetch_trac_events(force=args.force_rss, workers=args.rss_workers, limit=args.rss_limit)
    fetch_github_prs(force=args.force_github)
    data = analyze()
    render_report(data)


if __name__ == "__main__":
    main()
