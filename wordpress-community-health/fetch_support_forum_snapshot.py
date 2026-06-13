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
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
CACHE = ROOT / "cache" / "support_forum_views"
TOPICS_OUT = ROOT / "support_forum_topics.jsonl"
VIEWS_OUT = ROOT / "support_forum_view_snapshots.csv"
FORUMS_OUT = ROOT / "support_forum_forum_summary.csv"
UA = "codex-wordpress-community-health/1.0"
COLLECTED_AT = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

VIEWS = {
    "all_topics": {
        "label": "Recent support topics",
        "url": "https://wordpress.org/support/view/all-topics/",
        "queue": "all",
    },
    "resolved": {
        "label": "Resolved topics",
        "url": "https://wordpress.org/support/view/support-forum-yes/",
        "queue": "resolved",
    },
    "unresolved": {
        "label": "Unresolved topics",
        "url": "https://wordpress.org/support/view/support-forum-no/",
        "queue": "unresolved",
    },
    "no_replies": {
        "label": "Topics with no replies",
        "url": "https://wordpress.org/support/view/no-replies/",
        "queue": "no_replies",
    },
}


def eprint(message):
    print(message, file=sys.stderr, flush=True)


def clean_text(value):
    value = html.unescape(value or "")
    return re.sub(r"\s+", " ", value).strip()


def int_text(value):
    value = re.sub(r"[^\d]", "", value or "")
    return int(value) if value else 0


def cache_path(view, page):
    return CACHE / view / f"page-{page:04d}.html"


def page_url(base_url, page):
    if page == 1:
        return base_url
    return base_url.rstrip("/") + f"/page/{page}/"


def fetch_url(url, cache_file, force=False):
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    if cache_file.exists() and not force:
        return cache_file.read_text(encoding="utf-8", errors="replace"), "cached"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            cache_file.write_text(body, encoding="utf-8")
            return body, "fetched"
        except urllib.error.HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt < 4:
                time.sleep(2 + attempt * 3)
                continue
            raise
        except Exception:
            if attempt < 4:
                time.sleep(2 + attempt * 3)
                continue
            raise
    raise RuntimeError(f"failed to fetch {url}")


class SupportViewParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.max_page = 1
        self.topics = []
        self._in_topic = False
        self._topic = None
        self._class_stack = []
        self._current = None
        self._text = []
        self._last_anchor = None

    def _classes(self, attrs):
        return set(dict(attrs).get("class", "").split())

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        classes = self._classes(attrs)
        if tag == "ul" and any(c.startswith("post-") for c in classes) and "topic" in classes:
            topic_id = next((c[5:] for c in classes if c.startswith("post-")), "")
            self._in_topic = True
            self._topic = {
                "topic_id": topic_id,
                "title": "",
                "url": "",
                "resolved_badge": "0",
                "starter_name": "",
                "starter_slug": "",
                "forum_name": "",
                "forum_url": "",
                "participants": "0",
                "replies": "0",
                "last_activity_at": "",
                "last_activity_label": "",
                "last_author_name": "",
                "last_author_slug": "",
            }
        if tag == "a":
            href = attrs_dict.get("href", "")
            match = re.search(r"/page/(\d+)/", href)
            if match:
                self.max_page = max(self.max_page, int(match.group(1)))
        if not self._in_topic:
            return
        if "bbp-topic-permalink" in classes:
            self._current = "title"
            self._text = []
            self._topic["url"] = attrs_dict.get("href", "")
        elif "resolved" in classes:
            self._topic["resolved_badge"] = "1"
        elif "bbp-topic-started-by" in classes:
            self._current = "starter_block"
            self._text = []
        elif "bbp-topic-started-in" in classes:
            self._current = "forum_block"
            self._text = []
        elif "bbp-topic-voice-count" in classes:
            self._current = "participants"
            self._text = []
        elif "bbp-topic-reply-count" in classes:
            self._current = "replies"
            self._text = []
        elif "bbp-topic-freshness-author" in classes:
            self._current = "last_author_block"
            self._text = []
        if tag == "a" and self._current in {"starter_block", "forum_block", "last_author_block"}:
            self._last_anchor = attrs_dict.get("href", "")
        if tag == "a" and self._current is None and self._topic is not None:
            href = attrs_dict.get("href", "")
            title = attrs_dict.get("title", "")
            if "#post-" in href and title:
                self._current = "last_activity"
                self._text = []
                self._topic["last_activity_at"] = parse_forum_datetime(title)

    def handle_endtag(self, tag):
        if not self._in_topic:
            return
        if self._current and tag in {"a", "span", "li"}:
            value = clean_text("".join(self._text))
            if self._current == "title" and tag == "a":
                self._topic["title"] = value
                self._current = None
            elif self._current == "starter_block" and tag == "span":
                self._topic["starter_name"] = value.replace("Started by:", "").strip()
                self._topic["starter_slug"] = slug_from_user_url(self._last_anchor)
                self._current = None
                self._last_anchor = None
            elif self._current == "forum_block" and tag == "span":
                self._topic["forum_name"] = value.replace("in:", "").strip()
                self._topic["forum_url"] = self._last_anchor or ""
                self._current = None
                self._last_anchor = None
            elif self._current == "participants" and tag == "li":
                self._topic["participants"] = str(int_text(value))
                self._current = None
            elif self._current == "replies" and tag == "li":
                self._topic["replies"] = str(int_text(value))
                self._current = None
            elif self._current == "last_activity" and tag == "a":
                self._topic["last_activity_label"] = value
                self._current = None
            elif self._current == "last_author_block" and tag == "span":
                self._topic["last_author_name"] = value
                self._topic["last_author_slug"] = slug_from_user_url(self._last_anchor)
                self._current = None
                self._last_anchor = None
        if tag == "ul" and self._topic is not None:
            if self._topic.get("url"):
                self.topics.append(self._topic)
            self._topic = None
            self._in_topic = False
            self._current = None
            self._text = []
            self._last_anchor = None

    def handle_data(self, data):
        if self._current:
            self._text.append(data)

    def handle_entityref(self, name):
        if self._current:
            self._text.append(f"&{name};")

    def handle_charref(self, name):
        if self._current:
            self._text.append(f"&#{name};")


def slug_from_user_url(url):
    match = re.search(r"/support/users/([^/]+)/", url or "")
    return match.group(1) if match else ""


def parse_forum_datetime(value):
    value = clean_text(value)
    for fmt in ("%B %d, %Y at %I:%M %p", "%b %d, %Y at %I:%M %p"):
        try:
            parsed = dt.datetime.strptime(value, fmt).replace(tzinfo=dt.timezone.utc)
            return parsed.isoformat().replace("+00:00", "Z")
        except ValueError:
            continue
    return ""


def parse_page(body):
    parser = SupportViewParser()
    parser.feed(body)
    parser.close()
    return parser.max_page, parser.topics


def merge_topic(existing, row, view_name):
    existing["views"].add(view_name)
    existing["source_pages"].add(row["source_page"])
    for key, value in row.items():
        if key in {"views", "source_pages"}:
            continue
        if value and not existing.get(key):
            existing[key] = value
    if row.get("last_activity_at") and row.get("last_activity_at", "") > existing.get("last_activity_at", ""):
        existing["last_activity_at"] = row["last_activity_at"]
        existing["last_activity_label"] = row.get("last_activity_label", existing.get("last_activity_label", ""))
        existing["last_author_name"] = row.get("last_author_name", existing.get("last_author_name", ""))
        existing["last_author_slug"] = row.get("last_author_slug", existing.get("last_author_slug", ""))


def collect(force=False, max_pages=None, sleep=0.2):
    all_occurrences = []
    view_rows = []
    by_topic = {}
    for view_name, view in VIEWS.items():
        body, status = fetch_url(view["url"], cache_path(view_name, 1), force=force)
        max_page, topics = parse_page(body)
        if max_pages:
            max_page = min(max_page, max_pages)
        page_statuses = {status: 1}
        view_topics = []
        for page in range(1, max_page + 1):
            if page == 1:
                page_topics = topics
            else:
                url = page_url(view["url"], page)
                body, status = fetch_url(url, cache_path(view_name, page), force=force)
                page_statuses[status] = page_statuses.get(status, 0) + 1
                _max_page, page_topics = parse_page(body)
                time.sleep(sleep)
            for topic in page_topics:
                row = dict(topic)
                row.update(
                    {
                        "view": view_name,
                        "view_label": view["label"],
                        "queue": view["queue"],
                        "source_page": str(page),
                        "source_url": page_url(view["url"], page),
                        "collected_at": COLLECTED_AT,
                    }
                )
                all_occurrences.append(row)
                view_topics.append(row)
                topic_id = row.get("topic_id") or row.get("url")
                if topic_id not in by_topic:
                    by_topic[topic_id] = dict(row)
                    by_topic[topic_id]["views"] = {view_name}
                    by_topic[topic_id]["source_pages"] = {str(page)}
                else:
                    merge_topic(by_topic[topic_id], row, view_name)
        unique_urls = {row.get("url") for row in view_topics if row.get("url")}
        dates = sorted(row.get("last_activity_at", "") for row in view_topics if row.get("last_activity_at"))
        view_rows.append(
            {
                "collected_at": COLLECTED_AT,
                "view": view_name,
                "label": view["label"],
                "queue": view["queue"],
                "pages_discovered": str(max_page),
                "pages_fetched": str(max_page),
                "topics_seen": str(len(view_topics)),
                "unique_topics": str(len(unique_urls)),
                "latest_activity_at": dates[-1] if dates else "",
                "oldest_activity_at": dates[0] if dates else "",
                "total_replies": str(sum(int_text(row.get("replies")) for row in view_topics)),
                "fetch_statuses": json.dumps(page_statuses, sort_keys=True),
                "source_url": view["url"],
            }
        )
        eprint(f"{view_name}: {len(view_topics)} topics across {max_page} pages")
    topic_rows = []
    for row in by_topic.values():
        views = sorted(row.pop("views"))
        source_pages = sorted(row.pop("source_pages"), key=lambda value: int_text(value))
        resolved = "1" if "resolved" in views or row.get("resolved_badge") == "1" else "0"
        no_replies = "1" if "no_replies" in views or int_text(row.get("replies")) == 0 else "0"
        unresolved = "1" if "unresolved" in views and resolved != "1" else "0"
        row.update(
            {
                "views": ",".join(views),
                "source_pages": ",".join(source_pages),
                "is_resolved": resolved,
                "is_unresolved": unresolved,
                "has_no_replies": no_replies,
                "collected_at": COLLECTED_AT,
            }
        )
        topic_rows.append(row)
    topic_rows.sort(key=lambda row: (row.get("last_activity_at", ""), row.get("topic_id", "")), reverse=True)
    forum_rows = summarize_forums(topic_rows)
    return topic_rows, view_rows, forum_rows


def summarize_forums(topic_rows):
    buckets = defaultdict(lambda: {"topics": 0, "resolved": 0, "unresolved": 0, "no_replies": 0, "replies": 0, "participants": 0})
    for row in topic_rows:
        forum = row.get("forum_name") or "(unknown forum)"
        bucket = buckets[forum]
        bucket["topics"] += 1
        bucket["resolved"] += int_text(row.get("is_resolved"))
        bucket["unresolved"] += int_text(row.get("is_unresolved"))
        bucket["no_replies"] += int_text(row.get("has_no_replies"))
        bucket["replies"] += int_text(row.get("replies"))
        bucket["participants"] += int_text(row.get("participants"))
    rows = []
    for forum, values in sorted(buckets.items(), key=lambda item: (-item[1]["topics"], item[0])):
        topics = values["topics"]
        rows.append(
            {
                "collected_at": COLLECTED_AT,
                "forum_name": forum,
                "topics": str(topics),
                "resolved_topics": str(values["resolved"]),
                "unresolved_topics": str(values["unresolved"]),
                "no_reply_topics": str(values["no_replies"]),
                "resolution_share_percent": f"{(values['resolved'] / topics * 100) if topics else 0:.1f}",
                "no_reply_share_percent": f"{(values['no_replies'] / topics * 100) if topics else 0:.1f}",
                "total_replies": str(values["replies"]),
                "avg_replies": f"{(values['replies'] / topics) if topics else 0:.2f}",
                "avg_participants": f"{(values['participants'] / topics) if topics else 0:.2f}",
            }
        )
    return rows


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def write_csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Refetch cached support view pages.")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit pages per view for smoke tests.")
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between uncached page fetches.")
    args = parser.parse_args()

    ROOT.mkdir(parents=True, exist_ok=True)
    topic_rows, view_rows, forum_rows = collect(force=args.force, max_pages=args.max_pages, sleep=args.sleep)
    write_jsonl(TOPICS_OUT, topic_rows)
    write_csv(VIEWS_OUT, view_rows)
    write_csv(FORUMS_OUT, forum_rows)
    eprint(f"wrote {len(topic_rows)} unique topics to {TOPICS_OUT}")
    eprint(f"wrote {len(view_rows)} view rows to {VIEWS_OUT}")
    eprint(f"wrote {len(forum_rows)} forum rows to {FORUMS_OUT}")


if __name__ == "__main__":
    main()
