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
import re
import sqlite3
import subprocess
import sys
import threading
import time
import http.cookies
import http.cookiejar
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_ticket_classification")
DB_PATH = ROOT / "wordpress_tickets.sqlite"
OUT = ROOT / "final_report.html"
RAW = ROOT / "raw"

GUTENBERG_ROOT = Path("/Users/admin/gutenberg_issue_analysis")
CORE_ROOT = Path("/Users/admin/wordpress_core_issue_analysis")
PAGES_ROOT = Path("/Users/admin/sqlite-database-integration-pages")

GUTENBERG_ISSUES_CSV = GUTENBERG_ROOT / "issues_inventory.csv"
CORE_TICKETS_CSV = CORE_ROOT / "raw" / "trac_tickets.csv"
CORE_EVENTS_CSV = CORE_ROOT / "raw" / "trac_ticket_events.csv"

GITHUB_OWNER = "WordPress"
GITHUB_REPO = "gutenberg"
GITHUB_BASE = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
TRAC = "https://core.trac.wordpress.org"

END = dt.datetime(2026, 6, 11, 23, 59, 59, tzinfo=dt.timezone.utc)
CLASSIFIER_VERSION = "2026-06-12.1"
UA = "codex-wordpress-ticket-classification/1.0"
INVALID_XML_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

PRIMARY_CATEGORIES = [
    "bug",
    "feature_request",
    "enhancement",
    "task_maintenance",
    "documentation",
    "support_question",
    "test_flake",
    "accessibility",
    "performance",
    "security",
    "other",
]

CATEGORY_LABELS = {
    "bug": "Bugs",
    "feature_request": "Feature requests",
    "enhancement": "Enhancements",
    "task_maintenance": "Tasks / maintenance",
    "documentation": "Documentation",
    "support_question": "Support / questions",
    "test_flake": "Flaky tests",
    "accessibility": "Accessibility",
    "performance": "Performance",
    "security": "Security",
    "other": "Other / unclear",
}

CATEGORY_COLORS = {
    "bug": "#dc2626",
    "feature_request": "#2563eb",
    "enhancement": "#0891b2",
    "task_maintenance": "#7c3aed",
    "documentation": "#0f766e",
    "support_question": "#ea580c",
    "test_flake": "#be123c",
    "accessibility": "#9333ea",
    "performance": "#16a34a",
    "security": "#b91c1c",
    "other": "#64748b",
}


def eprint(message):
    print(message, file=sys.stderr, flush=True)


def ensure_dirs():
    ROOT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)


def now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value):
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_rss_date(value):
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


def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("\x00", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def json_dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def connect():
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=120)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA busy_timeout=120000")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
  source TEXT NOT NULL,
  ticket_id TEXT NOT NULL,
  url TEXT,
  title TEXT,
  body TEXT,
  state TEXT,
  status TEXT,
  resolution TEXT,
  type_raw TEXT,
  reporter TEXT,
  owner TEXT,
  author_type TEXT,
  author_association TEXT,
  created_at TEXT,
  updated_at TEXT,
  closed_at TEXT,
  component TEXT,
  milestone TEXT,
  priority TEXT,
  severity TEXT,
  labels_json TEXT NOT NULL DEFAULT '[]',
  keywords TEXT,
  comments_count INTEGER NOT NULL DEFAULT 0,
  raw_json TEXT,
  body_fetched_at TEXT,
  metadata_updated_at TEXT,
  PRIMARY KEY (source, ticket_id)
);

CREATE TABLE IF NOT EXISTS ticket_labels (
  source TEXT NOT NULL,
  ticket_id TEXT NOT NULL,
  label TEXT NOT NULL,
  PRIMARY KEY (source, ticket_id, label)
);

CREATE TABLE IF NOT EXISTS ticket_comments (
  source TEXT NOT NULL,
  ticket_id TEXT NOT NULL,
  comment_id TEXT NOT NULL,
  author TEXT,
  created_at TEXT,
  updated_at TEXT,
  body TEXT,
  raw_json TEXT,
  PRIMARY KEY (source, ticket_id, comment_id)
);

CREATE TABLE IF NOT EXISTS ticket_events (
  source TEXT NOT NULL,
  ticket_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  event_type TEXT,
  actor TEXT,
  created_at TEXT,
  body TEXT,
  raw_json TEXT,
  PRIMARY KEY (source, ticket_id, event_id)
);

CREATE TABLE IF NOT EXISTS fetch_state (
  source TEXT NOT NULL,
  item_type TEXT NOT NULL,
  item_key TEXT NOT NULL,
  status TEXT NOT NULL,
  fetched_at TEXT,
  error TEXT,
  PRIMARY KEY (source, item_type, item_key)
);

CREATE TABLE IF NOT EXISTS ticket_classifications (
  source TEXT NOT NULL,
  ticket_id TEXT NOT NULL,
  primary_category TEXT NOT NULL,
  secondary_categories_json TEXT NOT NULL,
  confidence TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  classifier_version TEXT NOT NULL,
  method TEXT NOT NULL,
  shard INTEGER,
  classified_by TEXT,
  classified_at TEXT NOT NULL,
  PRIMARY KEY (source, ticket_id)
);

CREATE TABLE IF NOT EXISTS classification_audit (
  source TEXT NOT NULL,
  ticket_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  note TEXT NOT NULL,
  payload_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_tickets_source_created ON tickets(source, created_at);
CREATE INDEX IF NOT EXISTS idx_tickets_source_state ON tickets(source, state, status);
CREATE INDEX IF NOT EXISTS idx_comments_ticket ON ticket_comments(source, ticket_id);
CREATE INDEX IF NOT EXISTS idx_events_ticket ON ticket_events(source, ticket_id);
CREATE INDEX IF NOT EXISTS idx_class_category ON ticket_classifications(source, primary_category);
"""


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def upsert_ticket(conn, row):
    fields = [
        "source",
        "ticket_id",
        "url",
        "title",
        "body",
        "state",
        "status",
        "resolution",
        "type_raw",
        "reporter",
        "owner",
        "author_type",
        "author_association",
        "created_at",
        "updated_at",
        "closed_at",
        "component",
        "milestone",
        "priority",
        "severity",
        "labels_json",
        "keywords",
        "comments_count",
        "raw_json",
        "body_fetched_at",
        "metadata_updated_at",
    ]
    values = {key: row.get(key) for key in fields}
    values.setdefault("labels_json", "[]")
    values.setdefault("comments_count", 0)
    values["metadata_updated_at"] = values.get("metadata_updated_at") or now_iso()
    conn.execute(
        f"""
        INSERT INTO tickets ({','.join(fields)})
        VALUES ({','.join(':' + key for key in fields)})
        ON CONFLICT(source, ticket_id) DO UPDATE SET
          url=excluded.url,
          title=excluded.title,
          body=COALESCE(excluded.body, tickets.body),
          state=excluded.state,
          status=excluded.status,
          resolution=excluded.resolution,
          type_raw=excluded.type_raw,
          reporter=excluded.reporter,
          owner=excluded.owner,
          author_type=excluded.author_type,
          author_association=excluded.author_association,
          created_at=excluded.created_at,
          updated_at=excluded.updated_at,
          closed_at=excluded.closed_at,
          component=excluded.component,
          milestone=excluded.milestone,
          priority=excluded.priority,
          severity=excluded.severity,
          labels_json=excluded.labels_json,
          keywords=excluded.keywords,
          comments_count=excluded.comments_count,
          raw_json=COALESCE(excluded.raw_json, tickets.raw_json),
          body_fetched_at=COALESCE(excluded.body_fetched_at, tickets.body_fetched_at),
          metadata_updated_at=excluded.metadata_updated_at
        """,
        values,
    )


def replace_labels(conn, source, ticket_id, labels):
    conn.execute("DELETE FROM ticket_labels WHERE source=? AND ticket_id=?", (source, ticket_id))
    conn.executemany(
        "INSERT OR IGNORE INTO ticket_labels(source,ticket_id,label) VALUES (?,?,?)",
        [(source, ticket_id, label) for label in labels if label],
    )


def ingest_gutenberg():
    conn = connect()
    count = 0
    with GUTENBERG_ISSUES_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels = [label.strip() for label in (row.get("labels") or "").split("|") if label.strip()]
            ticket_id = str(row["number"])
            upsert_ticket(
                conn,
                {
                    "source": "gutenberg",
                    "ticket_id": ticket_id,
                    "url": row.get("html_url"),
                    "title": row.get("title"),
                    "body": None,
                    "state": row.get("state"),
                    "status": row.get("state"),
                    "resolution": row.get("state_reason"),
                    "type_raw": "",
                    "reporter": row.get("author_login"),
                    "owner": "",
                    "author_type": row.get("author_type"),
                    "author_association": row.get("author_association"),
                    "created_at": row.get("created_at"),
                    "updated_at": "",
                    "closed_at": row.get("closed_at"),
                    "component": "",
                    "milestone": row.get("milestone"),
                    "priority": "",
                    "severity": "",
                    "labels_json": json_dumps(labels),
                    "keywords": "",
                    "comments_count": int(row.get("comments") or 0),
                    "raw_json": json_dumps(row),
                    "metadata_updated_at": now_iso(),
                },
            )
            replace_labels(conn, "gutenberg", ticket_id, labels)
            count += 1
            if count % 5000 == 0:
                conn.commit()
                eprint(f"ingested Gutenberg metadata {count:,}")
    conn.commit()
    conn.close()
    eprint(f"ingested Gutenberg metadata {count:,}")


def ingest_core():
    conn = connect()
    count = 0
    with CORE_TICKETS_CSV.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            keywords = row.get("keywords") or ""
            labels = [f"type:{row.get('type') or ''}", f"component:{row.get('component') or ''}"]
            labels += [f"keyword:{kw}" for kw in keywords.split() if kw]
            ticket_id = str(row["id"])
            status = (row.get("status") or "").lower()
            upsert_ticket(
                conn,
                {
                    "source": "core",
                    "ticket_id": ticket_id,
                    "url": f"{TRAC}/ticket/{ticket_id}",
                    "title": row.get("summary"),
                    "body": None,
                    "state": "closed" if status == "closed" else "open",
                    "status": row.get("status"),
                    "resolution": row.get("resolution"),
                    "type_raw": row.get("type"),
                    "reporter": row.get("reporter"),
                    "owner": row.get("owner"),
                    "author_type": "",
                    "author_association": "",
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("modified_at"),
                    "closed_at": "",
                    "component": row.get("component"),
                    "milestone": row.get("milestone"),
                    "priority": row.get("priority"),
                    "severity": row.get("severity"),
                    "labels_json": json_dumps([label for label in labels if label and not label.endswith(":")]),
                    "keywords": keywords,
                    "comments_count": 0,
                    "raw_json": json_dumps(row),
                    "metadata_updated_at": now_iso(),
                },
            )
            replace_labels(conn, "core", ticket_id, [label for label in labels if label and not label.endswith(":")])
            count += 1
            if count % 5000 == 0:
                conn.commit()
                eprint(f"ingested Core metadata {count:,}")
    if CORE_EVENTS_CSV.exists():
        with CORE_EVENTS_CSV.open(newline="", encoding="utf-8") as f:
            for event in csv.DictReader(f):
                body = " ".join(part for part in [event.get("title"), event.get("from_status"), event.get("to_status")] if part)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO ticket_events(source,ticket_id,event_id,event_type,actor,created_at,body,raw_json)
                    VALUES ('core',?,?,?,?,?,?,?)
                    """,
                    (
                        event["ticket_id"],
                        f"status:{event['event_at']}:{event['event_type']}",
                        event.get("event_type"),
                        event.get("creator"),
                        event.get("event_at"),
                        body,
                        json_dumps(event),
                    ),
                )
    conn.commit()
    conn.close()
    eprint(f"ingested Core metadata {count:,}")


def ingest_all():
    init_db()
    ingest_gutenberg()
    ingest_core()


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
                    if remaining <= 20:
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


def fetch_gutenberg_issues(force=False):
    conn = connect()
    if not force:
        missing = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE source='gutenberg' AND (body IS NULL OR body_fetched_at IS NULL)"
        ).fetchone()[0]
        if missing == 0:
            eprint("using cached Gutenberg issue bodies")
            conn.close()
            return
    client = GitHubClient()
    url = GITHUB_BASE + "/issues?" + urllib.parse.urlencode(
        {"state": "all", "sort": "created", "direction": "asc", "per_page": "100"}
    )
    count = 0
    while url:
        items, headers = client.request_with_headers(url)
        stop = False
        for item in items:
            if "pull_request" in item:
                continue
            created = parse_iso(item.get("created_at"))
            if created and created > END:
                stop = True
                continue
            labels = [label["name"] for label in item.get("labels") or []]
            user = item.get("user") or {}
            milestone = item.get("milestone") or {}
            ticket_id = str(item["number"])
            upsert_ticket(
                conn,
                {
                    "source": "gutenberg",
                    "ticket_id": ticket_id,
                    "url": item.get("html_url"),
                    "title": item.get("title"),
                    "body": item.get("body") or "",
                    "state": item.get("state"),
                    "status": item.get("state"),
                    "resolution": item.get("state_reason") or "",
                    "type_raw": "",
                    "reporter": user.get("login") or "",
                    "owner": "",
                    "author_type": user.get("type") or "",
                    "author_association": item.get("author_association") or "",
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                    "closed_at": item.get("closed_at") or "",
                    "component": "",
                    "milestone": milestone.get("title") or "",
                    "priority": "",
                    "severity": "",
                    "labels_json": json_dumps(labels),
                    "keywords": "",
                    "comments_count": int(item.get("comments") or 0),
                    "raw_json": json_dumps(item),
                    "body_fetched_at": now_iso(),
                    "metadata_updated_at": now_iso(),
                },
            )
            replace_labels(conn, "gutenberg", ticket_id, labels)
            count += 1
        conn.commit()
        eprint(f"fetched Gutenberg issue bodies {count:,}")
        if stop:
            break
        url = next_link(headers)
    conn.close()


def fetch_gutenberg_comments(force=False):
    conn = connect()
    known = {row[0] for row in conn.execute("SELECT ticket_id FROM tickets WHERE source='gutenberg'")}
    if not force:
        state = conn.execute(
            "SELECT status FROM fetch_state WHERE source='gutenberg' AND item_type='repo_comments' AND item_key='all'"
        ).fetchone()
        if state and state[0] == "ok":
            eprint("using cached Gutenberg comments")
            conn.close()
            return
    client = GitHubClient()
    url = GITHUB_BASE + "/issues/comments?" + urllib.parse.urlencode(
        {"sort": "created", "direction": "asc", "per_page": "100"}
    )
    count = 0
    while url:
        comments, headers = client.request_with_headers(url)
        for comment in comments:
            issue_url = comment.get("issue_url") or ""
            ticket_id = issue_url.rstrip("/").split("/")[-1]
            if ticket_id not in known:
                continue
            user = comment.get("user") or {}
            conn.execute(
                """
                INSERT OR REPLACE INTO ticket_comments(source,ticket_id,comment_id,author,created_at,updated_at,body,raw_json)
                VALUES ('gutenberg',?,?,?,?,?,?,?)
                """,
                (
                    ticket_id,
                    str(comment["id"]),
                    user.get("login") or "",
                    comment.get("created_at") or "",
                    comment.get("updated_at") or "",
                    comment.get("body") or "",
                    json_dumps(comment),
                ),
            )
            count += 1
        conn.commit()
        if count and count % 5000 == 0:
            eprint(f"fetched Gutenberg comments {count:,}")
        url = next_link(headers)
    conn.execute(
        "INSERT OR REPLACE INTO fetch_state(source,item_type,item_key,status,fetched_at,error) VALUES ('gutenberg','repo_comments','all','ok',?, '')",
        (now_iso(),),
    )
    conn.commit()
    conn.close()
    eprint(f"fetched Gutenberg comments {count:,}")


def fetch_gutenberg_events(force=False):
    conn = connect()
    known = {row[0] for row in conn.execute("SELECT ticket_id FROM tickets WHERE source='gutenberg'")}
    if not force:
        state = conn.execute(
            "SELECT status FROM fetch_state WHERE source='gutenberg' AND item_type='repo_events' AND item_key='all'"
        ).fetchone()
        if state and state[0] == "ok":
            eprint("using cached Gutenberg issue events")
            conn.close()
            return
    client = GitHubClient()
    url = GITHUB_BASE + "/issues/events?" + urllib.parse.urlencode({"per_page": "100"})
    count = 0
    while url:
        events, headers = client.request_with_headers(url)
        for event in events:
            issue = event.get("issue") or {}
            if "pull_request" in issue:
                continue
            ticket_id = str(issue.get("number") or "")
            if ticket_id not in known:
                continue
            actor = event.get("actor") or {}
            conn.execute(
                """
                INSERT OR REPLACE INTO ticket_events(source,ticket_id,event_id,event_type,actor,created_at,body,raw_json)
                VALUES ('gutenberg',?,?,?,?,?,?,?)
                """,
                (
                    ticket_id,
                    str(event.get("id") or f"{ticket_id}:{event.get('event')}:{event.get('created_at')}"),
                    event.get("event") or "",
                    actor.get("login") or "",
                    event.get("created_at") or "",
                    event.get("label", {}).get("name", "") if isinstance(event.get("label"), dict) else "",
                    json_dumps(event),
                ),
            )
            count += 1
        conn.commit()
        if count and count % 5000 == 0:
            eprint(f"fetched Gutenberg events {count:,}")
        url = next_link(headers)
    conn.execute(
        "INSERT OR REPLACE INTO fetch_state(source,item_type,item_key,status,fetched_at,error) VALUES ('gutenberg','repo_events','all','ok',?, '')",
        (now_iso(),),
    )
    conn.commit()
    conn.close()
    eprint(f"fetched Gutenberg events {count:,}")


class TracClient:
    def __init__(self):
        self.jar = urllib.request.HTTPCookieProcessor()
        self.cookiejar = self.jar.cookiejar
        self.opener = urllib.request.build_opener(self.jar)
        self.lock = threading.Lock()

    def _cookie(self, name):
        now = time.time()
        for cookie in self.cookiejar:
            min_life = 30 if name == "_hcp" else 1
            if cookie.name == name and (cookie.expires is None or cookie.expires > now + min_life):
                return cookie.value
        return None

    def _clear_cookie(self, name):
        for cookie in list(self.cookiejar):
            if cookie.name == name:
                try:
                    self.cookiejar.clear(cookie.domain, cookie.path, cookie.name)
                except KeyError:
                    pass

    def solve_challenge(self, trigger_url, force=False):
        with self.lock:
            for solve_attempt in range(4):
                if force or solve_attempt:
                    self._clear_cookie("_hcp")
                    self._clear_cookie("_hcc")
                if self._cookie("_hcp"):
                    return
                headers = {"User-Agent": UA, "Accept": "text/html,*/*"}
                if not self._cookie("_hcc"):
                    try:
                        self.opener.open(urllib.request.Request(trigger_url, headers=headers), timeout=60).read()
                    except urllib.error.HTTPError as exc:
                        self._store_hcc_from_headers(exc.headers)
                        exc.read(500)
                        if exc.code != 403:
                            raise
                if not self._cookie("_hcc"):
                    challenge_url = f"{TRAC}/query?status=!closed&max=1&format=csv&col=id"
                    try:
                        self.opener.open(urllib.request.Request(challenge_url, headers=headers), timeout=60).read()
                    except urllib.error.HTTPError as exc:
                        self._store_hcc_from_headers(exc.headers)
                        exc.read(500)
                        if exc.code != 403:
                            raise
                hcc = self._cookie("_hcc")
                if not hcc:
                    if solve_attempt < 3:
                        time.sleep(3)
                        continue
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
                headers = {
                    "User-Agent": UA,
                    "Accept": "*/*",
                    "X-Hashcash-Solution": base64.b64encode(solution.encode("utf-8")).decode("ascii"),
                    "X-Interactive": "",
                }
                req = urllib.request.Request(f"{TRAC}/__challenge", data=b"", headers=headers, method="POST")
                try:
                    with self.opener.open(req, timeout=60) as resp:
                        resp.read()
                    if self._cookie("_hcp"):
                        return
                except urllib.error.HTTPError as exc:
                    exc.read(500)
                    if exc.code != 400 or solve_attempt == 3:
                        raise
                time.sleep(5 + solve_attempt * 5)
            raise RuntimeError("Could not complete Core Trac challenge.")

    def _store_hcc_from_headers(self, headers):
        raw = headers.get("Set-Cookie") or ""
        if "_hcc=" not in raw:
            return
        jar = http.cookies.SimpleCookie()
        try:
            jar.load(raw)
        except http.cookies.CookieError:
            return
        morsel = jar.get("_hcc")
        if not morsel:
            return
        expires = None
        if morsel["max-age"]:
            try:
                expires = int(time.time()) + int(morsel["max-age"])
            except ValueError:
                expires = None
        cookie = http.cookiejar.Cookie(
            version=0,
            name="_hcc",
            value=morsel.value,
            port=None,
            port_specified=False,
            domain="core.trac.wordpress.org",
            domain_specified=True,
            domain_initial_dot=False,
            path=morsel["path"] or "/",
            path_specified=True,
            secure=False,
            expires=expires,
            discard=False,
            comment=None,
            comment_url=None,
            rest={},
            rfc2109=False,
        )
        self.cookiejar.set_cookie(cookie)

    def cookie_header(self):
        parts = []
        for cookie in self.cookiejar:
            if cookie.name in {"_hcp", "_hcc"}:
                parts.append(f"{cookie.name}={cookie.value}")
        return "; ".join(parts)


def parse_core_rss(ticket_id, data):
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        text = data.decode("utf-8", "replace")
        text = INVALID_XML_CHARS.sub(" ", text).replace("\ufffd", " ")
        root = ET.fromstring(text.encode("utf-8"))
    channel = root.find("./channel")
    body = clean_text(channel.findtext("description") if channel is not None else "")
    comments = []
    events = []
    ns = {"dc": "http://purl.org/dc/elements/1.1/"}
    for idx, item in enumerate(root.findall("./channel/item")):
        title = clean_text(item.findtext("title") or "")
        description = clean_text(item.findtext("description") or "")
        author = item.findtext("dc:creator", default="", namespaces=ns) or ""
        created_at = iso(parse_rss_date(item.findtext("pubDate") or ""))
        link = item.findtext("link") or ""
        event_type = "comment" if not title else "change"
        event_id = link.split("#")[-1] if "#" in link else f"rss:{ticket_id}:{idx}:{created_at}:{hashlib.sha1((title+description).encode()).hexdigest()[:12]}"
        payload = {"title": title, "description": description, "link": link}
        events.append((ticket_id, event_id, event_type, author, created_at, description, json_dumps(payload)))
        if event_type == "comment" and description:
            comments.append((ticket_id, event_id, author, created_at, "", description, json_dumps(payload)))
    return body, comments, events


def fetch_core_rss_one(ticket_id, cookie_header):
    url = f"{TRAC}/ticket/{ticket_id}?format=rss"
    for attempt in range(3):
        headers = {"User-Agent": UA, "Accept": "application/rss+xml,text/xml,*/*"}
        if cookie_header:
            headers["Cookie"] = cookie_header
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=25) as resp:
                return ticket_id, resp.read(), ""
        except urllib.error.HTTPError as exc:
            exc.read(500)
            if exc.code == 429 and attempt < 2:
                retry_after = exc.headers.get("Retry-After")
                time.sleep((int(retry_after) if retry_after and retry_after.isdigit() else 8) + 0.2)
                continue
            return ticket_id, b"", repr(exc)
        except Exception as exc:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            return ticket_id, b"", repr(exc)


def chunks(values, size):
    for idx in range(0, len(values), size):
        yield values[idx : idx + size]


def fetch_core_rss(force=False, workers=8, limit=None, batch_size=1000):
    conn = connect()
    if force:
        conn.execute("DELETE FROM fetch_state WHERE source='core' AND item_type='rss'")
        conn.commit()
    rows = conn.execute("SELECT ticket_id FROM tickets WHERE source='core' ORDER BY CAST(ticket_id AS INTEGER)").fetchall()
    ids = [row[0] for row in rows]
    if limit:
        ids = ids[:limit]
    done = {
        row[0]
        for row in conn.execute(
            "SELECT item_key FROM fetch_state WHERE source='core' AND item_type='rss' AND status='ok'"
        )
    }
    pending = [ticket_id for ticket_id in ids if ticket_id not in done]
    if not pending:
        eprint(f"using cached Core RSS for {len(done):,} tickets")
        conn.close()
        return
    completed = 0
    errors = 0
    for batch in chunks(pending, batch_size):
        session = TracClient()
        session.solve_challenge(f"{TRAC}/query?status=!closed&max=1&format=csv&col=id")
        cookie_header = session.cookie_header()
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(fetch_core_rss_one, ticket_id, cookie_header): ticket_id for ticket_id in batch}
            for future in concurrent.futures.as_completed(futures):
                ticket_id = futures[future]
                try:
                    _tid, data, error = future.result()
                    if error:
                        raise RuntimeError(error)
                    body, comments, events = parse_core_rss(ticket_id, data)
                    conn.execute(
                        "UPDATE tickets SET body=?, body_fetched_at=? WHERE source='core' AND ticket_id=?",
                        (body, now_iso(), ticket_id),
                    )
                    conn.executemany(
                        """
                        INSERT OR REPLACE INTO ticket_comments(source,ticket_id,comment_id,author,created_at,updated_at,body,raw_json)
                        VALUES ('core',?,?,?,?,?,?,?)
                        """,
                        comments,
                    )
                    conn.executemany(
                        """
                        INSERT OR REPLACE INTO ticket_events(source,ticket_id,event_id,event_type,actor,created_at,body,raw_json)
                        VALUES ('core',?,?,?,?,?,?,?)
                        """,
                        events,
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO fetch_state(source,item_type,item_key,status,fetched_at,error) VALUES ('core','rss',?,'ok',?, '')",
                        (ticket_id, now_iso()),
                    )
                except Exception as exc:
                    errors += 1
                    conn.execute(
                        "INSERT OR REPLACE INTO fetch_state(source,item_type,item_key,status,fetched_at,error) VALUES ('core','rss',?,'error',?,?)",
                        (ticket_id, now_iso(), repr(exc)[:500]),
                    )
                completed += 1
                if completed % 250 == 0 or completed == len(pending):
                    conn.commit()
                    eprint(f"Core RSS {completed:,}/{len(pending):,}; errors {errors:,}")
    conn.commit()
    conn.close()


def fetch_all(args):
    fetch_gutenberg_issues(force=args.force)
    fetch_gutenberg_comments(force=args.force)
    fetch_gutenberg_events(force=args.force)
    fetch_core_rss(force=args.force, workers=args.workers, limit=args.limit)


def text_blob_for_ticket(conn, source, ticket_id):
    ticket = conn.execute(
        "SELECT * FROM tickets WHERE source=? AND ticket_id=?", (source, ticket_id)
    ).fetchone()
    comments = conn.execute(
        "SELECT body FROM ticket_comments WHERE source=? AND ticket_id=? ORDER BY created_at",
        (source, ticket_id),
    ).fetchall()
    events = conn.execute(
        "SELECT event_type, body FROM ticket_events WHERE source=? AND ticket_id=? ORDER BY created_at",
        (source, ticket_id),
    ).fetchall()
    labels = json.loads(ticket["labels_json"] or "[]")
    pieces = [
        ticket["title"] or "",
        ticket["body"] or "",
        " ".join(labels),
        ticket["type_raw"] or "",
        ticket["component"] or "",
        ticket["keywords"] or "",
        " ".join(row[0] or "" for row in comments),
        " ".join(((row[0] or "") + " " + (row[1] or "")) for row in events),
    ]
    return ticket, labels, clean_text(" ".join(pieces)).lower(), len(comments)


def has_any(text, patterns):
    return any(pattern in text for pattern in patterns)


def classify_ticket(conn, source, ticket_id, shard=None, classified_by="local"):
    ticket, labels, text, comment_count = text_blob_for_ticket(conn, source, ticket_id)
    label_text = " ".join(labels).lower()
    type_raw = (ticket["type_raw"] or "").lower()
    component = (ticket["component"] or "").lower()
    title = (ticket["title"] or "").lower()
    resolution = (ticket["resolution"] or "").lower()
    evidence = {
        "title": ticket["title"] or "",
        "type_raw": ticket["type_raw"] or "",
        "labels": labels,
        "component": ticket["component"] or "",
        "keywords": ticket["keywords"] or "",
        "resolution": ticket["resolution"] or "",
        "comment_count_read": comment_count,
        "body_present": bool(ticket["body"]),
    }
    secondary = []
    reasons = []

    def mark(category, confidence, reason):
        reasons.append(reason)
        return category, confidence

    if source == "core":
        if type_raw == "defect (bug)":
            primary, confidence = mark("bug", "high", "Core Trac type is defect (bug).")
        elif type_raw == "feature request":
            primary, confidence = mark("feature_request", "high", "Core Trac type is feature request.")
        elif type_raw == "enhancement":
            primary, confidence = mark("enhancement", "high", "Core Trac type is enhancement.")
        elif type_raw == "task (blessed)":
            primary, confidence = mark("task_maintenance", "high", "Core Trac type is task (blessed).")
        else:
            primary, confidence = mark("other", "low", "No recognized Core Trac type.")
    else:
        if "[type] flaky test" in label_text or "flaky test" in text:
            primary, confidence = mark("test_flake", "high", "Gutenberg flaky-test label or text.")
        elif "[type] developer documentation" in label_text or "[type] documentation" in label_text:
            primary, confidence = mark("documentation", "high", "Gutenberg documentation type label.")
        elif "[type] help request" in label_text:
            primary, confidence = mark("support_question", "high", "Gutenberg help-request type label.")
        elif "[type] regression" in label_text or "[type] bug" in label_text:
            primary, confidence = mark("bug", "high", "Gutenberg bug/regression type label.")
        elif "[type] enhancement" in label_text:
            primary, confidence = mark("enhancement", "high", "Gutenberg enhancement type label.")
        elif "[type] task" in label_text or "tracking issue" in title or title.startswith("tracking:"):
            primary, confidence = mark("task_maintenance", "high", "Gutenberg task/tracking signal.")
        else:
            if has_any(text, ["bug", "error", "crash", "broken", "regression", "expected", "actual"]):
                primary, confidence = mark("bug", "medium", "Bug-like language in title/body/comments.")
            elif has_any(text, ["feature request", "proposal", "add support", "new feature", "allow users", "ability to"]):
                primary, confidence = mark("feature_request", "medium", "Feature-request language in title/body/comments.")
            elif has_any(text, ["enhancement", "improve", "better", "polish"]):
                primary, confidence = mark("enhancement", "medium", "Enhancement language in title/body/comments.")
            elif has_any(text, ["documentation", "docs", "readme", "handbook"]):
                primary, confidence = mark("documentation", "medium", "Documentation language in title/body/comments.")
            else:
                primary, confidence = mark("other", "low", "No clear type label or strong text signal.")

    facet_rules = [
        ("accessibility", ["accessibility", "a11y", "aria", "screen reader", "keyboard navigation"]),
        ("performance", ["performance", "slow", "latency", "cache", "query performance"]),
        ("security", ["security", "xss", "csrf", "vulnerability", "sanitize", "escape"]),
        ("regression", ["regression", "backward compatibility", "breaks existing"]),
        ("duplicate", ["duplicate", "duplicated"]),
        ("stale", ["stale", "no activity"]),
        ("needs_info", ["needs more info", "reporter-feedback", "needs-testing", "needs testing"]),
        ("has_patch", ["has-patch", "has patch", "pull request", "commit"]),
    ]
    for facet, patterns in facet_rules:
        if has_any(f"{label_text} {text} {component} {resolution}", patterns):
            secondary.append(facet)

    if primary == "other" and "accessibility" in secondary:
        primary, confidence = "accessibility", "medium"
        reasons.append("No type category; accessibility is the strongest signal.")
    if primary == "other" and "performance" in secondary:
        primary, confidence = "performance", "medium"
        reasons.append("No type category; performance is the strongest signal.")
    if primary == "other" and "security" in secondary:
        primary, confidence = "security", "medium"
        reasons.append("No type category; security is the strongest signal.")

    evidence["reasons"] = reasons
    evidence["text_hash"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    conn.execute(
        """
        INSERT OR REPLACE INTO ticket_classifications(
          source,ticket_id,primary_category,secondary_categories_json,confidence,evidence_json,
          classifier_version,method,shard,classified_by,classified_at
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            source,
            ticket_id,
            primary,
            json_dumps(sorted(set(secondary))),
            confidence,
            json_dumps(evidence),
            CLASSIFIER_VERSION,
            "rules_with_full_text",
            shard,
            classified_by,
            now_iso(),
        ),
    )


def classify_shard(shard, shards, agent="local", force=False, batch=1000):
    conn = connect()
    if force:
        conn.execute(
            """
            DELETE FROM ticket_classifications
            WHERE (abs(CAST(ticket_id AS INTEGER)) % ?) = ?
            """,
            (shards, shard),
        )
        conn.commit()
    rows = conn.execute(
        """
        SELECT source, ticket_id FROM tickets
        WHERE (abs(CAST(ticket_id AS INTEGER)) % ?) = ?
          AND (? OR NOT EXISTS (
            SELECT 1 FROM ticket_classifications c
            WHERE c.source=tickets.source AND c.ticket_id=tickets.ticket_id
              AND c.classifier_version=?
          ))
        ORDER BY source, CAST(ticket_id AS INTEGER)
        """,
        (shards, shard, 1 if force else 0, CLASSIFIER_VERSION),
    ).fetchall()
    total = len(rows)
    for idx, row in enumerate(rows, 1):
        classify_ticket(conn, row["source"], row["ticket_id"], shard=shard, classified_by=agent)
        if idx % batch == 0:
            conn.commit()
            eprint(f"classified shard {shard}/{shards}: {idx:,}/{total:,}")
    conn.commit()
    conn.close()
    eprint(f"classified shard {shard}/{shards}: {total:,}")


def classify_all(shards=10, force=False, workers=10):
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(classify_shard, shard, shards, f"process-{shard}", force) for shard in range(shards)]
        for future in concurrent.futures.as_completed(futures):
            future.result()


def quarter(value):
    parsed = parse_iso(value)
    if not parsed:
        return ""
    q = ((parsed.month - 1) // 3) + 1
    return f"{parsed.year}-Q{q}"


def load_summary(conn, source):
    rows = conn.execute(
        """
        SELECT primary_category, COUNT(*) count
        FROM ticket_classifications
        WHERE source=?
        GROUP BY primary_category
        """,
        (source,),
    ).fetchall()
    return {row["primary_category"]: row["count"] for row in rows}


def load_open_summary(conn, source):
    rows = conn.execute(
        """
        SELECT c.primary_category, COUNT(*) count
        FROM ticket_classifications c
        JOIN tickets t ON t.source=c.source AND t.ticket_id=c.ticket_id
        WHERE c.source=? AND t.state='open'
        GROUP BY c.primary_category
        """,
        (source,),
    ).fetchall()
    return {row["primary_category"]: row["count"] for row in rows}


def write_summary_csvs(conn):
    for source in ["gutenberg", "core"]:
        path = ROOT / f"classification_summary_{source}.csv"
        rows = conn.execute(
            """
            SELECT c.primary_category category,
                   COUNT(*) total,
                   SUM(CASE WHEN t.state='open' THEN 1 ELSE 0 END) open_count,
                   SUM(CASE WHEN c.confidence='high' THEN 1 ELSE 0 END) high_confidence,
                   SUM(CASE WHEN c.confidence='medium' THEN 1 ELSE 0 END) medium_confidence,
                   SUM(CASE WHEN c.confidence='low' THEN 1 ELSE 0 END) low_confidence
            FROM ticket_classifications c
            JOIN tickets t ON t.source=c.source AND t.ticket_id=c.ticket_id
            WHERE c.source=?
            GROUP BY c.primary_category
            ORDER BY total DESC
            """,
            (source,),
        ).fetchall()
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["category", "total", "open_count", "high_confidence", "medium_confidence", "low_confidence"])
            writer.writerows(rows)
    trend = ROOT / "classification_trend_quarterly.csv"
    rows = conn.execute(
        """
        SELECT t.source, c.primary_category, t.created_at
        FROM ticket_classifications c
        JOIN tickets t ON t.source=c.source AND t.ticket_id=c.ticket_id
        """
    ).fetchall()
    buckets = Counter()
    for row in rows:
        bucket = quarter(row["created_at"])
        if bucket:
            buckets[(row["source"], bucket, row["primary_category"])] += 1
    with trend.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "quarter", "category", "count"])
        for key, count in sorted(buckets.items()):
            writer.writerow([*key, count])


def esc(value):
    return html.escape(str(value))


def fmt(value):
    return f"{int(value):,}"


def pct(value, total):
    if not total:
        return "0%"
    return f"{(value / total) * 100:.0f}%"


def bar_chart(summary, title, note):
    rows = [(cat, summary.get(cat, 0)) for cat in PRIMARY_CATEGORIES if summary.get(cat, 0)]
    rows.sort(key=lambda item: item[1], reverse=True)
    max_v = max((v for _c, v in rows), default=1)
    width = 1120
    row_h = 34
    height = 112 + len(rows) * row_h
    left, right, top = 220, 44, 76
    plot_w = width - left - right
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        f'<text x="40" y="28" class="chart-title">{esc(title)}</text>',
        f'<text x="40" y="50" class="chart-note">{esc(note)}</text>',
    ]
    for idx, (cat, value) in enumerate(rows):
        y = top + idx * row_h
        bar_w = value * plot_w / max_v
        value_x = left + bar_w + 10
        value_anchor = "start"
        if bar_w > plot_w - 80:
            value_x = left + bar_w - 10
            value_anchor = "end"
        parts.append(f'<text x="{left - 14}" y="{y + 18}" text-anchor="end" class="bar-label">{esc(CATEGORY_LABELS[cat])}</text>')
        parts.append(f'<rect x="{left}" y="{y}" width="{plot_w}" height="20" fill="#e5e7eb" rx="3"/>')
        parts.append(f'<rect x="{left}" y="{y}" width="{bar_w:.1f}" height="20" fill="{CATEGORY_COLORS[cat]}" rx="3"/>')
        parts.append(f'<text x="{value_x:.1f}" y="{y + 15}" text-anchor="{value_anchor}" class="axis">{fmt(value)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def category_tiles(summary, open_summary):
    total = sum(summary.values())
    rows = [(cat, summary.get(cat, 0), open_summary.get(cat, 0)) for cat in PRIMARY_CATEGORIES if summary.get(cat, 0)]
    rows.sort(key=lambda item: item[1], reverse=True)
    parts = ['<div class="category-grid">']
    for cat, count, open_count in rows:
        parts.append(
            f"""
            <div class="category-tile" style="--accent:{CATEGORY_COLORS[cat]}">
              <div class="tile-top"><span class="swatch"></span><span>{esc(CATEGORY_LABELS[cat])}</span></div>
              <div class="tile-value">{fmt(count)}</div>
              <div class="tile-meta">{pct(count, total)} of all tickets · {fmt(open_count)} open</div>
            </div>
            """
        )
    parts.append("</div>")
    return "\n".join(parts)


def stacked_open_chart(total_summary, open_summary, title, note):
    rows = [(cat, total_summary.get(cat, 0), open_summary.get(cat, 0)) for cat in PRIMARY_CATEGORIES if total_summary.get(cat, 0)]
    rows.sort(key=lambda item: item[1], reverse=True)
    max_v = max((v for _c, v, _o in rows), default=1)
    width = 1120
    row_h = 34
    height = 112 + len(rows) * row_h
    left, right, top = 220, 44, 76
    plot_w = width - left - right
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        f'<text x="40" y="28" class="chart-title">{esc(title)}</text>',
        f'<text x="40" y="50" class="chart-note">{esc(note)}</text>',
    ]
    for idx, (cat, total, open_count) in enumerate(rows):
        y = top + idx * row_h
        total_w = total * plot_w / max_v
        open_w = open_count * plot_w / max_v
        value_x = left + total_w + 10
        value_anchor = "start"
        if total_w > plot_w - 210:
            value_x = left + total_w - 10
            value_anchor = "end"
        parts.append(f'<text x="{left - 14}" y="{y + 18}" text-anchor="end" class="bar-label">{esc(CATEGORY_LABELS[cat])}</text>')
        parts.append(f'<rect x="{left}" y="{y}" width="{total_w:.1f}" height="20" fill="#dbeafe" rx="3"/>')
        parts.append(f'<rect x="{left}" y="{y}" width="{open_w:.1f}" height="20" fill="{CATEGORY_COLORS[cat]}" rx="3"/>')
        parts.append(f'<text x="{value_x:.1f}" y="{y + 15}" text-anchor="{value_anchor}" class="axis">{fmt(open_count)} open / {fmt(total)} total</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def confidence_counts(conn):
    rows = conn.execute(
        "SELECT source, confidence, COUNT(*) count FROM ticket_classifications GROUP BY source, confidence"
    ).fetchall()
    data = defaultdict(dict)
    for row in rows:
        data[row["source"]][row["confidence"]] = row["count"]
    return data


def yearly_category_counts(conn, source):
    rows = conn.execute(
        """
        SELECT substr(t.created_at, 1, 4) year, c.primary_category, COUNT(*) count
        FROM ticket_classifications c
        JOIN tickets t ON t.source=c.source AND t.ticket_id=c.ticket_id
        WHERE t.source=? AND t.created_at IS NOT NULL AND t.created_at != ''
        GROUP BY year, c.primary_category
        ORDER BY year, c.primary_category
        """,
        (source,),
    ).fetchall()
    data = defaultdict(dict)
    for row in rows:
        year = row["year"]
        if not year or not year.isdigit():
            continue
        data[year][row["primary_category"]] = row["count"]
    return data


def stacked_year_chart(data, title, note):
    years = sorted(data)
    if not years:
        return ""
    cats = [cat for cat in PRIMARY_CATEGORIES if any(data[year].get(cat, 0) for year in years)]
    legend_rows = max(1, math.ceil(len(cats) / 5))
    totals = {year: sum(data[year].values()) for year in years}
    max_total = max(totals.values(), default=1)
    width = max(1120, 150 + len(years) * 34)
    plot_left, plot_right = 58, 34
    plot_top, plot_h = 92 + legend_rows * 22, 230
    plot_w = width - plot_left - plot_right
    height = plot_top + plot_h + 54
    step = plot_w / max(len(years), 1)
    bar_w = min(24, step * 0.72)
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        f'<text x="40" y="28" class="chart-title">{esc(title)}</text>',
        f'<text x="40" y="50" class="chart-note">{esc(note)}</text>',
    ]
    lx, ly = 40, 76
    for idx, cat in enumerate(cats):
        row = idx // 5
        col = idx % 5
        x = lx + col * 205
        y = ly + row * 20
        parts.append(f'<rect x="{x}" y="{y - 10}" width="10" height="10" fill="{CATEGORY_COLORS[cat]}" rx="2"/>')
        parts.append(f'<text x="{x + 16}" y="{y}" class="legend-label">{esc(CATEGORY_LABELS[cat])}</text>')
    axis_y = plot_top + plot_h
    parts.append(f'<line x1="{plot_left}" y1="{axis_y}" x2="{width - plot_right}" y2="{axis_y}" stroke="#cbd5e1" stroke-width="1"/>')
    for idx, year in enumerate(years):
        x = plot_left + idx * step + (step - bar_w) / 2
        y_cursor = axis_y
        for cat in cats:
            value = data[year].get(cat, 0)
            if not value:
                continue
            h = max(1, value * plot_h / max_total)
            y_cursor -= h
            parts.append(f'<rect x="{x:.1f}" y="{y_cursor:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{CATEGORY_COLORS[cat]}" rx="2"/>')
        show_label = len(years) <= 12 or idx % 2 == 0 or idx == len(years) - 1
        if show_label:
            parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{axis_y + 22}" text-anchor="middle" class="axis">{esc(year)}</text>')
    parts.append(f'<text x="{plot_left}" y="{plot_top - 10}" class="axis">{fmt(max_total)} tickets</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def discussion(summary, open_summary, source_name):
    rows = [(cat, summary.get(cat, 0), open_summary.get(cat, 0)) for cat in PRIMARY_CATEGORIES if summary.get(cat, 0)]
    rows.sort(key=lambda item: item[1], reverse=True)
    if not rows:
        return ""
    top = rows[:3]
    total = sum(summary.values())
    top_text = ", ".join(f"{CATEGORY_LABELS[cat].lower()} ({pct(count, total)})" for cat, count, _open in top)
    open_rows = sorted(rows, key=lambda item: item[2], reverse=True)[:3]
    open_text = ", ".join(f"{CATEGORY_LABELS[cat].lower()} ({fmt(open_count)} open)" for cat, _count, open_count in open_rows)
    return (
        f"<p>{esc(source_name)} is mainly concentrated in {esc(top_text)}.</p>"
        f"<p>The current open set is led by {esc(open_text)}.</p>"
    )


def generate_report():
    conn = connect()
    write_summary_csvs(conn)
    g_total = load_summary(conn, "gutenberg")
    c_total = load_summary(conn, "core")
    g_open = load_open_summary(conn, "gutenberg")
    c_open = load_open_summary(conn, "core")
    g_years = yearly_category_counts(conn, "gutenberg")
    c_years = yearly_category_counts(conn, "core")
    conf = confidence_counts(conn)
    counts = {
        source: conn.execute("SELECT COUNT(*) FROM tickets WHERE source=?", (source,)).fetchone()[0]
        for source in ["gutenberg", "core"]
    }
    classified = {
        source: conn.execute("SELECT COUNT(*) FROM ticket_classifications WHERE source=?", (source,)).fetchone()[0]
        for source in ["gutenberg", "core"]
    }
    comments = {
        source: conn.execute("SELECT COUNT(*) FROM ticket_comments WHERE source=?", (source,)).fetchone()[0]
        for source in ["gutenberg", "core"]
    }
    conn.close()
    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WordPress Ticket Classification</title>
  <style>
    :root {{ --bg:#f8fafc; --panel:#fff; --text:#172033; --muted:#5b6b7f; --line:#d8e0ea; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    main {{ max-width:1220px; margin:0 auto; padding:44px 24px 64px; }}
    h1 {{ margin:0 0 10px; font-size:clamp(32px,4vw,56px); line-height:1.03; letter-spacing:0; }}
    h2 {{ margin:34px 0 10px; font-size:25px; line-height:1.15; letter-spacing:0; }}
    .deck {{ margin:0; max-width:900px; color:#475569; font-size:18px; }}
    .metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:30px 0; }}
    .metric,.chart,.note,.discussion {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; }}
    .metric {{ padding:16px; min-height:126px; }}
    .metric-label {{ color:#64748b; font-size:12px; font-weight:800; text-transform:uppercase; letter-spacing:.04em; }}
    .metric-value {{ margin-top:8px; font-size:27px; line-height:1.15; font-weight:850; }}
    .metric-note {{ margin-top:8px; color:#64748b; font-size:13px; }}
    .source-band {{ margin-top:26px; }}
    .category-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin-top:14px; }}
    .category-tile {{ background:#fff; border:1px solid var(--line); border-top:5px solid var(--accent); border-radius:8px; padding:13px; min-height:118px; }}
    .tile-top {{ display:flex; align-items:center; gap:8px; min-height:34px; color:#334155; font-size:13px; font-weight:800; }}
    .swatch {{ width:10px; height:10px; background:var(--accent); border-radius:2px; flex:0 0 auto; }}
    .tile-value {{ margin-top:10px; font-size:26px; line-height:1; font-weight:850; color:#0f172a; }}
    .tile-meta {{ margin-top:8px; color:#64748b; font-size:13px; }}
    .chart {{ margin-top:18px; padding:18px; overflow-x:auto; overflow-y:hidden; }}
    svg {{ display:block; width:100%; height:auto; overflow:visible; }}
    .chart-title {{ font-size:23px; font-weight:850; fill:#0f172a; }}
    .chart-note {{ font-size:14px; fill:#53667f; }}
    .axis,.bar-label,.legend-label {{ font-size:12px; fill:#334155; }}
    .bar-label {{ font-weight:700; }}
    .discussion {{ margin-top:18px; padding:18px; display:grid; grid-template-columns:1fr 1fr; gap:18px; color:#475569; }}
    .discussion p {{ margin:0; }}
    .note {{ margin-top:22px; padding:18px; color:#475569; }}
    a {{ color:#1d4ed8; font-weight:800; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    code {{ background:#eef2f7; padding:2px 5px; border-radius:4px; overflow-wrap:anywhere; word-break:break-word; }}
    @media (max-width:860px) {{
      main {{ padding:30px 14px 48px; }}
      .metrics {{ grid-template-columns:1fr; }}
      .category-grid {{ grid-template-columns:1fr; }}
      .discussion {{ grid-template-columns:1fr; }}
      .chart {{ padding:12px; overflow:visible; }}
      .chart svg {{ width:100%; max-width:100%; }}
      .deck {{ font-size:16px; }}
    }}
  </style>
</head>
<body>
<main>
  <h1>WordPress ticket classification</h1>
  <p class="deck">Large-category classification for Gutenberg GitHub issues and WordPress Core Trac tickets, stored in a reusable SQLite database.</p>
  <section class="metrics">
    <div class="metric"><div class="metric-label">Gutenberg classified</div><div class="metric-value">{fmt(classified['gutenberg'])}</div><div class="metric-note">{fmt(comments['gutenberg'])} comments stored</div></div>
    <div class="metric"><div class="metric-label">Core classified</div><div class="metric-value">{fmt(classified['core'])}</div><div class="metric-note">{fmt(comments['core'])} comments stored</div></div>
    <div class="metric"><div class="metric-label">Gutenberg confidence</div><div class="metric-value">{fmt(conf['gutenberg'].get('high',0))} high</div><div class="metric-note">{fmt(conf['gutenberg'].get('low',0))} low-confidence rows</div></div>
    <div class="metric"><div class="metric-label">Core confidence</div><div class="metric-value">{fmt(conf['core'].get('high',0))} high</div><div class="metric-note">{fmt(conf['core'].get('low',0))} low-confidence rows</div></div>
  </section>
  <section class="source-band">
    <h2>Gutenberg GitHub issues</h2>
    {category_tiles(g_total, g_open)}
    <section class="chart">{stacked_year_chart(g_years, "Gutenberg category timeline", "Tickets created per year, split by primary category.")}</section>
    <section class="chart">{bar_chart(g_total, "Gutenberg issues by category", "Primary category across all cached WordPress/gutenberg issues.")}</section>
    <section class="chart">{stacked_open_chart(g_total, g_open, "Gutenberg open backlog by category", "Dark bars are currently open issues; pale bars are total issues in that category.")}</section>
    <section class="discussion">{discussion(g_total, g_open, "Gutenberg")}</section>
  </section>
  <section class="source-band">
    <h2>WordPress Core Trac tickets</h2>
    {category_tiles(c_total, c_open)}
    <section class="chart">{stacked_year_chart(c_years, "Core category timeline", "Tickets created per year since 2003, split by primary category.")}</section>
    <section class="chart">{bar_chart(c_total, "WordPress Core tickets by category", "Primary category across all Core Trac tickets in the database.")}</section>
    <section class="chart">{stacked_open_chart(c_total, c_open, "Core open backlog by category", "Dark bars are currently open tickets; pale bars are total tickets in that category.")}</section>
    <section class="discussion">{discussion(c_total, c_open, "Core")}</section>
  </section>
  <section class="note">
    <p>Local SQLite database: <code>{DB_PATH}</code>. Classification version: <code>{CLASSIFIER_VERSION}</code>.</p>
    <p>Published CSVs: <a href="classification_summary_gutenberg.csv">Gutenberg summary</a>, <a href="classification_summary_core.csv">Core summary</a>, <a href="classification_trend_quarterly.csv">category trend</a>.</p>
    <p>Core uses Trac type as the strongest signal. Gutenberg uses issue type labels first, then title/body/comment text. Secondary facets preserve accessibility, performance, security, duplicate, stale, needs-info, and has-patch signals.</p>
  </section>
</main>
</body>
</html>
"""
    OUT.write_text(html_text, encoding="utf-8")
    eprint(f"wrote {OUT}")


def status():
    conn = connect()
    for source in ["gutenberg", "core"]:
        total = conn.execute("SELECT COUNT(*) FROM tickets WHERE source=?", (source,)).fetchone()[0]
        bodies = conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE source=? AND body IS NOT NULL AND body != ''", (source,)
        ).fetchone()[0]
        comments = conn.execute("SELECT COUNT(*) FROM ticket_comments WHERE source=?", (source,)).fetchone()[0]
        classified = conn.execute("SELECT COUNT(*) FROM ticket_classifications WHERE source=?", (source,)).fetchone()[0]
        print(source, {"tickets": total, "bodies": bodies, "comments": comments, "classified": classified})
    conn.close()


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("ingest")
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--force", action="store_true")
    fetch.add_argument("--workers", type=int, default=8)
    fetch.add_argument("--limit", type=int)
    classify = sub.add_parser("classify")
    classify.add_argument("--shards", type=int, default=10)
    classify.add_argument("--shard", type=int)
    classify.add_argument("--workers", type=int, default=10)
    classify.add_argument("--agent", default="local")
    classify.add_argument("--force", action="store_true")
    sub.add_parser("report")
    sub.add_parser("status")
    args = parser.parse_args()
    ensure_dirs()
    if args.cmd == "init":
        init_db()
    elif args.cmd == "ingest":
        ingest_all()
    elif args.cmd == "fetch":
        fetch_all(args)
    elif args.cmd == "classify":
        if args.shard is not None:
            classify_shard(args.shard, args.shards, args.agent, force=args.force)
        else:
            classify_all(shards=args.shards, force=args.force, workers=args.workers)
    elif args.cmd == "report":
        generate_report()
    elif args.cmd == "status":
        status()


if __name__ == "__main__":
    main()
