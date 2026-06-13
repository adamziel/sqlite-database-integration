#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
GUT_ROOT = Path("/Users/admin/gutenberg_issue_analysis")
ISSUES_JSONL = GUT_ROOT / "raw" / "issues_inventory.jsonl"
CACHE = ROOT / "cache" / "gutenberg_timeline_graphql"
OUT_JSONL = ROOT / "gutenberg_issue_timeline_metrics.jsonl"
OUT_QUARTERLY = ROOT / "gutenberg_timeline_quarterly.csv"

OWNER = "WordPress"
REPO = "gutenberg"
END = dt.datetime(2026, 6, 11, 23, 59, 59, tzinfo=dt.timezone.utc)
UA = "codex-gutenberg-timeline-metrics/1.0"
GRAPHQL_URL = "https://api.github.com/graphql"
MAINTAINER_ASSOCIATIONS = {"MEMBER", "OWNER", "COLLABORATOR"}

PAGE_QUERY = """
query($owner:String!, $repo:String!, $after:String) {
  repository(owner:$owner, name:$repo) {
    issues(first: 100, after:$after, orderBy:{field:CREATED_AT, direction:ASC}) {
      nodes {
        number
        createdAt
        updatedAt
        closedAt
        state
        author { login }
        comments(first: 100) {
          totalCount
          pageInfo { hasNextPage endCursor }
          nodes {
            createdAt
            author { login }
            authorAssociation
          }
        }
        timelineItems(first: 100, itemTypes:[REOPENED_EVENT]) {
          totalCount
          pageInfo { hasNextPage endCursor }
          nodes {
            __typename
            ... on ReopenedEvent {
              createdAt
              actor { login }
            }
          }
        }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
  rateLimit { cost remaining resetAt }
}
"""

COMMENTS_QUERY = """
query($owner:String!, $repo:String!, $number:Int!, $after:String) {
  repository(owner:$owner, name:$repo) {
    issue(number:$number) {
      comments(first: 100, after:$after) {
        totalCount
        pageInfo { hasNextPage endCursor }
        nodes {
          createdAt
          author { login }
          authorAssociation
        }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
"""


def eprint(message):
    print(message, file=sys.stderr, flush=True)


def parse_dt(value):
    if not value:
        return None
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def hours_between(start, end):
    if not start or not end:
        return ""
    return round((end - start).total_seconds() / 3600, 2)


def quarter_start(value):
    if isinstance(value, str):
        value = parse_dt(value)
    month = ((value.month - 1) // 3) * 3 + 1
    return f"{value.year:04d}-{month:02d}-01"


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
    username = ""
    token = ""
    for line in proc.stdout.splitlines():
        if line.startswith("username="):
            username = line.split("=", 1)[1]
        elif line.startswith("password="):
            token = line.split("=", 1)[1]
    return username, token


class GitHubGraphQL:
    def __init__(self):
        self.username, self.token = credential_from_git()
        if not self.token:
            raise RuntimeError("No GitHub token available from git credential helper.")

    def request(self, query, variables):
        body = json.dumps({"query": query, "variables": variables}, sort_keys=True).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": UA,
        }
        while True:
            req = urllib.request.Request(GRAPHQL_URL, data=body, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code in (403, 429):
                    reset = int(exc.headers.get("X-RateLimit-Reset", "0") or 0)
                    sleep_for = max(30, reset - int(time.time()) + 5)
                    eprint(f"GitHub throttle pause {sleep_for}s")
                    time.sleep(sleep_for)
                    continue
                body_text = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"GitHub GraphQL HTTP {exc.code}: {body_text}") from exc
            if payload.get("errors"):
                raise RuntimeError(json.dumps(payload["errors"], ensure_ascii=True))
            rate = (payload.get("data") or {}).get("rateLimit") or {}
            remaining = int(rate.get("remaining") or 0)
            if remaining and remaining < 50:
                reset_at = parse_dt(rate.get("resetAt"))
                sleep_for = max(10, int((reset_at - dt.datetime.now(dt.timezone.utc)).total_seconds()) + 5) if reset_at else 60
                eprint(f"GitHub rate-limit pause {sleep_for}s")
                time.sleep(sleep_for)
            return payload


def load_inventory_numbers():
    numbers = set()
    with ISSUES_JSONL.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                issue = json.loads(line)
                created = parse_dt(issue.get("created_at"))
                if created and created <= END:
                    numbers.add(int(issue["number"]))
    return numbers


def page_cache_path(index):
    return CACHE / f"issues-page-{index:04d}.json"


def comment_cache_path(number):
    return CACHE / "comments" / f"issue-{int(number)}.jsonl"


def fetch_issue_pages(client, inventory_numbers, force=False, limit_pages=None):
    CACHE.mkdir(parents=True, exist_ok=True)
    after = None
    page = 1
    fetched = 0
    while True:
        cache_path = page_cache_path(page)
        if cache_path.exists() and not force:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            payload = client.request(PAGE_QUERY, {"owner": OWNER, "repo": REPO, "after": after})
            cache_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            fetched += 1
        issues = (((payload.get("data") or {}).get("repository") or {}).get("issues") or {})
        nodes = issues.get("nodes") or []
        if not nodes:
            break
        latest_created = max((parse_dt(node.get("createdAt")) for node in nodes if node.get("createdAt")), default=None)
        eprint(
            f"issue page {page}: {len(nodes)} issues, through "
            f"{latest_created.date().isoformat() if latest_created else 'unknown'}"
        )
        page_info = issues.get("pageInfo") or {}
        after = page_info.get("endCursor")
        if latest_created and latest_created > END:
            break
        if limit_pages and page >= limit_pages:
            break
        if not page_info.get("hasNextPage"):
            break
        page += 1
    eprint(f"fetched {fetched} new GraphQL issue pages")


def read_cached_issue_nodes():
    nodes = []
    for path in sorted(CACHE.glob("issues-page-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        issue_conn = (((payload.get("data") or {}).get("repository") or {}).get("issues") or {})
        for node in issue_conn.get("nodes") or []:
            created = parse_dt(node.get("createdAt"))
            if created and created <= END:
                nodes.append(node)
    by_number = {}
    for node in nodes:
        by_number[int(node["number"])] = node
    return [by_number[number] for number in sorted(by_number)]


def first_responses(created_at, author_login, comments):
    first_comment_at = None
    first_non_author_at = None
    first_maintainer_at = None
    author_login = (author_login or "").lower()
    for comment in sorted(comments, key=lambda row: row.get("createdAt") or ""):
        comment_at = parse_dt(comment.get("createdAt"))
        if not comment_at:
            continue
        login = (((comment.get("author") or {}).get("login")) or "").lower()
        assoc = comment.get("authorAssociation") or ""
        if first_comment_at is None:
            first_comment_at = comment_at
        if login and login != author_login and first_non_author_at is None:
            first_non_author_at = comment_at
        if login and login != author_login and assoc in MAINTAINER_ASSOCIATIONS and first_maintainer_at is None:
            first_maintainer_at = comment_at
    return {
        "first_comment_at": first_comment_at,
        "first_non_author_response_at": first_non_author_at,
        "first_maintainer_response_at": first_maintainer_at,
        "first_comment_hours": hours_between(created_at, first_comment_at),
        "first_non_author_response_hours": hours_between(created_at, first_non_author_at),
        "first_maintainer_response_hours": hours_between(created_at, first_maintainer_at),
    }


def needs_more_comments(node, metrics):
    comments = node.get("comments") or {}
    return bool((comments.get("pageInfo") or {}).get("hasNextPage"))


def fetch_extra_comments(client, node, force=False):
    number = int(node["number"])
    out = comment_cache_path(number)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not force:
        rows = []
        with out.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        return rows
    rows = []
    after = ((node.get("comments") or {}).get("pageInfo") or {}).get("endCursor")
    page = 2
    while after:
        payload = client.request(COMMENTS_QUERY, {"owner": OWNER, "repo": REPO, "number": number, "after": after})
        comments = ((((payload.get("data") or {}).get("repository") or {}).get("issue") or {}).get("comments") or {})
        nodes = comments.get("nodes") or []
        rows.extend(nodes)
        page_info = comments.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")
        page += 1
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    eprint(f"extra comments issue {number}: {len(rows)} rows")
    return rows


def build_issue_metrics(client, force_comment_pages=False):
    rows = []
    nodes = read_cached_issue_nodes()
    for index, node in enumerate(nodes, 1):
        created_at = parse_dt(node.get("createdAt"))
        author_login = ((node.get("author") or {}).get("login")) or ""
        comments_conn = node.get("comments") or {}
        comments = list(comments_conn.get("nodes") or [])
        response = first_responses(created_at, author_login, comments)
        if needs_more_comments(node, response):
            comments.extend(fetch_extra_comments(client, node, force=force_comment_pages))
            response = first_responses(created_at, author_login, comments)
        reopen_conn = node.get("timelineItems") or {}
        reopen_nodes = [
            event for event in reopen_conn.get("nodes") or []
            if event.get("__typename") == "ReopenedEvent" and event.get("createdAt")
        ]
        reopen_dates = sorted(parse_dt(event.get("createdAt")) for event in reopen_nodes if event.get("createdAt"))
        comments_complete = not (comments_conn.get("pageInfo") or {}).get("hasNextPage") or bool(
            comment_cache_path(node["number"]).exists()
        )
        row = {
            "number": node["number"],
            "created_at": node.get("createdAt") or "",
            "closed_at": node.get("closedAt") or "",
            "state": node.get("state") or "",
            "author_login": author_login,
            "comment_count": comments_conn.get("totalCount") or 0,
            "comments_fetched": len(comments),
            "comments_complete": int(comments_complete),
            "comments_truncated": int((comments_conn.get("pageInfo") or {}).get("hasNextPage") and not comments_complete),
            "reopened_event_count": reopen_conn.get("totalCount") or 0,
            "reopened_events_fetched": len(reopen_nodes),
            "reopened_events_truncated": int((reopen_conn.get("pageInfo") or {}).get("hasNextPage") or False),
            "first_reopened_at": reopen_dates[0].isoformat().replace("+00:00", "Z") if reopen_dates else "",
            "last_reopened_at": reopen_dates[-1].isoformat().replace("+00:00", "Z") if reopen_dates else "",
            "source_url": f"https://github.com/{OWNER}/{REPO}/issues/{node['number']}",
        }
        for key, value in response.items():
            if isinstance(value, dt.datetime):
                row[key] = value.isoformat().replace("+00:00", "Z")
            elif value is None:
                row[key] = ""
            else:
                row[key] = value
        rows.append(row)
        if index % 5000 == 0:
            eprint(f"processed {index:,}/{len(nodes):,} issue metrics")
    return rows


def median(values):
    values = sorted(v for v in values if v not in ("", None))
    if not values:
        return ""
    mid = len(values) // 2
    if len(values) % 2:
        return round(values[mid], 2)
    return round((values[mid - 1] + values[mid]) / 2, 2)


def build_quarterly(metrics):
    by_created = defaultdict(list)
    by_closed = defaultdict(list)
    by_reopened = defaultdict(list)
    for row in metrics:
        created = parse_dt(row.get("created_at"))
        closed = parse_dt(row.get("closed_at"))
        if created:
            by_created[quarter_start(created)].append(row)
        if closed:
            by_closed[quarter_start(closed)].append(row)
        first_reopen = parse_dt(row.get("first_reopened_at"))
        if first_reopen:
            by_reopened[quarter_start(first_reopen)].append(row)
    quarters = sorted(set(by_created) | set(by_closed) | set(by_reopened))
    rows = []
    for q in quarters:
        created_rows = by_created.get(q, [])
        closed_rows = by_closed.get(q, [])
        reopened_rows = by_reopened.get(q, [])
        response_hours = [float(row["first_non_author_response_hours"]) for row in created_rows if row.get("first_non_author_response_hours") != ""]
        maintainer_hours = [float(row["first_maintainer_response_hours"]) for row in created_rows if row.get("first_maintainer_response_hours") != ""]
        reopened_events = sum(int(row.get("reopened_event_count") or 0) for row in reopened_rows)
        closed_count = len(closed_rows)
        rows.append(
            {
                "quarter": q,
                "issues_created": len(created_rows),
                "issues_closed": closed_count,
                "issues_with_first_non_author_response": len(response_hours),
                "issues_with_first_maintainer_response": len(maintainer_hours),
                "issues_without_first_non_author_response": len(created_rows) - len(response_hours),
                "median_first_non_author_response_hours": median(response_hours),
                "median_first_maintainer_response_hours": median(maintainer_hours),
                "reopened_issues": len(reopened_rows),
                "reopened_events": reopened_events,
                "reopened_events_per_100_closed": round(reopened_events / closed_count * 100, 2) if closed_count else 0,
                "comment_truncated_issue_count": sum(int(row.get("comments_truncated") or 0) for row in created_rows),
                "reopen_truncated_issue_count": sum(int(row.get("reopened_events_truncated") or 0) for row in created_rows),
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
    parser.add_argument("--force-pages", action="store_true", help="Refetch cached issue GraphQL pages.")
    parser.add_argument("--force-comment-pages", action="store_true", help="Refetch cached extra comment pages.")
    parser.add_argument("--limit-pages", type=int, help="Fetch only the first N issue pages for testing.")
    args = parser.parse_args()

    ROOT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    inventory_numbers = load_inventory_numbers()
    client = GitHubGraphQL()
    eprint(f"authenticated as {client.username or 'unknown'}; inventory issues {len(inventory_numbers):,}")
    fetch_issue_pages(client, inventory_numbers, force=args.force_pages, limit_pages=args.limit_pages)
    metrics = build_issue_metrics(client, force_comment_pages=args.force_comment_pages)
    metrics = [row for row in metrics if int(row["number"]) in inventory_numbers]
    if args.limit_pages:
        metrics = metrics[: args.limit_pages * 100]
    quarterly = build_quarterly(metrics)
    write_jsonl(OUT_JSONL, metrics)
    write_csv(OUT_QUARTERLY, quarterly)
    eprint(f"wrote {len(metrics):,} issue metrics to {OUT_JSONL}")
    eprint(f"wrote {len(quarterly):,} quarterly rows to {OUT_QUARTERLY}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
