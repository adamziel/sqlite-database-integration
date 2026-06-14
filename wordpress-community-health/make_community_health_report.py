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
    "core_response_metrics": ROOT / "core_response_metrics.jsonl",
    "core_response_quarterly": ROOT / "core_response_quarterly.csv",
    "github_pr_quarterly": CORE_ROOT / "github_pr_quarterly.csv",
    "github_prs": CORE_ROOT / "raw" / "github_wordpress_develop_prs.jsonl",
    "gutenberg_quarterly": GUT_ROOT / "quarterly_metrics.csv",
    "gutenberg_issues": GUT_ROOT / "issues_inventory.csv",
    "gutenberg_issues_jsonl": GUT_ROOT / "raw" / "issues_inventory.jsonl",
    "gutenberg_timeline_metrics": ROOT / "gutenberg_issue_timeline_metrics.jsonl",
    "gutenberg_timeline_quarterly": ROOT / "gutenberg_timeline_quarterly.csv",
    "classification_trend": CLASS_ROOT / "classification_trend_quarterly.csv",
    "classification_summary_core": CLASS_ROOT / "classification_summary_core.csv",
    "classification_summary_gutenberg": CLASS_ROOT / "classification_summary_gutenberg.csv",
    "support_forum_topics": ROOT / "support_forum_topics.jsonl",
    "support_forum_view_snapshots": ROOT / "support_forum_view_snapshots.csv",
    "support_forum_forum_summary": ROOT / "support_forum_forum_summary.csv",
    "builtwith_new_site_snapshot": ROOT / "builtwith_new_site_snapshot.csv",
}

SKIP_NETWORK_DB_FALLBACK_TABLES = [
    "market_share",
    "http_archive_adoption_monthly",
    "http_archive_tracked_share_monthly",
    "http_archive_rank_adoption_snapshot",
    "http_archive_cwv_monthly",
    "wporg_ecosystem_stats_snapshot",
    "wikimedia_pageviews_monthly",
    "wikimedia_pageviews_quarterly",
    "hn_hiring_wordpress_quarterly",
    "wordpress_jobs_board_snapshots",
    "wordpress_jobs_board_category_snapshots",
    "attention_demand_summary",
    "enterprise_vip_case_studies",
    "builtwith_technology_snapshots",
    "builtwith_technology_history",
    "new_site_choice_summary",
    "directory_snapshots",
    "directory_activity_snapshots",
    "plugin_directory_activity_sample",
    "plugin_maintenance_summary",
    "plugin_stale_popular_sample",
    "major_plugin_install_snapshot",
    "major_plugin_install_history",
    "major_plugin_download_daily",
    "major_plugin_download_quarterly",
    "theme_directory_activity_sample",
    "wordcamps",
    "wordcamp_yearly",
    "wp_event_snapshots",
    "wp_events",
    "translation_snapshots",
    "translation_locale_snapshot",
    "translation_core_dev_status",
    "make_core_posts",
    "make_core_comments",
    "make_core_comment_quarterly",
    "make_core_dev_note_tags",
    "make_core_dev_notes",
    "make_core_dev_note_quarterly",
    "make_core_dev_note_releases",
    "fttf_snapshots",
    "fttf_pledges",
    "fttf_contributors",
    "core_releases",
    "core_release_credits",
    "core_release_committers",
    "core_release_committer_counts",
]

W3TECHS_USAGE_URL = "https://w3techs.com/technologies/history_overview/content_management/all/y"
W3TECHS_MARKET_SHARE_URL = "https://w3techs.com/technologies/history_overview/content_management/ms/y"
HTTP_ARCHIVE_CMS_URL = "https://almanac.httparchive.org/en/2025/cms"
HTTP_ARCHIVE_TECH_REPORT_URL = "https://httparchive.org/reports/techreport/tech"
HTTP_ARCHIVE_API_BASE = "https://cdn.httparchive.org/v1"
HTTP_ARCHIVE_ADOPTION_TECHNOLOGIES = [
    {"technology": "WordPress", "label": "WordPress", "color": "#2563eb"},
    {"technology": "Shopify", "label": "Shopify", "color": "#16a34a"},
    {"technology": "Wix", "label": "Wix", "color": "#f59e0b"},
    {"technology": "Squarespace", "label": "Squarespace", "color": "#64748b"},
    {"technology": "Webflow", "label": "Webflow", "color": "#0891b2"},
]
HTTP_ARCHIVE_RANKS = [
    {"rank": "Top 1k", "rank_order": 1},
    {"rank": "Top 10k", "rank_order": 2},
    {"rank": "Top 100k", "rank_order": 3},
    {"rank": "Top 1M", "rank_order": 4},
    {"rank": "Top 10M", "rank_order": 5},
]
BUILTWITH_TECHNOLOGIES = [
    {"technology": "Shopify", "category": "eCommerce", "source_url": "https://trends.builtwith.com/ecommerce/Shopify"},
    {"technology": "WooCommerce", "category": "eCommerce", "source_url": "https://trends.builtwith.com/ecommerce/WooCommerce"},
]
PLUGIN_API = "https://api.wordpress.org/plugins/info/1.2/?action=query_plugins&request[page]=1&request[per_page]=1"
THEME_API = "https://api.wordpress.org/themes/info/1.2/?action=query_themes&request[page]=1&request[per_page]=1"
WPORG_STATS_URLS = {
    "wordpress_version": "https://api.wordpress.org/stats/wordpress/1.0/",
    "php_version": "https://api.wordpress.org/stats/php/1.0/",
    "database_version": "https://api.wordpress.org/stats/mysql/1.0/",
}
PLUGIN_INFO_API = "https://api.wordpress.org/plugins/info/1.2/"
PLUGIN_DOWNLOADS_API = "https://api.wordpress.org/stats/plugin/1.0/downloads.php"
PLUGIN_DOWNLOADS_DOCS_URL = "https://codex.wordpress.org/WordPress.org_API#Plugin_Download_Stats"
THEME_INFO_API = "https://api.wordpress.org/themes/info/1.2/"
WORDCAMP_API = "https://central.wordcamp.org/wp-json/wp/v2/wordcamps"
EVENTS_WORDPRESS_URL = "https://events.wordpress.org/"
MAKE_CORE_API = "https://make.wordpress.org/core/wp-json/wp/v2/posts"
MAKE_CORE_COMMENTS_API = "https://make.wordpress.org/core/wp-json/wp/v2/comments"
MAKE_CORE_TAGS_API = "https://make.wordpress.org/core/wp-json/wp/v2/tags"
TRANSLATE_LOCALES_URL = "https://translate.wordpress.org/"
TRANSLATE_CORE_DEV_URL = "https://translate.wordpress.org/projects/wp/dev/"
FTTF_PLEDGES_URL = "https://wordpress.org/five-for-the-future/pledges/"
RELEASE_ARCHIVE_URL = "https://wordpress.org/download/releases/"
CREDITS_API = "https://api.wordpress.org/core/credits/1.1/"
GITHUB_COMPARE_API = "https://api.github.com/repos/WordPress/wordpress-develop/compare"
STACK_EXCHANGE_QUESTIONS_API = "https://api.stackexchange.com/2.3/questions"
STACK_EXCHANGE_DOCS_URL = "https://api.stackexchange.com/docs/questions"
HN_SEARCH_API = "https://hn.algolia.com/api/v1/search"
HN_ITEM_API = "https://hn.algolia.com/api/v1/items"
HN_HIRING_SOURCE_URL = "https://news.ycombinator.com/submitted?id=whoishiring"
WORDPRESS_JOBS_URL = "https://jobs.wordpress.net/"
WAYBACK_CDX_API = "https://web.archive.org/cdx"
WAYBACK_WEB_ROOT = "https://web.archive.org/web"
WIKIMEDIA_PAGEVIEWS_API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
WIKIMEDIA_PAGEVIEWS_DOCS_URL = "https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html"
WPVIP_CASE_STUDY_API = "https://wpvip.com/wp-json/wp/v2/case-study"
WPVIP_CASE_STUDY_ARCHIVE_URL = "https://wpvip.com/case-studies/"
STACK_OVERFLOW_TAG_START = dt.datetime(2010, 1, 1, tzinfo=dt.timezone.utc)
HN_HIRING_START = dt.datetime(2012, 1, 1, tzinfo=dt.timezone.utc)
WIKIMEDIA_PAGEVIEW_START = dt.datetime(2015, 7, 1, tzinfo=dt.timezone.utc)
WORDPRESS_JOBS_ARCHIVE_START_YEAR = 2016
MAJOR_PLUGIN_ARCHIVE_START_YEAR = 2016
STACK_OVERFLOW_TAGS = [
    {"tag": "wordpress", "label": "WordPress", "color": "#2563eb"},
    {"tag": "woocommerce", "label": "WooCommerce", "color": "#7c3aed"},
    {"tag": "shopify", "label": "Shopify", "color": "#16a34a"},
    {"tag": "wix", "label": "Wix", "color": "#f59e0b"},
    {"tag": "squarespace", "label": "Squarespace", "color": "#64748b"},
    {"tag": "webflow", "label": "Webflow", "color": "#0891b2"},
]
WIKIMEDIA_PAGEVIEW_ARTICLES = [
    {"article": "WordPress", "label": "WordPress", "color": "#2563eb"},
    {"article": "WooCommerce", "label": "WooCommerce", "color": "#7c3aed"},
    {"article": "Shopify", "label": "Shopify", "color": "#16a34a"},
    {"article": "Wix.com", "label": "Wix", "color": "#f59e0b"},
    {"article": "Squarespace", "label": "Squarespace", "color": "#64748b"},
    {"article": "Webflow", "label": "Webflow", "color": "#0891b2"},
]
MAJOR_PLUGIN_SLUGS = [
    "woocommerce",
    "elementor",
    "contact-form-7",
    "wordpress-seo",
    "classic-editor",
    "akismet",
    "jetpack",
    "wordfence",
    "all-in-one-wp-migration",
    "really-simple-ssl",
    "wpforms-lite",
    "litespeed-cache",
    "updraftplus",
    "advanced-custom-fields",
    "duplicate-post",
]
MAJOR_PLUGIN_DISPLAY_NAMES = {
    "woocommerce": "WooCommerce",
    "elementor": "Elementor",
    "contact-form-7": "Contact Form 7",
    "wordpress-seo": "Yoast SEO",
    "classic-editor": "Classic Editor",
    "akismet": "Akismet",
    "jetpack": "Jetpack",
    "wordfence": "Wordfence",
    "all-in-one-wp-migration": "All-in-One WP Migration",
    "really-simple-ssl": "Really Simple SSL",
    "wpforms-lite": "WPForms",
    "litespeed-cache": "LiteSpeed Cache",
    "updraftplus": "UpdraftPlus",
    "advanced-custom-fields": "ACF",
    "duplicate-post": "Duplicate Post",
}
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
    "webflow": "#0891b2",
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


def read_existing_db_table(table_name):
    if not DB_PATH.exists():
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(f'SELECT * FROM "{table_name}"')]
        conn.close()
        return rows
    except sqlite3.Error:
        return []


def apply_skip_network_db_fallback(fetched):
    restored = []
    for table_name in SKIP_NETWORK_DB_FALLBACK_TABLES:
        if fetched.get(table_name):
            continue
        rows = read_existing_db_table(table_name)
        if rows:
            fetched[table_name] = rows
            restored.append((table_name, len(rows)))
    if restored:
        eprint(
            "restored skip-network table snapshots from existing SQLite: "
            + ", ".join(f"{name}={count}" for name, count in restored)
        )


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


def month_start(value):
    parsed = parse_iso(value)
    if not parsed:
        return None
    return f"{parsed.year:04d}-{parsed.month:02d}-01"


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


def per_100(value, digits=2):
    if value is None:
        return "n/a"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if math.isnan(value):
        return "n/a"
    return f"{value:.{digits}f} / 100"


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


def category_label(value):
    labels = {
        "bug": "Bugs",
        "enhancement": "Enhancements",
        "feature_request": "Feature requests",
        "task_maintenance": "Tasks",
        "support_question": "Support questions",
        "test_flake": "Test flakes",
        "accessibility": "Accessibility",
        "performance": "Performance",
        "documentation": "Documentation",
        "security": "Security",
        "other": "Other",
    }
    value = str(value or "unknown")
    return labels.get(value, value.replace("_", " ").title())


def median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def percentile(values, percentile_value):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * percentile_value
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return values[int(rank)]
    lower_value = values[lower]
    upper_value = values[upper]
    return lower_value + (upper_value - lower_value) * (rank - lower)


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


def fetch_with_retries(fetcher, url, label, attempts=3, delay=1.0):
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return fetcher(url)
        except Exception as exc:
            last_exc = exc
            if attempt == attempts:
                break
            time.sleep(delay * attempt)
    raise last_exc


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


def strip_html(value):
    value = re.sub(r"<[^>]+>", " ", str(value or ""))
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_count(value):
    cleaned = re.sub(r"[^\d.-]", "", str(value or ""))
    return num(cleaned)


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


def w3techs_cache_path(metric_name):
    return CACHE / f"w3techs-{metric_name}.json"


def read_cached_w3techs_history(metric_name):
    cache_path = w3techs_cache_path(metric_name)
    if cache_path.exists():
        try:
            rows = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(rows, list):
                return rows
        except (json.JSONDecodeError, OSError):
            return []
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            rows = [
                dict(row)
                for row in conn.execute(
                    "SELECT metric, date, technology, value, source_url FROM market_share WHERE metric = ?",
                    (metric_name,),
                )
            ]
            conn.close()
            return rows
        except sqlite3.Error:
            return []
    return []


def write_cached_w3techs_history(metric_name, rows):
    CACHE.mkdir(parents=True, exist_ok=True)
    w3techs_cache_path(metric_name).write_text(json.dumps(rows, ensure_ascii=True, sort_keys=True), encoding="utf-8")


def read_existing_table(table_name):
    if not DB_PATH.exists():
        return []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(f'SELECT * FROM "{table_name}"')]
        conn.close()
        return rows
    except sqlite3.Error:
        return []


def parse_w3techs_history(url, metric_name, skip_network=False):
    fallback = read_cached_w3techs_history(metric_name)
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
        if rows:
            write_cached_w3techs_history(metric_name, rows)
        return rows
    except Exception as exc:
        eprint(f"w3techs fetch failed for {metric_name}: {exc}")
        return fallback


def http_archive_adoption_cache_path():
    return CACHE / "http-archive-adoption-monthly.json"


def read_cached_http_archive_adoption():
    path = http_archive_adoption_cache_path()
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
        rows = payload.get("rows") if isinstance(payload, dict) else payload
        if isinstance(rows, list):
            return rows
    return read_existing_table("http_archive_adoption_monthly")


def write_cached_http_archive_adoption(rows, source_url):
    CACHE.mkdir(parents=True, exist_ok=True)
    http_archive_adoption_cache_path().write_text(
        json.dumps(
            {
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "source_url": source_url,
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def http_archive_adoption_url(start="2020-01-01"):
    technologies = ",".join(row["technology"] for row in HTTP_ARCHIVE_ADOPTION_TECHNOLOGIES)
    params = {
        "technology": technologies,
        "geo": "ALL",
        "rank": "ALL",
        "start": start,
    }
    return f"{HTTP_ARCHIVE_API_BASE}/adoption?{urllib.parse.urlencode(params)}"


def fetch_http_archive_adoption_monthly(skip_network=False):
    fallback = read_cached_http_archive_adoption()
    if skip_network and fallback:
        return fallback
    if skip_network:
        return []
    source_url = http_archive_adoption_url()
    try:
        payload, _headers = fetch_with_retries(fetch_json, source_url, "HTTP Archive adoption", attempts=3, delay=1.5)
    except Exception as exc:
        eprint(f"HTTP Archive adoption fetch failed: {exc}")
        return fallback
    rows = []
    tech_lookup = {row["technology"]: row for row in HTTP_ARCHIVE_ADOPTION_TECHNOLOGIES}
    for item in payload if isinstance(payload, list) else []:
        technology = str(item.get("technology") or "")
        adoption = item.get("adoption") or {}
        date_value = str(item.get("date") or "")
        if technology not in tech_lookup or not parse_iso(date_value):
            continue
        desktop = num(adoption.get("desktop"))
        mobile = num(adoption.get("mobile"))
        rows.append(
            {
                "date": date_value,
                "technology": technology,
                "desktop_origins": desktop,
                "mobile_origins": mobile,
                "total_origins": desktop + mobile,
                "geo": "ALL",
                "rank": "ALL",
                "source_url": source_url,
                "source": "HTTP Archive Technology Report API adoption endpoint",
            }
        )
    rows.sort(key=lambda row: (row["date"], row["technology"]))
    if rows:
        write_cached_http_archive_adoption(rows, source_url)
    return rows or fallback


def derive_http_archive_tracked_share_monthly(adoption_rows):
    grouped = defaultdict(list)
    for row in adoption_rows or []:
        key = (row.get("date"), row.get("rank") or "ALL", row.get("geo") or "ALL")
        if not key[0]:
            continue
        grouped[key].append(row)

    rows = []
    collected_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    for (date, rank, geo), items in sorted(grouped.items()):
        tracked_mobile = sum(num(item.get("mobile_origins")) for item in items)
        tracked_desktop = sum(num(item.get("desktop_origins")) for item in items)
        tracked_total = sum(num(item.get("total_origins")) for item in items)
        for item in sorted(items, key=lambda value: str(value.get("technology") or "")):
            mobile_origins = num(item.get("mobile_origins"))
            desktop_origins = num(item.get("desktop_origins"))
            total_origins = num(item.get("total_origins"))
            rows.append(
                {
                    "date": date,
                    "technology": item.get("technology", ""),
                    "rank": rank,
                    "geo": geo,
                    "mobile_origins": mobile_origins,
                    "desktop_origins": desktop_origins,
                    "total_origins": total_origins,
                    "tracked_mobile_origins": tracked_mobile,
                    "tracked_desktop_origins": tracked_desktop,
                    "tracked_total_origins": tracked_total,
                    "mobile_tracked_share_pct": mobile_origins / tracked_mobile * 100 if tracked_mobile else 0,
                    "desktop_tracked_share_pct": desktop_origins / tracked_desktop * 100 if tracked_desktop else 0,
                    "total_tracked_share_pct": total_origins / tracked_total * 100 if tracked_total else 0,
                    "source": "Derived from HTTP Archive Technology Report API monthly adoption rows",
                    "source_url": HTTP_ARCHIVE_TECH_REPORT_URL,
                    "collected_at": collected_at,
                }
            )
    return rows


def http_archive_rank_cache_path():
    return CACHE / "http-archive-rank-adoption-snapshot.json"


def read_cached_http_archive_rank_adoption():
    path = http_archive_rank_cache_path()
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
        rows = payload.get("rows") if isinstance(payload, dict) else payload
        if isinstance(rows, list):
            return rows
    return read_existing_table("http_archive_rank_adoption_snapshot")


def write_cached_http_archive_rank_adoption(rows):
    CACHE.mkdir(parents=True, exist_ok=True)
    http_archive_rank_cache_path().write_text(
        json.dumps(
            {
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "source_url": HTTP_ARCHIVE_TECH_REPORT_URL,
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def http_archive_rank_adoption_url(rank):
    technologies = ",".join(row["technology"] for row in HTTP_ARCHIVE_ADOPTION_TECHNOLOGIES)
    params = {
        "technology": technologies,
        "geo": "ALL",
        "rank": rank,
        "start": "latest",
    }
    return f"{HTTP_ARCHIVE_API_BASE}/adoption?{urllib.parse.urlencode(params)}"


def fetch_http_archive_rank_adoption_snapshot(skip_network=False):
    fallback = read_cached_http_archive_rank_adoption()
    if skip_network and fallback:
        return fallback
    if skip_network:
        return []
    tech_lookup = {row["technology"]: row for row in HTTP_ARCHIVE_ADOPTION_TECHNOLOGIES}
    rows = []
    for rank_config in HTTP_ARCHIVE_RANKS:
        rank = rank_config["rank"]
        source_url = http_archive_rank_adoption_url(rank)
        try:
            payload, _headers = fetch_with_retries(fetch_json, source_url, f"HTTP Archive adoption {rank}", attempts=3, delay=1.5)
        except Exception as exc:
            eprint(f"HTTP Archive rank adoption fetch failed for {rank}: {exc}")
            continue
        for item in payload if isinstance(payload, list) else []:
            technology = str(item.get("technology") or "")
            adoption = item.get("adoption") or {}
            date_value = str(item.get("date") or "")
            if technology not in tech_lookup or not parse_iso(date_value):
                continue
            desktop = num(adoption.get("desktop"))
            mobile = num(adoption.get("mobile"))
            rows.append(
                {
                    "date": date_value,
                    "rank": rank,
                    "rank_order": rank_config["rank_order"],
                    "technology": technology,
                    "desktop_origins": desktop,
                    "mobile_origins": mobile,
                    "total_origins": desktop + mobile,
                    "geo": "ALL",
                    "source_url": source_url,
                    "source": "HTTP Archive Technology Report API adoption endpoint",
                }
            )
        time.sleep(0.2)
    rows.sort(key=lambda row: (num(row["rank_order"]), row["technology"]))
    if rows:
        write_cached_http_archive_rank_adoption(rows)
    return rows or fallback


def http_archive_cwv_cache_path():
    return CACHE / "http-archive-cwv-monthly.json"


def read_cached_http_archive_cwv():
    path = http_archive_cwv_cache_path()
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
        rows = payload.get("rows") if isinstance(payload, dict) else payload
        if isinstance(rows, list):
            return rows
    return read_existing_table("http_archive_cwv_monthly")


def write_cached_http_archive_cwv(rows, source_url):
    CACHE.mkdir(parents=True, exist_ok=True)
    http_archive_cwv_cache_path().write_text(
        json.dumps(
            {
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "source_url": source_url,
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def http_archive_cwv_url(start="2020-01-01"):
    technologies = ",".join(row["technology"] for row in HTTP_ARCHIVE_ADOPTION_TECHNOLOGIES)
    params = {
        "technology": technologies,
        "geo": "ALL",
        "rank": "ALL",
        "start": start,
    }
    return f"{HTTP_ARCHIVE_API_BASE}/cwv?{urllib.parse.urlencode(params)}"


def fetch_http_archive_cwv_monthly(skip_network=False):
    fallback = read_cached_http_archive_cwv()
    if skip_network and fallback:
        return fallback
    if skip_network:
        return []
    source_url = http_archive_cwv_url()
    try:
        payload, _headers = fetch_with_retries(fetch_json, source_url, "HTTP Archive CWV", attempts=3, delay=1.5)
    except Exception as exc:
        eprint(f"HTTP Archive CWV fetch failed: {exc}")
        return fallback
    rows = []
    tech_lookup = {row["technology"]: row for row in HTTP_ARCHIVE_ADOPTION_TECHNOLOGIES}
    for item in payload if isinstance(payload, list) else []:
        technology = str(item.get("technology") or "")
        date_value = str(item.get("date") or "")
        if technology not in tech_lookup or not parse_iso(date_value):
            continue
        for metric in item.get("vitals") or []:
            metric_name = str(metric.get("name") or "")
            if not metric_name:
                continue
            desktop = metric.get("desktop") or {}
            mobile = metric.get("mobile") or {}
            desktop_tested = num(desktop.get("tested"))
            desktop_good = num(desktop.get("good_number"))
            mobile_tested = num(mobile.get("tested"))
            mobile_good = num(mobile.get("good_number"))
            rows.append(
                {
                    "date": date_value,
                    "technology": technology,
                    "metric": metric_name,
                    "desktop_tested": desktop_tested,
                    "desktop_good": desktop_good,
                    "desktop_good_pct": round(desktop_good / desktop_tested * 100, 1) if desktop_tested else 0,
                    "mobile_tested": mobile_tested,
                    "mobile_good": mobile_good,
                    "mobile_good_pct": round(mobile_good / mobile_tested * 100, 1) if mobile_tested else 0,
                    "geo": "ALL",
                    "rank": "ALL",
                    "source_url": source_url,
                    "source": "HTTP Archive Technology Report API Core Web Vitals endpoint",
                }
            )
    rows.sort(key=lambda row: (row["date"], row["technology"], row["metric"]))
    if rows:
        write_cached_http_archive_cwv(rows, source_url)
    return rows or fallback


def wporg_ecosystem_stats_cache_path():
    return CACHE / "wporg-ecosystem-stats-snapshot.json"


def read_cached_wporg_ecosystem_stats():
    path = wporg_ecosystem_stats_cache_path()
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
        rows = payload.get("rows") if isinstance(payload, dict) else payload
        if isinstance(rows, list):
            return rows
    return read_existing_table("wporg_ecosystem_stats_snapshot")


def write_cached_wporg_ecosystem_stats(rows):
    CACHE.mkdir(parents=True, exist_ok=True)
    wporg_ecosystem_stats_cache_path().write_text(
        json.dumps(
            {
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "source_urls": WPORG_STATS_URLS,
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def database_version_family(label):
    label = str(label or "")
    if label.startswith("MariaDB"):
        return "MariaDB"
    if label.startswith("MySQL"):
        return "MySQL"
    if label.startswith("Percona"):
        return "Percona"
    if re.match(r"^\d", label):
        return "MySQL"
    return "Other"


def wporg_stat_family(metric, label):
    if metric == "database_version":
        return database_version_family(label)
    if metric == "php_version":
        return f"PHP {str(label).split('.')[0]}"
    if metric == "wordpress_version":
        return f"WordPress {str(label).split('.')[0]}"
    return ""


def fetch_wporg_ecosystem_stats_snapshot(skip_network=False):
    fallback = read_cached_wporg_ecosystem_stats()
    if skip_network and fallback:
        return fallback
    if skip_network:
        return []
    snapshot_date = live_snapshot_date()
    rows = []
    for metric, source_url in WPORG_STATS_URLS.items():
        try:
            payload, _headers = fetch_with_retries(fetch_json, source_url, f"WordPress.org stats {metric}", attempts=3, delay=1.5)
        except Exception as exc:
            eprint(f"WordPress.org ecosystem stats fetch failed for {metric}: {exc}")
            continue
        if not isinstance(payload, dict):
            continue
        for label, share in payload.items():
            try:
                share_pct = float(share)
            except (TypeError, ValueError):
                continue
            rows.append(
                {
                    "snapshot_date": snapshot_date,
                    "metric": metric,
                    "label": str(label),
                    "family": wporg_stat_family(metric, label),
                    "share_pct": round(share_pct, 3),
                    "source_url": source_url,
                    "source": "WordPress.org stats API current distribution snapshot",
                }
            )
    rows.sort(key=lambda row: (row["metric"], -float(row["share_pct"]), row["label"]))
    if rows:
        write_cached_wporg_ecosystem_stats(rows)
    return rows or fallback


def quarter_ranges(start, end):
    current = dt.datetime(start.year, ((start.month - 1) // 3) * 3 + 1, 1, tzinfo=dt.timezone.utc)
    while current <= end:
        next_month = current.month + 3
        next_year = current.year
        if next_month > 12:
            next_month -= 12
            next_year += 1
        next_quarter = dt.datetime(next_year, next_month, 1, tzinfo=dt.timezone.utc)
        yield current, min(next_quarter, end + dt.timedelta(seconds=1))
        current = next_quarter


def stackexchange_tag_cache_path():
    return CACHE / "stackexchange-tag-quarterly.json"


def read_cached_stackoverflow_tag_quarterly():
    path = stackexchange_tag_cache_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    return rows if isinstance(rows, list) else []


def write_cached_stackoverflow_tag_quarterly(rows):
    CACHE.mkdir(parents=True, exist_ok=True)
    stackexchange_tag_cache_path().write_text(
        json.dumps(
            {
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "source_url": STACK_EXCHANGE_DOCS_URL,
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def stackexchange_questions_url(tag, start, end):
    params = {
        "site": "stackoverflow",
        "tagged": tag,
        "fromdate": int(start.timestamp()),
        "todate": max(int(end.timestamp()) - 1, int(start.timestamp())),
        "order": "desc",
        "sort": "creation",
        "pagesize": 1,
        "filter": "total",
    }
    return f"{STACK_EXCHANGE_QUESTIONS_API}?{urllib.parse.urlencode(params)}"


def fetch_stackoverflow_tag_quarterly(skip_network=False):
    cached_rows = read_cached_stackoverflow_tag_quarterly()
    by_key = {
        (row.get("tag"), row.get("quarter")): dict(row)
        for row in cached_rows
        if isinstance(row, dict) and row.get("tag") and row.get("quarter")
    }
    quarters = list(quarter_ranges(STACK_OVERFLOW_TAG_START, END))
    expected_keys = {
        (tag_config["tag"], quarter_start_dt.strftime("%Y-%m-%d"))
        for tag_config in STACK_OVERFLOW_TAGS
        for quarter_start_dt, _quarter_end_dt in quarters
    }
    if skip_network or (expected_keys and expected_keys.issubset(set(by_key))):
        return sorted(by_key.values(), key=lambda row: (row.get("tag", ""), row.get("quarter", "")))

    collected_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    for tag_config in STACK_OVERFLOW_TAGS:
        tag = tag_config["tag"]
        label = tag_config["label"]
        for quarter_start_dt, quarter_end_dt in quarters:
            quarter = quarter_start_dt.strftime("%Y-%m-%d")
            key = (tag, quarter)
            if key in by_key:
                continue
            api_url = stackexchange_questions_url(tag, quarter_start_dt, quarter_end_dt)
            try:
                payload, _headers = fetch_json(api_url)
            except urllib.error.HTTPError as exc:
                try:
                    error_body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    error_body = ""
                lower_error = error_body.lower()
                throttled = exc.code == 429 or "too many requests" in lower_error or "throttle" in lower_error
                if throttled:
                    eprint(
                        f"Stack Exchange throttled while fetching {tag} {quarter} (HTTP {exc.code}); "
                        "keeping cached and newly fetched rows."
                    )
                    rows = sorted(by_key.values(), key=lambda row: (row.get("tag", ""), row.get("quarter", "")))
                    if rows:
                        write_cached_stackoverflow_tag_quarterly(rows)
                    return rows
                eprint(f"Stack Exchange fetch failed for {tag} {quarter}: HTTP {exc.code}")
                continue
            except Exception as exc:
                eprint(f"Stack Exchange fetch failed for {tag} {quarter}: {exc}")
                continue
            total = payload.get("total") if isinstance(payload, dict) else None
            if total is None:
                eprint(f"Stack Exchange fetch missing total for {tag} {quarter}")
                continue
            by_key[key] = {
                "quarter": quarter,
                "label": quarter_label(quarter),
                "tag": tag,
                "technology": label,
                "question_count": int(total),
                "source": "Stack Exchange API question totals by Stack Overflow tag",
                "source_url": STACK_EXCHANGE_DOCS_URL,
                "api_url": api_url,
                "collected_at": collected_at,
                "quota_remaining": payload.get("quota_remaining") if isinstance(payload, dict) else "",
            }
            backoff = payload.get("backoff") if isinstance(payload, dict) else None
            if backoff:
                rows = sorted(by_key.values(), key=lambda row: (row.get("tag", ""), row.get("quarter", "")))
                write_cached_stackoverflow_tag_quarterly(rows)
                time.sleep(float(backoff))
            else:
                time.sleep(0.08)
            if by_key:
                rows = sorted(by_key.values(), key=lambda row: (row.get("tag", ""), row.get("quarter", "")))
                write_cached_stackoverflow_tag_quarterly(rows)

    rows = sorted(by_key.values(), key=lambda row: (row.get("tag", ""), row.get("quarter", "")))
    if rows:
        write_cached_stackoverflow_tag_quarterly(rows)
    return rows


def wikimedia_pageviews_cache_path():
    return CACHE / "wikimedia-pageviews-monthly.json"


def read_cached_wikimedia_pageviews_monthly():
    path = wikimedia_pageviews_cache_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    return rows if isinstance(rows, list) else []


def write_cached_wikimedia_pageviews_monthly(rows):
    CACHE.mkdir(parents=True, exist_ok=True)
    wikimedia_pageviews_cache_path().write_text(
        json.dumps(
            {
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "source_url": WIKIMEDIA_PAGEVIEWS_DOCS_URL,
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def wikimedia_pageviews_url(article, start, end):
    encoded_article = urllib.parse.quote(article.replace(" ", "_"), safe="")
    start_value = start.strftime("%Y%m%d00")
    end_value = end.strftime("%Y%m%d00")
    return (
        f"{WIKIMEDIA_PAGEVIEWS_API}/en.wikipedia/all-access/all-agents/"
        f"{encoded_article}/monthly/{start_value}/{end_value}"
    )


def normalize_wikimedia_pageview_item(item, config, source_url, collected_at):
    timestamp = str(item.get("timestamp") or "")
    month = f"{timestamp[:4]}-{timestamp[4:6]}-01" if len(timestamp) >= 6 else ""
    return {
        "month": month,
        "label": month[:7],
        "article": config["article"],
        "technology": config["label"],
        "views": num(item.get("views")),
        "project": str(item.get("project") or "en.wikipedia"),
        "access": str(item.get("access") or "all-access"),
        "agent": str(item.get("agent") or "all-agents"),
        "source": "Wikimedia Pageviews API monthly en.wikipedia article views",
        "source_url": WIKIMEDIA_PAGEVIEWS_DOCS_URL,
        "api_url": source_url,
        "collected_at": collected_at,
    }


def aggregate_wikimedia_pageviews_quarterly(monthly_rows):
    grouped = defaultdict(list)
    for row in monthly_rows:
        q = quarter_start(row.get("month"))
        if q:
            grouped[(row.get("article"), q)].append(row)
    rows = []
    collected_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    label_by_article = {item["article"]: item["label"] for item in WIKIMEDIA_PAGEVIEW_ARTICLES}
    for (article, quarter), items in sorted(grouped.items()):
        rows.append(
            {
                "quarter": quarter,
                "label": quarter_label(quarter),
                "article": article,
                "technology": label_by_article.get(article, article),
                "views": sum(num(item.get("views")) for item in items),
                "months_covered": len(items),
                "source": "Wikimedia Pageviews API monthly en.wikipedia article views, aggregated quarterly",
                "source_url": WIKIMEDIA_PAGEVIEWS_DOCS_URL,
                "collected_at": collected_at,
            }
        )
    return rows


def fetch_wikimedia_pageviews(skip_network=False):
    cached_rows = read_cached_wikimedia_pageviews_monthly()
    by_key = {
        (row.get("article"), row.get("month")): dict(row)
        for row in cached_rows
        if isinstance(row, dict) and row.get("article") and row.get("month")
    }
    expected_months = [month.strftime("%Y-%m-%d") for month in month_starts(WIKIMEDIA_PAGEVIEW_START, END)]
    expected_keys = {
        (config["article"], month)
        for config in WIKIMEDIA_PAGEVIEW_ARTICLES
        for month in expected_months
    }
    if skip_network or (expected_keys and expected_keys.issubset(set(by_key))):
        monthly_rows = [
            by_key[(config["article"], month)]
            for config in WIKIMEDIA_PAGEVIEW_ARTICLES
            for month in expected_months
            if (config["article"], month) in by_key
        ]
        return monthly_rows, aggregate_wikimedia_pageviews_quarterly(monthly_rows)

    collected_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    for config in WIKIMEDIA_PAGEVIEW_ARTICLES:
        article = config["article"]
        missing_months = [month for month in expected_months if (article, month) not in by_key]
        if not missing_months:
            continue
        try:
            source_url = wikimedia_pageviews_url(article, WIKIMEDIA_PAGEVIEW_START, END)
            payload, _headers = fetch_json(source_url)
        except Exception as exc:
            eprint(f"Wikimedia pageviews fetch failed for {article}: {exc}")
            continue
        for item in payload.get("items", []) if isinstance(payload, dict) else []:
            row = normalize_wikimedia_pageview_item(item, config, source_url, collected_at)
            if row.get("month"):
                by_key[(article, row["month"])] = row
        time.sleep(0.08)
    monthly_rows = [
        by_key[(config["article"], month)]
        for config in WIKIMEDIA_PAGEVIEW_ARTICLES
        for month in expected_months
        if (config["article"], month) in by_key
    ]
    if monthly_rows:
        write_cached_wikimedia_pageviews_monthly(monthly_rows)
    return monthly_rows, aggregate_wikimedia_pageviews_quarterly(monthly_rows)


def month_starts(start, end):
    current = dt.datetime(start.year, start.month, 1, tzinfo=dt.timezone.utc)
    while current <= end:
        yield current
        if current.month == 12:
            current = dt.datetime(current.year + 1, 1, 1, tzinfo=dt.timezone.utc)
        else:
            current = dt.datetime(current.year, current.month + 1, 1, tzinfo=dt.timezone.utc)


def hn_hiring_cache_path():
    return CACHE / "hn-hiring-wordpress-monthly.json"


def read_cached_hn_hiring_monthly():
    path = hn_hiring_cache_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    return rows if isinstance(rows, list) else []


def write_cached_hn_hiring_monthly(rows):
    CACHE.mkdir(parents=True, exist_ok=True)
    hn_hiring_cache_path().write_text(
        json.dumps(
            {
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "source_url": HN_HIRING_SOURCE_URL,
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def hn_search_url(query, hits_per_page=10):
    params = {
        "query": query,
        "tags": "story",
        "hitsPerPage": hits_per_page,
    }
    return f"{HN_SEARCH_API}?{urllib.parse.urlencode(params)}"


def find_hn_hiring_story(month_start):
    title = f"Ask HN: Who is hiring? ({month_start.strftime('%B')} {month_start.year})"
    data, _headers = fetch_json(hn_search_url(title))
    hits = data.get("hits") if isinstance(data, dict) else []
    if not isinstance(hits, list):
        hits = []
    normalized_title = title.lower()
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        observed_title = str(hit.get("title") or hit.get("story_title") or "").strip()
        if observed_title.lower() == normalized_title:
            return str(hit.get("objectID") or ""), observed_title
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        observed_title = str(hit.get("title") or hit.get("story_title") or "").strip()
        if "who is hiring?" in observed_title.lower() and month_start.strftime("%B").lower() in observed_title.lower() and str(month_start.year) in observed_title:
            return str(hit.get("objectID") or ""), observed_title
    return "", ""


WP_HIRING_RE = re.compile(r"\bwordpress\b", re.I)
WOO_HIRING_RE = re.compile(r"\bwoo\s*commerce\b|\bwoocommerce\b", re.I)
PHP_HIRING_RE = re.compile(r"\bphp\b", re.I)
AGENCY_HIRING_RE = re.compile(r"\bagency\b|\bdigital studio\b|\bweb studio\b|\bmarketing agency\b", re.I)


def hn_hiring_month_row(month_start, story_id, story_title):
    source_url = f"https://news.ycombinator.com/item?id={story_id}"
    data, _headers = fetch_json(f"{HN_ITEM_API}/{story_id}")
    comments = data.get("children") if isinstance(data, dict) else []
    if not isinstance(comments, list):
        comments = []
    hiring_comments = 0
    wordpress_comments = 0
    woocommerce_comments = 0
    php_comments = 0
    agency_comments = 0
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        text = strip_html(comment.get("text") or "")
        if not text:
            continue
        hiring_comments += 1
        has_wordpress = bool(WP_HIRING_RE.search(text))
        has_woocommerce = bool(WOO_HIRING_RE.search(text))
        if has_wordpress:
            wordpress_comments += 1
        if has_woocommerce:
            woocommerce_comments += 1
        if PHP_HIRING_RE.search(text):
            php_comments += 1
        if AGENCY_HIRING_RE.search(text):
            agency_comments += 1
    wp_or_woo = 0
    for comment in comments:
        if isinstance(comment, dict):
            text = strip_html(comment.get("text") or "")
            if WP_HIRING_RE.search(text) or WOO_HIRING_RE.search(text):
                wp_or_woo += 1
    return {
        "month": month_start.strftime("%Y-%m-%d"),
        "label": month_start.strftime("%Y-%m"),
        "story_id": story_id,
        "story_title": story_title,
        "hiring_comments": hiring_comments,
        "wordpress_comments": wordpress_comments,
        "woocommerce_comments": woocommerce_comments,
        "wordpress_or_woocommerce_comments": wp_or_woo,
        "php_comments": php_comments,
        "agency_comments": agency_comments,
        "wordpress_or_woocommerce_per_100_comments": round(wp_or_woo / hiring_comments * 100, 2) if hiring_comments else 0,
        "source": "Hacker News monthly Who is hiring? thread top-level comments",
        "source_url": source_url,
    }


def aggregate_hn_hiring_quarterly(monthly_rows):
    grouped = defaultdict(list)
    for row in monthly_rows:
        q = quarter_start(row.get("month"))
        if q:
            grouped[q].append(row)
    quarterly = []
    collected_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    for quarter, rows in sorted(grouped.items()):
        hiring_comments = sum(num(row.get("hiring_comments")) for row in rows)
        wp = sum(num(row.get("wordpress_comments")) for row in rows)
        woo = sum(num(row.get("woocommerce_comments")) for row in rows)
        wp_or_woo = sum(num(row.get("wordpress_or_woocommerce_comments")) for row in rows)
        php = sum(num(row.get("php_comments")) for row in rows)
        agency = sum(num(row.get("agency_comments")) for row in rows)
        quarterly.append(
            {
                "quarter": quarter,
                "label": quarter_label(quarter),
                "months_with_thread": len(rows),
                "hiring_comments": hiring_comments,
                "wordpress_comments": wp,
                "woocommerce_comments": woo,
                "wordpress_or_woocommerce_comments": wp_or_woo,
                "php_comments": php,
                "agency_comments": agency,
                "wordpress_or_woocommerce_per_100_comments": round(wp_or_woo / hiring_comments * 100, 2) if hiring_comments else 0,
                "php_per_100_comments": round(php / hiring_comments * 100, 2) if hiring_comments else 0,
                "agency_per_100_comments": round(agency / hiring_comments * 100, 2) if hiring_comments else 0,
                "story_ids": ",".join(str(row.get("story_id") or "") for row in rows if row.get("story_id")),
                "source_urls": ",".join(str(row.get("source_url") or "") for row in rows if row.get("source_url")),
                "source": "Hacker News monthly Who is hiring? thread top-level comments",
                "source_url": HN_HIRING_SOURCE_URL,
                "collected_at": collected_at,
            }
        )
    return quarterly


def fetch_hn_hiring_wordpress_quarterly(skip_network=False):
    cached_rows = read_cached_hn_hiring_monthly()
    by_month = {
        row.get("month"): dict(row)
        for row in cached_rows
        if isinstance(row, dict) and row.get("month")
    }
    expected_months = [month.strftime("%Y-%m-%d") for month in month_starts(HN_HIRING_START, END)]
    if skip_network or set(expected_months).issubset(set(by_month)):
        return aggregate_hn_hiring_quarterly([by_month[month] for month in expected_months if month in by_month])

    for month_start in month_starts(HN_HIRING_START, END):
        month = month_start.strftime("%Y-%m-%d")
        if month in by_month:
            continue
        try:
            story_id, story_title = find_hn_hiring_story(month_start)
            if not story_id:
                eprint(f"HN Who is hiring thread not found for {month}")
                continue
            by_month[month] = hn_hiring_month_row(month_start, story_id, story_title)
            time.sleep(0.12)
        except Exception as exc:
            eprint(f"HN Who is hiring fetch failed for {month}: {exc}")
    monthly_rows = [by_month[month] for month in expected_months if month in by_month]
    if monthly_rows:
        write_cached_hn_hiring_monthly(monthly_rows)
    return aggregate_hn_hiring_quarterly(monthly_rows)


def derive_hn_hiring_demand_summary(rows):
    ordered = sorted(
        [row for row in rows if row.get("quarter")],
        key=lambda row: row.get("quarter", ""),
    )
    if not ordered:
        return []
    latest_four = ordered[-4:]
    windows = [
        ("all_time", "All parsed HN hiring history", ordered),
        ("pre_2024", "Before 2024", [row for row in ordered if row.get("quarter", "") < "2024-01-01"]),
        ("since_2024", "Since 2024", [row for row in ordered if row.get("quarter", "") >= "2024-01-01"]),
        ("latest_4q", "Latest four quarters", latest_four),
        ("latest_quarter", f"Latest quarter ({quarter_label(ordered[-1].get('quarter', ''))})", [ordered[-1]]),
    ]
    collected_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    summary = []
    for window, label, window_rows in windows:
        if not window_rows:
            continue
        hiring_comments = sum(num(row.get("hiring_comments")) for row in window_rows)
        wp_or_woo = sum(num(row.get("wordpress_or_woocommerce_comments")) for row in window_rows)
        php = sum(num(row.get("php_comments")) for row in window_rows)
        agency = sum(num(row.get("agency_comments")) for row in window_rows)
        first_quarter = min(row.get("quarter", "") for row in window_rows if row.get("quarter"))
        latest_quarter = max(row.get("quarter", "") for row in window_rows if row.get("quarter"))
        summary.append(
            {
                "window": window,
                "label": label,
                "quarter_count": len(window_rows),
                "first_quarter": first_quarter,
                "latest_quarter": latest_quarter,
                "quarter_range": f"{quarter_label(first_quarter)} to {quarter_label(latest_quarter)}",
                "months_with_thread": sum(num(row.get("months_with_thread")) for row in window_rows),
                "hiring_comments": hiring_comments,
                "wordpress_or_woocommerce_comments": wp_or_woo,
                "wordpress_or_woocommerce_per_100_comments": round(wp_or_woo / hiring_comments * 100, 2) if hiring_comments else 0,
                "php_comments": php,
                "php_per_100_comments": round(php / hiring_comments * 100, 2) if hiring_comments else 0,
                "agency_comments": agency,
                "agency_per_100_comments": round(agency / hiring_comments * 100, 2) if hiring_comments else 0,
                "source": "Hacker News monthly Who is hiring? thread top-level comments",
                "source_url": HN_HIRING_SOURCE_URL,
                "collected_at": collected_at,
            }
        )
    return summary


def derive_attention_demand_summary(stack_overflow_rows, wikimedia_rows, hn_summary_rows, jobs_rows):
    rows = []
    collected_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

    def add_row(signal, label, source_type, latest_period, latest_value, baseline_period, baseline_value, unit, source_note):
        latest_value = float(latest_value or 0)
        baseline_value = float(baseline_value or 0)
        change = latest_value - baseline_value
        change_pct = change / baseline_value * 100 if baseline_value else 0
        if baseline_value and change_pct <= -10:
            direction = "lower"
        elif baseline_value and change_pct >= 10:
            direction = "higher"
        elif baseline_value:
            direction = "flat"
        else:
            direction = "no_baseline"
        rows.append(
            {
                "signal": signal,
                "label": label,
                "source_type": source_type,
                "latest_period": latest_period,
                "latest_value": round(latest_value, 2),
                "baseline_period": baseline_period,
                "baseline_value": round(baseline_value, 2),
                "change_value": round(change, 2),
                "change_pct": round(change_pct, 2),
                "direction": direction,
                "unit": unit,
                "source_note": source_note,
                "collected_at": collected_at,
            }
        )

    so_wp = [row for row in stack_overflow_rows if row.get("tag") == "wordpress"]
    latest_so = max(so_wp, key=lambda row: row.get("quarter", ""), default={})
    baseline_so = max([row for row in so_wp if row.get("quarter", "") < "2024-01-01"], key=lambda row: row.get("quarter", ""), default={})
    if latest_so and baseline_so:
        add_row(
            "stack_overflow_wordpress_questions",
            "Stack Overflow WordPress questions",
            "developer_help_proxy",
            quarter_label(latest_so.get("quarter", "")),
            num(latest_so.get("question_count")),
            quarter_label(baseline_so.get("quarter", "")),
            num(baseline_so.get("question_count")),
            "questions per quarter",
            "Stack Exchange API quarterly WordPress tag question totals",
        )

    wiki_wp = [row for row in wikimedia_rows if row.get("article") == "WordPress"]
    latest_wiki = max(wiki_wp, key=lambda row: row.get("quarter", ""), default={})
    baseline_wiki = max([row for row in wiki_wp if row.get("quarter", "") < "2024-01-01"], key=lambda row: row.get("quarter", ""), default={})
    if latest_wiki and baseline_wiki:
        add_row(
            "wikimedia_wordpress_pageviews",
            "Wikipedia WordPress pageviews",
            "public_attention_proxy",
            quarter_label(latest_wiki.get("quarter", "")),
            num(latest_wiki.get("views")),
            quarter_label(baseline_wiki.get("quarter", "")),
            num(baseline_wiki.get("views")),
            "views per quarter",
            "Wikimedia Pageviews API quarterly en.wikipedia WordPress article views",
        )

    hn_by_window = {row.get("window"): row for row in hn_summary_rows}
    hn_latest = hn_by_window.get("latest_4q", {})
    hn_baseline = hn_by_window.get("pre_2024", {})
    if hn_latest and hn_baseline:
        add_row(
            "hn_wordpress_woocommerce_hiring_rate",
            "HN WP/Woo hiring mention rate",
            "hiring_proxy",
            hn_latest.get("quarter_range", "latest four quarters"),
            float(hn_latest.get("wordpress_or_woocommerce_per_100_comments") or 0),
            hn_baseline.get("quarter_range", "pre-2024"),
            float(hn_baseline.get("wordpress_or_woocommerce_per_100_comments") or 0),
            "mentions per 100 comments",
            "Hacker News monthly Who is hiring? top-level comments mentioning WordPress or WooCommerce",
        )

    jobs_ordered = sorted([row for row in jobs_rows if row.get("snapshot_date")], key=lambda row: row.get("snapshot_date", ""))
    latest_jobs = jobs_ordered[-1] if jobs_ordered else {}
    baseline_jobs = max([row for row in jobs_ordered if row.get("snapshot_date", "") < "2024-01-01"], key=lambda row: row.get("snapshot_date", ""), default={})
    if latest_jobs and baseline_jobs:
        add_row(
            "wordpress_jobs_open_listings",
            "WordPress Jobs open listings",
            "wordpress_specific_jobs_proxy",
            latest_jobs.get("snapshot_date", ""),
            num(latest_jobs.get("total_jobs")),
            baseline_jobs.get("snapshot_date", ""),
            num(baseline_jobs.get("total_jobs")),
            "open listings",
            "jobs.wordpress.net current page plus annual Internet Archive snapshots",
        )
        add_row(
            "wordpress_jobs_development_listings",
            "WordPress Jobs development listings",
            "wordpress_specific_jobs_proxy",
            latest_jobs.get("snapshot_date", ""),
            num(latest_jobs.get("development_jobs")),
            baseline_jobs.get("snapshot_date", ""),
            num(baseline_jobs.get("development_jobs")),
            "open listings",
            "jobs.wordpress.net current page plus annual Internet Archive snapshots",
        )
    return rows


def wordpress_jobs_cache_path():
    return CACHE / "wordpress-jobs-board-snapshots.json"


def read_cached_wordpress_jobs_board():
    path = wordpress_jobs_cache_path()
    if not path.exists():
        return [], []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    snapshots = payload.get("snapshots", []) if isinstance(payload, dict) else []
    categories = payload.get("categories", []) if isinstance(payload, dict) else []
    return (
        snapshots if isinstance(snapshots, list) else [],
        categories if isinstance(categories, list) else [],
    )


def write_cached_wordpress_jobs_board(snapshots, categories):
    CACHE.mkdir(parents=True, exist_ok=True)
    wordpress_jobs_cache_path().write_text(
        json.dumps(
            {
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "source_url": WORDPRESS_JOBS_URL,
                "snapshots": snapshots,
                "categories": categories,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def slugify_label(value):
    slug = re.sub(r"[^a-z0-9]+", "-", strip_html(value).lower()).strip("-")
    return slug or "unknown"


def wordpress_jobs_cdx_url():
    params = [
        ("url", "jobs.wordpress.net/"),
        ("from", str(WORDPRESS_JOBS_ARCHIVE_START_YEAR)),
        ("to", str(END.year - 1)),
        ("matchType", "exact"),
        ("filter", "statuscode:200"),
        ("filter", "mimetype:text/html"),
        ("collapse", "timestamp:4"),
        ("output", "json"),
        ("fl", "timestamp,original,digest"),
    ]
    return f"{WAYBACK_CDX_API}?{urllib.parse.urlencode(params)}"


def fetch_wordpress_jobs_cdx_rows():
    url = wordpress_jobs_cdx_url()
    payload, _headers = fetch_with_retries(fetch_json, url, "WordPress Jobs CDX", attempts=4, delay=2.0)
    if not isinstance(payload, list) or len(payload) < 2:
        return [], url
    header = payload[0]
    rows = []
    for item in payload[1:]:
        if not isinstance(item, list) or len(item) != len(header):
            continue
        row = dict(zip(header, item))
        timestamp = str(row.get("timestamp") or "")
        if re.match(r"^\d{14}$", timestamp):
            rows.append(row)
    return rows, url


def classify_jobs_type(value):
    text = strip_html(value).lower()
    if "full time" in text or "full-time" in text:
        return "Full Time"
    if "part time" in text or "part-time" in text:
        return "Part Time"
    if "project" in text or "freelance" in text or "contract" in text:
        return "Project"
    if "intern" in text:
        return "Internship"
    return ""


def parse_wordpress_jobs_current_cards(page_html):
    rows = []
    for match in re.finditer(r'<a[^>]+class="[^"]*\bjob-card\b[^"]*"[^>]*>(.*?)</a>', page_html, flags=re.I | re.S):
        block = match.group(0)
        attrs = block[: block.find(">") + 1]
        href_match = re.search(r'href="([^"]+)"', attrs, flags=re.I)
        data_category_match = re.search(r'data-category="([^"]+)"', attrs, flags=re.I)
        category_match = re.search(r'class="[^"]*\bjob-card__badge\b[^"]*"[^>]*>(.*?)</span>', block, flags=re.I | re.S)
        title_match = re.search(r'class="[^"]*\bjob-card__title\b[^"]*"[^>]*>(.*?)</h2>', block, flags=re.I | re.S)
        company_match = re.search(r'class="[^"]*\bjob-card__company\b[^"]*"[^>]*>(.*?)</p>', block, flags=re.I | re.S)
        date_match = re.search(r'class="[^"]*\bjob-card__date\b[^"]*"[^>]*>\s*Posted\s+([^<]+)', block, flags=re.I | re.S)
        meta_text = strip_html(" ".join(re.findall(r'class="[^"]*\bjob-card__meta\b[^"]*"[^>]*>(.*?)</div>', block, flags=re.I | re.S)))
        category = strip_html(category_match.group(1)) if category_match else strip_html(data_category_match.group(1) if data_category_match else "")
        rows.append(
            {
                "title": strip_html(title_match.group(1)) if title_match else "",
                "url": href_match.group(1) if href_match else "",
                "category": category or "Uncategorized",
                "category_slug": slugify_label(data_category_match.group(1) if data_category_match else category),
                "company": strip_html(company_match.group(1)) if company_match else "",
                "job_type": classify_jobs_type(meta_text),
                "remote": "1" if "remote" in meta_text.lower() else "0",
                "posted_label": strip_html(date_match.group(1)) if date_match else "",
            }
        )
    return rows


def parse_wordpress_jobs_legacy_rows(page_html):
    rows = []
    group_pattern = re.compile(
        r'<div class="jobs-group">(.*?)(?=<div class="jobs-group">|<footer\b|</main>|<div id="footer")',
        re.I | re.S,
    )
    for group_match in group_pattern.finditer(page_html):
        group = group_match.group(1)
        category_match = re.search(r'View all jobs listed under ([^"]+)">([^<]+)</a>', group, flags=re.I | re.S)
        category = strip_html(category_match.group(2) if category_match else "")
        category = category or strip_html(category_match.group(1) if category_match else "") or "Uncategorized"
        category_slug = slugify_label(category)
        row_pattern = re.compile(
            r'<div class="row row-[^"]*">\s*'
            r'<div class="job-date[^"]*">(?P<date>.*?)</div>'
            r'<div class="job-title[^"]*"><a href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a></div>'
            r'<div class="job-type[^"]*">(?P<type>.*?)</div>'
            r'<div class="job-location[^"]*">(?P<location>.*?)</div>',
            re.I | re.S,
        )
        for row_match in row_pattern.finditer(group):
            rows.append(
                {
                    "title": strip_html(row_match.group("title")),
                    "url": row_match.group("url"),
                    "category": category,
                    "category_slug": category_slug,
                    "company": "",
                    "job_type": classify_jobs_type(row_match.group("type")),
                    "remote": "1" if "remote" in strip_html(row_match.group("location")).lower() else "0",
                    "posted_label": strip_html(row_match.group("date")),
                }
            )
    return rows


def parse_wordpress_jobs_page(page_html):
    rows = parse_wordpress_jobs_current_cards(page_html)
    if rows:
        return rows
    return parse_wordpress_jobs_legacy_rows(page_html)


def wordpress_jobs_summary_row(snapshot_date, source_type, source_url, jobs, archive_timestamp="", archive_digest="", archive_original_url=""):
    category_counts = Counter(row.get("category_slug") or "unknown" for row in jobs)
    type_counts = Counter(row.get("job_type") or "Unknown" for row in jobs)
    remote_jobs = sum(1 for row in jobs if row.get("remote") == "1")
    return {
        "snapshot_date": snapshot_date,
        "year": snapshot_date[:4],
        "source_type": source_type,
        "source_url": source_url,
        "archive_timestamp": archive_timestamp,
        "archive_digest": archive_digest,
        "archive_original_url": archive_original_url,
        "total_jobs": len(jobs),
        "development_jobs": category_counts.get("development", 0),
        "plugin_development_jobs": category_counts.get("plugin-development", 0),
        "theme_customization_jobs": category_counts.get("theme-customization", 0),
        "support_jobs": category_counts.get("support", 0),
        "design_jobs": category_counts.get("design", 0),
        "writing_jobs": category_counts.get("writing", 0),
        "performance_jobs": category_counts.get("performance", 0),
        "general_jobs": category_counts.get("general", 0),
        "full_time_jobs": type_counts.get("Full Time", 0),
        "project_jobs": type_counts.get("Project", 0),
        "part_time_jobs": type_counts.get("Part Time", 0),
        "remote_jobs": remote_jobs,
        "source": "WordPress Jobs board open listings snapshot",
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def wordpress_jobs_category_rows(snapshot_row, jobs):
    counts = Counter((row.get("category_slug") or "unknown", row.get("category") or "Uncategorized") for row in jobs)
    rows = []
    for (category_slug, category), count in sorted(counts.items(), key=lambda item: (-item[1], item[0][1])):
        rows.append(
            {
                "snapshot_date": snapshot_row["snapshot_date"],
                "year": snapshot_row["year"],
                "source_type": snapshot_row["source_type"],
                "category_slug": category_slug,
                "category": category,
                "open_jobs": count,
                "total_jobs": snapshot_row["total_jobs"],
                "category_share_pct": round(count / snapshot_row["total_jobs"] * 100, 2) if snapshot_row["total_jobs"] else 0,
                "source_url": snapshot_row["source_url"],
                "archive_timestamp": snapshot_row.get("archive_timestamp", ""),
            }
        )
    return rows


def fetch_wordpress_jobs_board_snapshots(skip_network=False):
    cached_snapshots, cached_categories = read_cached_wordpress_jobs_board()
    if skip_network and cached_snapshots:
        return cached_snapshots, cached_categories
    if skip_network:
        return [], []

    snapshots_by_key = {
        (row.get("snapshot_date"), row.get("source_type")): dict(row)
        for row in cached_snapshots
        if isinstance(row, dict) and row.get("snapshot_date")
    }
    category_rows = [
        dict(row) for row in cached_categories if isinstance(row, dict) and row.get("snapshot_date")
    ]
    category_keys = {
        (row.get("snapshot_date"), row.get("source_type"), row.get("category_slug"))
        for row in category_rows
    }

    try:
        cdx_rows, _cdx_source_url = fetch_wordpress_jobs_cdx_rows()
    except Exception as exc:
        eprint(f"WordPress Jobs CDX fetch failed: {exc}")
        cdx_rows = []
    for cdx_row in cdx_rows:
        timestamp = str(cdx_row.get("timestamp") or "")
        snapshot_date = f"{timestamp[0:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
        key = (snapshot_date, "wayback_archive")
        if key in snapshots_by_key:
            continue
        original_url = str(cdx_row.get("original") or WORDPRESS_JOBS_URL)
        replay_url = wayback_replay_url(timestamp, original_url)
        try:
            page_html, _headers = fetch_with_retries(fetch_text, replay_url, f"WordPress Jobs {timestamp}", attempts=4, delay=2.0)
        except Exception as exc:
            eprint(f"WordPress Jobs archive fetch failed for {timestamp}: {exc}")
            continue
        jobs = parse_wordpress_jobs_page(page_html)
        if not jobs:
            eprint(f"WordPress Jobs archive snapshot had no parseable jobs for {timestamp}")
            continue
        snapshot = wordpress_jobs_summary_row(
            snapshot_date,
            "wayback_archive",
            replay_url,
            jobs,
            archive_timestamp=timestamp,
            archive_digest=str(cdx_row.get("digest") or ""),
            archive_original_url=original_url,
        )
        snapshots_by_key[key] = snapshot
        for row in wordpress_jobs_category_rows(snapshot, jobs):
            cat_key = (row.get("snapshot_date"), row.get("source_type"), row.get("category_slug"))
            if cat_key not in category_keys:
                category_rows.append(row)
                category_keys.add(cat_key)
        time.sleep(0.8)

    try:
        live_html, _headers = fetch_text(WORDPRESS_JOBS_URL)
        live_jobs = parse_wordpress_jobs_page(live_html)
    except Exception as exc:
        eprint(f"WordPress Jobs current-page fetch failed: {exc}")
        live_jobs = []
    if live_jobs:
        snapshot_date = live_snapshot_date()
        snapshot = wordpress_jobs_summary_row(snapshot_date, "current_page", WORDPRESS_JOBS_URL, live_jobs)
        snapshots_by_key[(snapshot_date, "current_page")] = snapshot
        category_rows = [
            row for row in category_rows
            if not (row.get("snapshot_date") == snapshot_date and row.get("source_type") == "current_page")
        ]
        category_rows.extend(wordpress_jobs_category_rows(snapshot, live_jobs))

    snapshots = sorted(snapshots_by_key.values(), key=lambda row: (row.get("snapshot_date", ""), row.get("source_type", "")))
    category_rows = sorted(category_rows, key=lambda row: (row.get("snapshot_date", ""), row.get("category", "")))
    if snapshots:
        write_cached_wordpress_jobs_board(snapshots, category_rows)
    return snapshots, category_rows


def vip_case_studies_cache_path():
    return CACHE / "wpvip-case-studies.json"


def read_cached_vip_case_studies():
    path = vip_case_studies_cache_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    return rows if isinstance(rows, list) else []


def write_cached_vip_case_studies(rows):
    CACHE.mkdir(parents=True, exist_ok=True)
    vip_case_studies_cache_path().write_text(
        json.dumps(
            {
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "source_url": WPVIP_CASE_STUDY_API,
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def embedded_terms(item, taxonomy):
    terms = []
    for group in item.get("_embedded", {}).get("wp:term", []):
        if not isinstance(group, list):
            continue
        for term in group:
            if term.get("taxonomy") == taxonomy:
                name = strip_html(term.get("name"))
                if name:
                    terms.append(name)
    return sorted(set(terms))


def fetch_wordpress_vip_case_studies(skip_network=False):
    fallback = read_cached_vip_case_studies()
    if skip_network:
        return fallback
    rows = []
    collected_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    page = 1
    total = ""
    total_pages = ""
    try:
        while True:
            url = f"{WPVIP_CASE_STUDY_API}?{urllib.parse.urlencode({'per_page': 100, 'page': page, '_embed': 1})}"
            data, headers = fetch_json(url)
            if not isinstance(data, list):
                break
            total = headers.get("X-WP-Total", total)
            total_pages = headers.get("X-WP-TotalPages", total_pages)
            for item in data:
                industries = embedded_terms(item, "industry")
                use_cases = embedded_terms(item, "use-case")
                tags = embedded_terms(item, "post_tag")
                rows.append(
                    {
                        "id": item.get("id", ""),
                        "slug": item.get("slug", ""),
                        "title": strip_html((item.get("title") or {}).get("rendered", "")),
                        "link": item.get("link", ""),
                        "date": item.get("date", ""),
                        "modified": item.get("modified", ""),
                        "industries": " | ".join(industries),
                        "use_cases": " | ".join(use_cases),
                        "tags": " | ".join(tags),
                        "source_url": WPVIP_CASE_STUDY_ARCHIVE_URL,
                        "api_url": WPVIP_CASE_STUDY_API,
                        "api_total": total,
                        "api_total_pages": total_pages,
                        "collected_at": collected_at,
                    }
                )
            if not data or (total_pages and page >= int(total_pages)):
                break
            page += 1
        if rows:
            write_cached_vip_case_studies(rows)
        return rows or fallback
    except Exception as exc:
        eprint(f"WordPress VIP case-study fetch failed: {exc}")
        return fallback


def builtwith_cache_path(technology):
    slug = re.sub(r"[^A-Za-z0-9]+", "-", technology).strip("-").lower()
    return CACHE / f"builtwith-{slug}.html"


def fetch_builtwith_page(technology, source_url, skip_network=False):
    cache_path = builtwith_cache_path(technology)
    legacy_cache_path = CACHE / f"builtwith-{technology}.html"
    read_path = cache_path if cache_path.exists() else legacy_cache_path
    if skip_network and cache_path.exists():
        return cache_path.read_text(encoding="utf-8", errors="replace")
    if skip_network and read_path.exists():
        return read_path.read_text(encoding="utf-8", errors="replace")
    if skip_network:
        return ""
    try:
        body, _headers = fetch_text(source_url)
        if len(body) > 1000:
            CACHE.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(body, encoding="utf-8")
        return body
    except Exception as exc:
        eprint(f"BuiltWith fetch failed for {technology}: {exc}")
        if cache_path.exists():
            return cache_path.read_text(encoding="utf-8", errors="replace")
        return ""


def builtwith_count_after_label(body, label):
    pattern = rf">{re.escape(label)}<.*?<div class=\"col-5[^>]*\">.*?<a[^>]*>\s*([\d,]+)\s*</a>"
    match = re.search(pattern, body, re.S)
    return parse_count(match.group(1)) if match else 0


def extract_balanced_json(text, start_index):
    brace_start = text.find("{", start_index)
    if brace_start < 0:
        return ""
    depth = 0
    in_string = False
    escape = False
    for index in range(brace_start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start : index + 1]
    return ""


def parse_builtwith_history_dataset(body):
    start = body.find('dataset: {"source"')
    if start < 0:
        return []
    raw_json = extract_balanced_json(body, start)
    if not raw_json:
        return []
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        return []
    source = data.get("source") or []
    if len(source) < 2:
        return []
    headers = [str(item) for item in source[0]]
    rows = []
    for item in source[1:]:
        if not item or len(item) != len(headers):
            continue
        row = dict(zip(headers, item))
        date_value = row.get("Date")
        if not parse_iso(date_value):
            continue
        rows.append(
            {
                "date": date_value,
                "top_1k": num(row.get("Top 1k")),
                "top_10k": num(row.get("Top 10k")),
                "top_100k": num(row.get("Top 100k")),
                "top_1m": num(row.get("Top 1m")),
                "entire_internet": num(row.get("Entire Internet")),
            }
        )
    return rows


def parse_builtwith_page(technology, category, source_url, body):
    snapshot = {
        "collected_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "technology": technology,
        "category": category,
        "source_url": source_url,
        "total_live": builtwith_count_after_label(body, "Total Live"),
        "new_last_7_days": builtwith_count_after_label(body, "Last 7 Days"),
        "new_last_14_days": builtwith_count_after_label(body, "Last 14 Days"),
        "new_last_month": builtwith_count_after_label(body, "Last Month"),
        "new_last_3_months": builtwith_count_after_label(body, "Last 3 Months"),
        "top_1m": builtwith_count_after_label(body, "Top 1m"),
        "top_100k": builtwith_count_after_label(body, "Top 100k"),
        "top_10k": builtwith_count_after_label(body, "Top 10k"),
        "top_1000": builtwith_count_after_label(body, "Top 1000"),
        "source_note": "BuiltWith public technology page exposes live totals, recent detections, traffic tiers, and a historical live-site dataset.",
    }
    history = []
    for row in parse_builtwith_history_dataset(body):
        row.update(
            {
                "technology": technology,
                "category": category,
                "source_url": source_url,
                "collected_at": snapshot["collected_at"],
            }
        )
        history.append(row)
    return snapshot, history


def fetch_builtwith_technology_signals(skip_network=False):
    fallback_snapshots = read_existing_table("builtwith_technology_snapshots")
    fallback_history = read_existing_table("builtwith_technology_history")
    snapshots = []
    history_rows = []
    for config in BUILTWITH_TECHNOLOGIES:
        body = fetch_builtwith_page(config["technology"], config["source_url"], skip_network)
        if not body:
            continue
        snapshot, history = parse_builtwith_page(config["technology"], config["category"], config["source_url"], body)
        if snapshot.get("total_live") or history:
            snapshots.append(snapshot)
            history_rows.extend(history)
    if not snapshots:
        snapshots = fallback_snapshots
    if not history_rows:
        history_rows = fallback_history
    return snapshots, history_rows


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


def live_snapshot_date():
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def parse_wporg_datetime(value):
    raw = strip_html(value)
    if not raw:
        return None
    parsed = parse_iso(raw)
    if parsed:
        return parsed
    cleaned = re.sub(r"\s+GMT$", "", raw, flags=re.I).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).upper().replace(" PM", "PM").replace(" AM", "AM")
    for fmt in ("%Y-%m-%d %I:%M%p", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = dt.datetime.strptime(cleaned, fmt)
            return parsed.replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    return None


def directory_query_url(api_base, action, browse, page, per_page):
    params = [
        ("action", action),
        ("request[browse]", browse),
        ("request[page]", page),
        ("request[per_page]", per_page),
        ("request[fields][description]", 0),
        ("request[fields][sections]", 0),
        ("request[fields][screenshots]", 0),
        ("request[fields][tags]", 0),
    ]
    return f"{api_base}?{urllib.parse.urlencode(params)}"


def fetch_directory_page(kind, browse, page, per_page=100):
    if kind == "plugin":
        url = directory_query_url(PLUGIN_INFO_API, "query_plugins", browse, page, per_page)
        data, _headers = fetch_json(url)
        return data.get("plugins", []), data.get("info", {}), url
    url = directory_query_url(THEME_INFO_API, "query_themes", browse, page, per_page)
    data, _headers = fetch_json(url)
    return data.get("themes", []), data.get("info", {}), url


def wporg_author_name(value):
    if isinstance(value, dict):
        for key in ("display_name", "name", "author", "user_nicename"):
            if value.get(key):
                return strip_html(value.get(key))
        return ""
    return strip_html(value)


def wporg_author_profile(item):
    author = item.get("author")
    if isinstance(author, dict):
        return str(author.get("profile") or author.get("url") or "")
    return str(item.get("author_profile") or "")


def normalize_plugin_item(item, browse, page, rank, source_url):
    added = str(item.get("added") or "")
    last_updated = str(item.get("last_updated") or "")
    last_updated_at = parse_wporg_datetime(last_updated)
    return {
        "snapshot_date": live_snapshot_date(),
        "browse": browse,
        "page": page,
        "rank": rank,
        "slug": str(item.get("slug") or ""),
        "name": strip_html(item.get("name")),
        "author_name": wporg_author_name(item.get("author")),
        "author_profile": wporg_author_profile(item),
        "added": added,
        "last_updated": last_updated,
        "last_updated_date": last_updated_at.date().isoformat() if last_updated_at else "",
        "active_installs": num(item.get("active_installs")),
        "downloaded": num(item.get("downloaded")),
        "rating": num(item.get("rating")),
        "num_ratings": num(item.get("num_ratings")),
        "requires": str(item.get("requires") or ""),
        "requires_php": str(item.get("requires_php") or ""),
        "tested": str(item.get("tested") or ""),
        "version": str(item.get("version") or ""),
        "plugin_url": f"https://wordpress.org/plugins/{item.get('slug')}/" if item.get("slug") else "",
        "source_url": source_url,
    }


def major_plugin_cache_path():
    return CACHE / "major-plugin-install-snapshot.json"


def read_cached_major_plugin_snapshot():
    path = major_plugin_cache_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    return rows if isinstance(rows, list) else []


def write_cached_major_plugin_snapshot(rows):
    CACHE.mkdir(parents=True, exist_ok=True)
    major_plugin_cache_path().write_text(
        json.dumps(
            {
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "source_url": PLUGIN_INFO_API,
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def plugin_information_url(slug):
    params = [
        ("action", "plugin_information"),
        ("request[slug]", slug),
        ("request[fields][description]", 0),
        ("request[fields][sections]", 0),
        ("request[fields][screenshots]", 0),
        ("request[fields][tags]", 0),
        ("request[fields][versions]", 0),
        ("request[fields][contributors]", 0),
        ("request[fields][active_installs]", 1),
        ("request[fields][downloaded]", 1),
        ("request[fields][last_updated]", 1),
        ("request[fields][short_description]", 1),
    ]
    return f"{PLUGIN_INFO_API}?{urllib.parse.urlencode(params)}"


def normalize_major_plugin_info(item, slug, rank, source_url):
    last_updated = str(item.get("last_updated") or "")
    last_updated_at = parse_wporg_datetime(last_updated)
    return {
        "snapshot_date": live_snapshot_date(),
        "rank": rank,
        "slug": str(item.get("slug") or slug),
        "name": strip_html(item.get("name") or slug),
        "author_name": wporg_author_name(item.get("author")),
        "author_profile": wporg_author_profile(item),
        "active_installs": num(item.get("active_installs")),
        "downloaded": num(item.get("downloaded")),
        "rating": num(item.get("rating")),
        "num_ratings": num(item.get("num_ratings")),
        "support_threads": num(item.get("support_threads")),
        "support_threads_resolved": num(item.get("support_threads_resolved")),
        "last_updated": last_updated,
        "last_updated_date": last_updated_at.date().isoformat() if last_updated_at else "",
        "version": str(item.get("version") or ""),
        "requires": str(item.get("requires") or ""),
        "requires_php": str(item.get("requires_php") or ""),
        "tested": str(item.get("tested") or ""),
        "plugin_url": f"https://wordpress.org/plugins/{item.get('slug') or slug}/",
        "source_url": source_url,
    }


def fetch_major_plugin_install_snapshot(skip_network=False):
    cached_rows = read_cached_major_plugin_snapshot()
    if skip_network and cached_rows:
        return cached_rows
    if skip_network:
        return []

    rows_by_slug = {
        row.get("slug"): dict(row)
        for row in cached_rows
        if isinstance(row, dict) and row.get("slug")
    }
    for index, slug in enumerate(MAJOR_PLUGIN_SLUGS, start=1):
        source_url = plugin_information_url(slug)
        try:
            item, _headers = fetch_json(source_url)
        except Exception as exc:
            eprint(f"Major plugin fetch failed for {slug}: {exc}")
            continue
        if not isinstance(item, dict) or item.get("error"):
            eprint(f"Major plugin fetch returned no plugin info for {slug}")
            continue
        rows_by_slug[slug] = normalize_major_plugin_info(item, slug, index, source_url)
        time.sleep(0.08)
    rows = [rows_by_slug[slug] for slug in MAJOR_PLUGIN_SLUGS if slug in rows_by_slug]
    if rows:
        write_cached_major_plugin_snapshot(rows)
    return rows


def major_plugin_install_history_cache_path():
    return CACHE / "major-plugin-install-history.json"


def read_cached_major_plugin_install_history():
    path = major_plugin_install_history_cache_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    return rows if isinstance(rows, list) else []


def write_cached_major_plugin_install_history(rows):
    CACHE.mkdir(parents=True, exist_ok=True)
    major_plugin_install_history_cache_path().write_text(
        json.dumps(
            {
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "source_url": WAYBACK_CDX_API,
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def wayback_cdx_url(slug):
    params = [
        ("url", f"wordpress.org/plugins/{slug}/"),
        ("from", str(MAJOR_PLUGIN_ARCHIVE_START_YEAR)),
        ("to", str(END.year - 1)),
        ("matchType", "exact"),
        ("filter", "statuscode:200"),
        ("filter", "mimetype:text/html"),
        ("collapse", "timestamp:4"),
        ("output", "json"),
        ("fl", "timestamp,original,digest"),
    ]
    return f"{WAYBACK_CDX_API}?{urllib.parse.urlencode(params)}"


def wayback_replay_url(timestamp, original_url):
    return f"{WAYBACK_WEB_ROOT}/{timestamp}id_/{original_url}"


def parse_active_install_bucket(value):
    raw = strip_html(value).lower().replace("\xa0", " ")
    raw = re.sub(r"\s+", " ", raw).strip()
    match = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*\+?\s*(billion|million|thousand|k|m)?", raw)
    if not match:
        return None
    number_text = match.group(1)
    if "," in number_text and "." not in number_text:
        if re.search(r",\d{3}(?:\D|$)", number_text):
            number_text = number_text.replace(",", "")
        else:
            number_text = number_text.replace(",", ".")
    number = float(number_text)
    unit = match.group(2) or ""
    multiplier = 1
    if unit in {"billion"}:
        multiplier = 1_000_000_000
    elif unit in {"million", "m"}:
        multiplier = 1_000_000
    elif unit in {"thousand", "k"}:
        multiplier = 1_000
    return int(number * multiplier)


def parse_plugin_page_active_installs(page_html):
    patterns = [
        r"Active installations:\s*<strong>\s*([^<]+)\s*</strong>",
        r"<li[^>]*>\s*Active installations:\s*<strong>\s*([^<]+)\s*</strong>",
        r"Active installations:\s*([^<\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, page_html, flags=re.I | re.S)
        if not match:
            continue
        bucket = strip_html(match.group(1))
        installs = parse_active_install_bucket(bucket)
        if installs is not None:
            return bucket, installs
    text = strip_html(page_html)
    match = re.search(r"Active installations:\s*([0-9][0-9.,]*\s*\+?\s*(?:billion|million|thousand|k|m)?)", text, flags=re.I)
    if match:
        bucket = match.group(1)
        installs = parse_active_install_bucket(bucket)
        if installs is not None:
            return bucket, installs
    return "", None


def fetch_wayback_cdx_rows(slug):
    url = wayback_cdx_url(slug)
    payload, _headers = fetch_with_retries(fetch_json, url, f"Wayback CDX {slug}", attempts=4, delay=2.0)
    if not isinstance(payload, list) or len(payload) < 2:
        return [], url
    header = payload[0]
    rows = []
    for item in payload[1:]:
        if not isinstance(item, list) or len(item) != len(header):
            continue
        row = dict(zip(header, item))
        timestamp = str(row.get("timestamp") or "")
        if not re.match(r"^\d{14}$", timestamp):
            continue
        rows.append(row)
    return rows, url


def current_major_plugin_install_history_rows(major_plugin_rows):
    rows = []
    collected_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    for index, row in enumerate(major_plugin_rows or [], start=1):
        slug = str(row.get("slug") or "")
        if not slug:
            continue
        installs = num(row.get("active_installs"))
        rows.append(
            {
                "snapshot_date": str(row.get("snapshot_date") or live_snapshot_date()),
                "year": str(row.get("snapshot_date") or live_snapshot_date())[:4],
                "slug": slug,
                "plugin_name": MAJOR_PLUGIN_DISPLAY_NAMES.get(slug, str(row.get("name") or slug)),
                "rank": row.get("rank") or index,
                "active_installs": installs,
                "active_install_bucket": compact(installs),
                "source_type": "current_api",
                "source": "WordPress.org plugin information API current snapshot",
                "source_url": str(row.get("source_url") or plugin_information_url(slug)),
                "archive_timestamp": "",
                "archive_original_url": "",
                "archive_digest": "",
                "collected_at": collected_at,
            }
        )
    return rows


def fetch_major_plugin_install_history(major_plugin_rows=None, skip_network=False):
    cached_rows = read_cached_major_plugin_install_history()
    if skip_network and cached_rows:
        return cached_rows
    if skip_network:
        return current_major_plugin_install_history_rows(major_plugin_rows or [])

    name_by_slug = {
        str(row.get("slug") or ""): str(row.get("name") or row.get("slug") or "")
        for row in (major_plugin_rows or [])
        if row.get("slug")
    }
    rows_by_key = {
        (str(row.get("slug") or ""), str(row.get("archive_timestamp") or ""), str(row.get("source_type") or "")): dict(row)
        for row in cached_rows
        if isinstance(row, dict) and row.get("slug")
    }
    collected_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    for index, slug in enumerate(MAJOR_PLUGIN_SLUGS, start=1):
        try:
            cdx_rows, cdx_source_url = fetch_wayback_cdx_rows(slug)
        except Exception as exc:
            eprint(f"Wayback CDX fetch failed for {slug}: {exc}")
            continue
        for cdx_row in cdx_rows:
            timestamp = str(cdx_row.get("timestamp") or "")
            key = (slug, timestamp, "wayback_archive")
            if key in rows_by_key and rows_by_key[key].get("active_installs"):
                continue
            original_url = str(cdx_row.get("original") or f"https://wordpress.org/plugins/{slug}/")
            replay_url = wayback_replay_url(timestamp, original_url)
            try:
                page_html, _headers = fetch_with_retries(fetch_text, replay_url, f"Wayback plugin page {slug} {timestamp}", attempts=4, delay=2.0)
            except Exception as exc:
                eprint(f"Wayback plugin page fetch failed for {slug} {timestamp}: {exc}")
                continue
            bucket, installs = parse_plugin_page_active_installs(page_html)
            if installs is None:
                eprint(f"Wayback plugin page had no active install bucket for {slug} {timestamp}")
                continue
            snapshot_date = f"{timestamp[0:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
            rows_by_key[key] = {
                "snapshot_date": snapshot_date,
                "year": timestamp[:4],
                "slug": slug,
                "plugin_name": MAJOR_PLUGIN_DISPLAY_NAMES.get(slug, name_by_slug.get(slug, slug)),
                "rank": index,
                "active_installs": installs,
                "active_install_bucket": bucket,
                "source_type": "wayback_archive",
                "source": "Internet Archive Wayback Machine archived WordPress.org plugin page",
                "source_url": cdx_source_url,
                "archive_timestamp": timestamp,
                "archive_original_url": original_url,
                "archive_digest": str(cdx_row.get("digest") or ""),
                "archive_replay_url": replay_url,
                "collected_at": collected_at,
            }
            time.sleep(0.6)
        time.sleep(1.0)

    for row in current_major_plugin_install_history_rows(major_plugin_rows or []):
        rows_by_key[(row["slug"], "", "current_api")] = row

    rows = sorted(
        rows_by_key.values(),
        key=lambda row: (num(row.get("rank")), str(row.get("slug") or ""), str(row.get("snapshot_date") or ""), str(row.get("source_type") or "")),
    )
    if rows:
        write_cached_major_plugin_install_history(rows)
    return rows


def major_plugin_download_cache_path():
    return CACHE / "major-plugin-download-history.json"


def read_cached_major_plugin_download_history():
    path = major_plugin_download_cache_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    return rows if isinstance(rows, list) else []


def write_cached_major_plugin_download_history(rows):
    CACHE.mkdir(parents=True, exist_ok=True)
    major_plugin_download_cache_path().write_text(
        json.dumps(
            {
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                "source_url": PLUGIN_DOWNLOADS_API,
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def plugin_downloads_url(slug, limit=365):
    params = urllib.parse.urlencode({"slug": slug, "limit": limit})
    return f"{PLUGIN_DOWNLOADS_API}?{params}"


def fetch_major_plugin_download_history(major_plugin_rows=None, skip_network=False):
    cached_rows = read_cached_major_plugin_download_history()
    if skip_network and cached_rows:
        return cached_rows, aggregate_major_plugin_downloads_quarterly(cached_rows)
    if skip_network:
        return [], []

    name_by_slug = {
        str(row.get("slug") or ""): str(row.get("name") or row.get("slug") or "")
        for row in (major_plugin_rows or [])
        if row.get("slug")
    }
    rows_by_key = {
        (row.get("slug"), row.get("date")): dict(row)
        for row in cached_rows
        if isinstance(row, dict) and row.get("slug") and row.get("date")
    }
    collected_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    for index, slug in enumerate(MAJOR_PLUGIN_SLUGS, start=1):
        source_url = plugin_downloads_url(slug)
        try:
            payload, _headers = fetch_json(source_url)
        except Exception as exc:
            eprint(f"Major plugin download-history fetch failed for {slug}: {exc}")
            continue
        if not isinstance(payload, dict):
            continue
        for date_value, downloads in payload.items():
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(date_value)):
                continue
            rows_by_key[(slug, date_value)] = {
                "date": date_value,
                "quarter": quarter_start(date_value) or "",
                "slug": slug,
                "plugin_name": name_by_slug.get(slug, slug),
                "rank": index,
                "downloads": num(downloads),
                "source": "WordPress.org plugin daily download stats",
                "source_url": PLUGIN_DOWNLOADS_DOCS_URL,
                "api_url": source_url,
                "collected_at": collected_at,
            }
        time.sleep(0.08)
    rows = [
        rows_by_key[(slug, date_value)]
        for slug in MAJOR_PLUGIN_SLUGS
        for _row_slug, date_value in sorted(rows_by_key)
        if _row_slug == slug
    ]
    if rows:
        write_cached_major_plugin_download_history(rows)
    return rows, aggregate_major_plugin_downloads_quarterly(rows)


def aggregate_major_plugin_downloads_quarterly(daily_rows):
    grouped = defaultdict(list)
    name_by_slug = {}
    rank_by_slug = {}
    for row in daily_rows:
        q = quarter_start(row.get("date"))
        slug = row.get("slug")
        if q and slug:
            grouped[(slug, q)].append(row)
            if row.get("plugin_name"):
                name_by_slug[slug] = row.get("plugin_name")
            if row.get("rank"):
                rank_by_slug[slug] = row.get("rank")
    collected_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    rows = []
    for (slug, quarter), items in sorted(grouped.items()):
        rows.append(
            {
                "quarter": quarter,
                "label": quarter_label(quarter),
                "slug": slug,
                "plugin_name": name_by_slug.get(slug, slug),
                "rank": rank_by_slug.get(slug, ""),
                "downloads": sum(num(item.get("downloads")) for item in items),
                "days_covered": len({item.get("date") for item in items if item.get("date")}),
                "source": "WordPress.org plugin daily download stats, aggregated quarterly",
                "source_url": PLUGIN_DOWNLOADS_DOCS_URL,
                "collected_at": collected_at,
            }
        )
    return rows


def normalize_theme_item(item, browse, page, rank, source_url):
    return {
        "snapshot_date": live_snapshot_date(),
        "browse": browse,
        "page": page,
        "rank": rank,
        "slug": str(item.get("slug") or ""),
        "name": strip_html(item.get("name")),
        "author_name": wporg_author_name(item.get("author")),
        "author_profile": wporg_author_profile(item),
        "rating": num(item.get("rating")),
        "num_ratings": num(item.get("num_ratings")),
        "requires": str(item.get("requires") or ""),
        "requires_php": str(item.get("requires_php") or ""),
        "version": str(item.get("version") or ""),
        "is_commercial": str(item.get("is_commercial") or ""),
        "is_community": str(item.get("is_community") or ""),
        "theme_url": f"https://wordpress.org/themes/{item.get('slug')}/" if item.get("slug") else "",
        "preview_url": str(item.get("preview_url") or ""),
        "source_url": source_url,
    }


def fetch_directory_activity(skip_network=False):
    if skip_network:
        return [], [], []

    today = dt.datetime.now(dt.timezone.utc).date()
    cutoff_30 = today - dt.timedelta(days=30)
    cutoff_90 = today - dt.timedelta(days=90)
    stale_cutoff = today - dt.timedelta(days=730)
    snapshot_date = live_snapshot_date()
    plugin_rows = []
    theme_rows = []
    info_by_browse = {}
    pages_fetched = defaultdict(int)
    complete_90d = {"new": False, "updated": False}

    plugin_limits = {"new": 50, "updated": 80, "popular": 10}
    for browse, max_pages in plugin_limits.items():
        for page in range(1, max_pages + 1):
            try:
                items, info, source_url = fetch_directory_page("plugin", browse, page)
            except Exception as exc:
                eprint(f"plugin directory activity fetch failed for {browse} page {page}: {exc}")
                break
            if page == 1:
                info_by_browse[f"plugin_{browse}"] = info
            if not items:
                complete_90d[browse] = True
                break
            pages_fetched[f"plugin_{browse}"] = page
            oldest_date = None
            for offset, item in enumerate(items, start=1):
                rank = (page - 1) * 100 + offset
                row = normalize_plugin_item(item, browse, page, rank, source_url)
                plugin_rows.append(row)
                date_value = row["added"] if browse == "new" else row["last_updated_date"]
                parsed = parse_iso(date_value)
                if parsed and (oldest_date is None or parsed.date() < oldest_date):
                    oldest_date = parsed.date()
            if browse in {"new", "updated"} and oldest_date and oldest_date < cutoff_90:
                complete_90d[browse] = True
                break
            time.sleep(0.04)

    for browse in ("new", "updated", "popular"):
        for page in range(1, 4):
            try:
                items, info, source_url = fetch_directory_page("theme", browse, page)
            except Exception as exc:
                eprint(f"theme directory activity fetch failed for {browse} page {page}: {exc}")
                break
            if page == 1:
                info_by_browse[f"theme_{browse}"] = info
            if not items:
                break
            pages_fetched[f"theme_{browse}"] = page
            for offset, item in enumerate(items, start=1):
                rank = (page - 1) * 100 + offset
                theme_rows.append(normalize_theme_item(item, browse, page, rank, source_url))
            time.sleep(0.04)

    new_plugins = [row for row in plugin_rows if row.get("browse") == "new"]
    updated_plugins = [row for row in plugin_rows if row.get("browse") == "updated"]
    popular_plugins = [row for row in plugin_rows if row.get("browse") == "popular"]

    def date_in_window(row, key, cutoff):
        parsed = parse_iso(row.get(key))
        return bool(parsed and parsed.date() >= cutoff)

    stale_popular = [
        row
        for row in popular_plugins
        if parse_iso(row.get("last_updated_date")) and parse_iso(row.get("last_updated_date")).date() < stale_cutoff
    ]
    snapshot = {
        "snapshot_date": snapshot_date,
        "plugin_new_results": num(info_by_browse.get("plugin_new", {}).get("results")),
        "plugin_updated_results": num(info_by_browse.get("plugin_updated", {}).get("results")),
        "plugin_popular_results": num(info_by_browse.get("plugin_popular", {}).get("results")),
        "plugins_added_30d": sum(1 for row in new_plugins if date_in_window(row, "added", cutoff_30)),
        "plugins_added_90d": sum(1 for row in new_plugins if date_in_window(row, "added", cutoff_90)),
        "plugins_added_pages_fetched": pages_fetched.get("plugin_new", 0),
        "plugins_added_complete_90d": int(complete_90d.get("new", False)),
        "plugins_updated_30d": sum(1 for row in updated_plugins if date_in_window(row, "last_updated_date", cutoff_30)),
        "plugins_updated_90d": sum(1 for row in updated_plugins if date_in_window(row, "last_updated_date", cutoff_90)),
        "plugins_updated_pages_fetched": pages_fetched.get("plugin_updated", 0),
        "plugins_updated_complete_90d": int(complete_90d.get("updated", False)),
        "popular_plugin_sample_size": len(popular_plugins),
        "popular_plugin_stale_2y": len(stale_popular),
        "popular_plugin_stale_2y_active_installs": sum(num(row.get("active_installs")) for row in stale_popular),
        "theme_new_results": num(info_by_browse.get("theme_new", {}).get("results")),
        "theme_updated_results": num(info_by_browse.get("theme_updated", {}).get("results")),
        "theme_popular_results": num(info_by_browse.get("theme_popular", {}).get("results")),
        "theme_new_sample_size": sum(1 for row in theme_rows if row.get("browse") == "new"),
        "theme_updated_sample_size": sum(1 for row in theme_rows if row.get("browse") == "updated"),
        "theme_popular_sample_size": sum(1 for row in theme_rows if row.get("browse") == "popular"),
        "source_url": PLUGIN_INFO_API,
        "theme_source_url": THEME_INFO_API,
    }
    return [snapshot], plugin_rows, theme_rows


def derive_plugin_maintenance_tables(plugin_rows):
    popular_plugins = [row for row in plugin_rows if row.get("browse") == "popular"]
    if not popular_plugins:
        return [], []
    snapshot_date = max([row.get("snapshot_date", "") for row in popular_plugins if row.get("snapshot_date")] or [live_snapshot_date()])
    snapshot_at = parse_iso(snapshot_date) or END
    age_rows = []
    unknown_last_updated = 0
    for row in popular_plugins:
        updated_at = parse_iso(row.get("last_updated_date"))
        if not updated_at:
            unknown_last_updated += 1
            continue
        days_since_update = max(0, int((snapshot_at - updated_at).total_seconds() // 86400))
        enriched = dict(row)
        enriched["days_since_update"] = days_since_update
        age_rows.append(enriched)

    def count_stale(days):
        return [row for row in age_rows if num(row.get("days_since_update")) >= days]

    stale_1y = count_stale(365)
    stale_2y = count_stale(730)
    stale_3y = count_stale(1095)
    stale_5y = count_stale(1825)
    total_installs = sum(num(row.get("active_installs")) for row in popular_plugins)
    stale_2y_installs = sum(num(row.get("active_installs")) for row in stale_2y)
    ages = [num(row.get("days_since_update")) for row in age_rows]
    summary = [
        {
            "snapshot_date": snapshot_date,
            "sample": "popular_plugins",
            "sample_size": len(popular_plugins),
            "known_last_updated": len(age_rows),
            "unknown_last_updated": unknown_last_updated,
            "stale_1y_count": len(stale_1y),
            "stale_2y_count": len(stale_2y),
            "stale_3y_count": len(stale_3y),
            "stale_5y_count": len(stale_5y),
            "active_installs_total": total_installs,
            "stale_2y_active_installs": stale_2y_installs,
            "stale_2y_sample_share_pct": round(len(stale_2y) / len(popular_plugins) * 100, 2) if popular_plugins else 0,
            "stale_2y_active_install_share_pct": round(stale_2y_installs / total_installs * 100, 2) if total_installs else 0,
            "median_days_since_update": round(median(ages), 2) if ages else "",
            "p90_days_since_update": round(percentile(ages, 0.90), 2) if ages else "",
            "source_note": "Derived from the WordPress.org popular plugin browse sample. Stale means last updated at least two years before the snapshot date.",
        }
    ]
    detail = []
    for row in sorted(stale_2y, key=lambda item: num(item.get("active_installs")), reverse=True):
        detail.append(
            {
                "snapshot_date": snapshot_date,
                "slug": row.get("slug", ""),
                "name": row.get("name", ""),
                "rank": row.get("rank", ""),
                "active_installs": row.get("active_installs", ""),
                "last_updated_date": row.get("last_updated_date", ""),
                "days_since_update": row.get("days_since_update", ""),
                "requires": row.get("requires", ""),
                "requires_php": row.get("requires_php", ""),
                "tested": row.get("tested", ""),
                "plugin_url": row.get("plugin_url", ""),
                "source_url": row.get("source_url", ""),
                "source_note": "Popular plugin browse sample rows whose last update is at least two years before the snapshot date.",
            }
        )
    return summary, detail


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


def parse_attendee_estimate(value):
    raw = strip_html(value)
    if not raw:
        return 0
    numbers = [int(match.replace(",", "")) for match in re.findall(r"\d[\d,]*", raw)]
    if not numbers:
        return 0
    if len(numbers) >= 2 and re.search(r"[-–—]| to ", raw, flags=re.I):
        return round(sum(numbers[:2]) / 2)
    return numbers[0]


def boolish(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def derive_wordcamp_yearly(wordcamps):
    buckets = defaultdict(
        lambda: {
            "events": 0,
            "events_with_attendance_estimate": 0,
            "anticipated_attendance": 0,
            "virtual_events": 0,
            "regions": set(),
        }
    )
    for row in wordcamps:
        started = parse_iso(row.get("start_date"))
        if not started:
            continue
        year = f"{started.year:04d}-01-01"
        bucket = buckets[year]
        bucket["events"] += 1
        try:
            raw = json.loads(row.get("raw_json") or "{}")
        except json.JSONDecodeError:
            raw = {}
        estimate = parse_attendee_estimate(raw.get("Number of Anticipated Attendees"))
        if estimate:
            bucket["events_with_attendance_estimate"] += 1
            bucket["anticipated_attendance"] += estimate
        if boolish(raw.get("Virtual event only")):
            bucket["virtual_events"] += 1
        region = strip_html(raw.get("Host region"))
        if region:
            bucket["regions"].add(region)
    rows = []
    for year, values in sorted(buckets.items()):
        events = values["events"]
        with_estimate = values["events_with_attendance_estimate"]
        rows.append(
            {
                "year": year,
                "label": str(parse_iso(year).year),
                "events": events,
                "events_with_attendance_estimate": with_estimate,
                "attendance_estimate_coverage_pct": round(with_estimate / events * 100, 2) if events else 0,
                "anticipated_attendance": values["anticipated_attendance"],
                "virtual_events": values["virtual_events"],
                "in_person_or_unspecified_events": events - values["virtual_events"],
                "regions": len(values["regions"]),
                "source": "WordCamp Central API Number of Anticipated Attendees field",
            }
        )
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
    fields = "id,date,modified,author,link,title,categories,tags"
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
                    "categories": json.dumps(item.get("categories") or []),
                    "tags": json.dumps(item.get("tags") or []),
                    "raw_json": json.dumps(item, ensure_ascii=True, sort_keys=True),
                }
            )
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.05)
    return rows


def make_commenter_key(item):
    author = str(item.get("author") or "").strip()
    if author and author != "0":
        return f"user:{author}"
    author_name = strip_html(item.get("author_name")).lower()
    author_url = str(item.get("author_url") or "").strip().lower()
    if author_url:
        return f"url:{author_url}"
    if author_name:
        return f"name:{author_name}"
    return "anonymous"


def fetch_make_core_comments(skip_network=False):
    if skip_network:
        return []
    rows = []
    page = 1
    total_pages = None
    fields = "id,date,post,parent,author,author_name,author_url,link"
    while True:
        params = urllib.parse.urlencode({"per_page": 100, "page": page, "_fields": fields})
        try:
            data, headers = fetch_json(f"{MAKE_CORE_COMMENTS_API}?{params}")
        except urllib.error.HTTPError as exc:
            if exc.code == 400 and page > 1:
                break
            raise
        if total_pages is None:
            total_pages = int(headers.get("X-WP-TotalPages", "1") or 1)
        for item in data:
            commenter_key = make_commenter_key(item)
            rows.append(
                {
                    "id": str(item.get("id", "")),
                    "date": str(item.get("date", "")),
                    "post": str(item.get("post", "")),
                    "parent": str(item.get("parent", "")),
                    "author": str(item.get("author", "")),
                    "author_name": strip_html(item.get("author_name")),
                    "author_url": str(item.get("author_url") or ""),
                    "commenter_key": commenter_key,
                    "is_registered_author": "1" if str(item.get("author") or "").strip() not in {"", "0"} else "0",
                    "link": str(item.get("link", "")),
                    "raw_json": json.dumps(item, ensure_ascii=True, sort_keys=True),
                    "source_url": MAKE_CORE_COMMENTS_API,
                }
            )
        if page >= total_pages:
            break
        if page % 50 == 0:
            eprint(f"make/core comments page {page}/{total_pages}")
        page += 1
        time.sleep(0.05)
    return rows


def derive_make_core_comment_quarterly(comments):
    buckets = defaultdict(lambda: {"comments": 0, "commenters": set(), "registered": 0, "anonymous": 0, "posts": set()})
    for row in comments:
        q = quarter_start(row.get("date"))
        if not q:
            continue
        bucket = buckets[q]
        bucket["comments"] += 1
        bucket["commenters"].add(row.get("commenter_key") or row.get("author_name") or "anonymous")
        bucket["posts"].add(str(row.get("post", "")))
        if str(row.get("is_registered_author")) == "1":
            bucket["registered"] += 1
        else:
            bucket["anonymous"] += 1
    return [
        {
            "quarter": quarter,
            "label": quarter_label(quarter),
            "comments": values["comments"],
            "unique_commenters": len(values["commenters"]),
            "registered_author_comments": values["registered"],
            "guest_or_anonymous_comments": values["anonymous"],
            "posts_commented_on": len(values["posts"]),
        }
        for quarter, values in sorted(buckets.items())
    ]


def parse_translate_locale_cards(body, source_url):
    rows = []
    for match in re.finditer(r'<div class="locale percent-(\d+)">(.*?)(?=<div class="locale percent-|\Z)', body, re.S):
        percent = int(match.group(1))
        block = match.group(2)
        english_match = re.search(r'<li class="english"><a href="([^"]+)">(.*?)</a></li>', block, re.S)
        native_match = re.search(r'<li class="native"><a href="[^"]+">(.*?)</a></li>', block, re.S)
        code_match = re.search(r'<li class="code"><a href="[^"]+">(.*?)</a></li>', block, re.S)
        contributor_match = re.search(r'<div class="contributors">.*?<br\s*/>\s*([\d,]+)\s*</a>', block, re.S)
        if not english_match or not code_match:
            continue
        locale_path = english_match.group(1)
        rows.append(
            {
                "snapshot_date": END.date().isoformat(),
                "locale": strip_html(english_match.group(2)),
                "native_name": strip_html(native_match.group(1)) if native_match else "",
                "locale_code": strip_html(code_match.group(1)),
                "contributors": parse_count(contributor_match.group(1)) if contributor_match else 0,
                "percent_complete": percent,
                "locale_url": urllib.parse.urljoin(source_url, locale_path),
                "team_url": f"https://make.wordpress.org/polyglots/teams/?locale={strip_html(code_match.group(1))}",
                "source_url": source_url,
            }
        )
    return rows


def parse_translate_core_dev_table(body, source_url):
    match = re.search(r'<table class="gp-table translation-sets">(.*?)</table>', body, re.S)
    if not match:
        return []
    table = match.group(1)
    rows = []
    for row_html in re.findall(r"<tr>(.*?)</tr>", table, re.S):
        href_match = re.search(r'<a href="(/projects/wp/dev/([^/]+)/default/)">(.*?)</a>', row_html, re.S)
        if not href_match:
            continue
        percent_match = re.search(r'<td class="stats percent">\s*([^<]+)\s*</td>', row_html, re.S)

        def count_for(cls):
            cls_match = re.search(rf'<td class="stats {cls}"[^>]*>.*?<a [^>]*>(.*?)</a>', row_html, re.S)
            return parse_count(cls_match.group(1)) if cls_match else 0

        rows.append(
            {
                "snapshot_date": END.date().isoformat(),
                "locale": strip_html(href_match.group(3)),
                "locale_code": href_match.group(2),
                "percent_complete": parse_percent(strip_html(percent_match.group(1))) if percent_match else 0,
                "translated": count_for("translated"),
                "fuzzy": count_for("fuzzy"),
                "untranslated": count_for("untranslated"),
                "waiting": count_for("waiting"),
                "locale_url": urllib.parse.urljoin(source_url, href_match.group(1)),
                "source_url": source_url,
            }
        )
    return rows


def fetch_translation_snapshots(skip_network=False):
    if skip_network:
        return [], [], []
    locale_rows = []
    core_rows = []
    try:
        locale_body, _headers = fetch_text(TRANSLATE_LOCALES_URL)
        locale_rows = parse_translate_locale_cards(locale_body, TRANSLATE_LOCALES_URL)
    except Exception as exc:
        eprint(f"translate locale fetch failed: {exc}")
    try:
        core_body, _headers = fetch_text(TRANSLATE_CORE_DEV_URL)
        core_rows = parse_translate_core_dev_table(core_body, TRANSLATE_CORE_DEV_URL)
    except Exception as exc:
        eprint(f"translate Core dev fetch failed: {exc}")
    snapshots = []
    if locale_rows or core_rows:
        snapshots.append(
            {
                "snapshot_date": END.date().isoformat(),
                "locale_count": len(locale_rows),
                "locale_contributor_profile_sum": sum(num(row.get("contributors")) for row in locale_rows),
                "locales_90_plus": sum(1 for row in locale_rows if num(row.get("percent_complete")) >= 90),
                "locales_50_to_89": sum(1 for row in locale_rows if 50 <= num(row.get("percent_complete")) < 90),
                "locales_under_50": sum(1 for row in locale_rows if num(row.get("percent_complete")) < 50),
                "core_dev_locale_count": len(core_rows),
                "core_dev_100": sum(1 for row in core_rows if float(row.get("percent_complete") or 0) >= 100),
                "core_dev_90_plus": sum(1 for row in core_rows if float(row.get("percent_complete") or 0) >= 90),
                "core_dev_50_to_89": sum(1 for row in core_rows if 50 <= float(row.get("percent_complete") or 0) < 90),
                "core_dev_under_50": sum(1 for row in core_rows if float(row.get("percent_complete") or 0) < 50),
                "core_dev_waiting_strings": sum(num(row.get("waiting")) for row in core_rows),
                "source_url": TRANSLATE_LOCALES_URL,
                "core_dev_source_url": TRANSLATE_CORE_DEV_URL,
            }
        )
    return snapshots, locale_rows, core_rows


def fetch_make_core_dev_note_tags(skip_network=False):
    if skip_network:
        return []
    rows_by_id = {}
    page = 1
    total_pages = None
    fields = "id,count,name,slug,link"
    while True:
        params = urllib.parse.urlencode({"per_page": 100, "page": page, "search": "dev-notes", "_fields": fields})
        try:
            data, headers = fetch_json(f"{MAKE_CORE_TAGS_API}?{params}")
        except urllib.error.HTTPError as exc:
            if exc.code == 400 and page > 1:
                break
            raise
        if total_pages is None:
            total_pages = int(headers.get("X-WP-TotalPages", "1") or 1)
        for item in data:
            slug = str(item.get("slug") or "")
            if not re.match(r"^dev-notes(?:[-0-9]|$)", slug):
                continue
            rows_by_id[str(item.get("id", ""))] = {
                "id": str(item.get("id", "")),
                "slug": slug,
                "name": html.unescape(str(item.get("name") or "")),
                "count": str(item.get("count", "")),
                "link": str(item.get("link", "")),
                "source_url": MAKE_CORE_TAGS_API,
            }
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.05)
    return sorted(rows_by_id.values(), key=lambda row: row["slug"])


def json_int_list(value):
    if isinstance(value, list):
        items = value
    else:
        try:
            items = json.loads(value or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            items = []
    parsed = []
    for item in items:
        try:
            parsed.append(int(item))
        except (TypeError, ValueError):
            continue
    return parsed


def dev_note_release_from_slug(slug):
    match = re.search(r"dev-notes-?(\d+)[-.](\d+)", str(slug or ""))
    if not match:
        return ""
    return f"{int(match.group(1))}.{int(match.group(2))}"


def derive_make_core_dev_notes(make_posts, dev_note_tags):
    tag_by_id = {str(row.get("id")): row for row in dev_note_tags}
    dev_note_tag_ids = {str(row.get("id")) for row in dev_note_tags}
    note_rows = []
    quarterly = defaultdict(lambda: {"dev_notes": 0, "authors": set(), "release_tagged": 0})
    releases = defaultdict(lambda: {"dev_notes": 0, "authors": set(), "first_post_date": "", "last_post_date": ""})

    for post in make_posts:
        post_tag_ids = {str(item) for item in json_int_list(post.get("tags"))}
        matched_tag_ids = sorted(post_tag_ids & dev_note_tag_ids)
        if not matched_tag_ids:
            continue
        matched_tags = [tag_by_id[tag_id] for tag_id in matched_tag_ids if tag_id in tag_by_id]
        release_versions = sorted(
            {
                dev_note_release_from_slug(tag.get("slug"))
                for tag in matched_tags
                if dev_note_release_from_slug(tag.get("slug"))
            },
            key=version_tuple,
        )
        primary_release = release_versions[-1] if release_versions else ""
        q = quarter_start(post.get("date"))
        if q:
            quarterly[q]["dev_notes"] += 1
            if post.get("author"):
                quarterly[q]["authors"].add(str(post.get("author")))
            if primary_release:
                quarterly[q]["release_tagged"] += 1
        if primary_release:
            release = releases[primary_release]
            release["dev_notes"] += 1
            if post.get("author"):
                release["authors"].add(str(post.get("author")))
            post_date = str(post.get("date") or "")
            if post_date:
                if not release["first_post_date"] or post_date < release["first_post_date"]:
                    release["first_post_date"] = post_date
                if not release["last_post_date"] or post_date > release["last_post_date"]:
                    release["last_post_date"] = post_date
        note_rows.append(
            {
                "id": str(post.get("id", "")),
                "date": str(post.get("date", "")),
                "author": str(post.get("author", "")),
                "title": str(post.get("title", "")),
                "link": str(post.get("link", "")),
                "tag_ids": ",".join(matched_tag_ids),
                "tag_slugs": ",".join(sorted(tag.get("slug", "") for tag in matched_tags)),
                "release_versions": ",".join(release_versions),
                "primary_release_version": primary_release,
                "source_url": MAKE_CORE_API,
            }
        )

    quarterly_rows = [
        {
            "quarter": quarter,
            "dev_notes": values["dev_notes"],
            "unique_authors": len(values["authors"]),
            "release_tagged_dev_notes": values["release_tagged"],
        }
        for quarter, values in sorted(quarterly.items())
    ]
    release_rows = [
        {
            "version": version,
            "dev_notes": values["dev_notes"],
            "unique_authors": len(values["authors"]),
            "first_post_date": values["first_post_date"],
            "last_post_date": values["last_post_date"],
        }
        for version, values in sorted(releases.items(), key=lambda item: version_tuple(item[0]))
    ]
    note_rows.sort(key=lambda row: (row["date"], row["id"]))
    return note_rows, quarterly_rows, release_rows


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
    # The generated DB is rebuilt from source data; avoid a large persistent WAL on low-disk refreshes.
    conn.execute("PRAGMA journal_mode=DELETE")
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
    gaps = []
    if data.get("builtwith_new_site_snapshot"):
        gaps.append(
            (
                "new_site_share_history",
                "partial",
                "BuiltWith historical trends or HTTP Archive cohort queries",
                "Current report includes BuiltWith current Net New Pipeline, HTTP Archive monthly origin counts, derived tracked-share history, rank-tier detected-origin adoption, a compact new-site choice summary, and a dedicated new-site choice companion view; not a multi-year newly created site cohort.",
            )
        )
    else:
        gaps.append(
            (
                "new_site_share",
                "missing",
                "BuiltWith paid trends or HTTP Archive cohort queries",
                "Current report uses all-site and CMS-share trends, not newly created site cohorts.",
            )
        )
    if data.get("support_forum_topics"):
        gaps.append(
            (
                "support_forum_history",
                "partial",
                "Historical WordPress.org support forum topic/reply export",
                "Current report includes public support queue snapshots, resolved/unresolved/no-reply summaries, last-activity buckets, forum-level unanswered summaries, a support-load companion view, and major-plugin support-thread totals; not a full long-term topic/reply history.",
            )
        )
    else:
        gaps.append(
            (
                "support_forums",
                "missing",
                "WordPress.org support forum topic/resolution data",
                "Needs a dedicated source pull.",
            )
        )
    if not data.get("core_response_quarterly"):
        gaps.append(
            (
                "core_first_response",
                "missing",
                "Trac ticket RSS comments/change history",
                "Existing Core event export covers status transitions, not first non-reporter response.",
            )
        )
    if not data.get("gutenberg_timeline_quarterly"):
        gaps.extend(
            [
                ("gutenberg_first_response", "missing", "GitHub issue comments/timeline events", "Existing issue export has comment counts but not first comment timestamps."),
                ("gutenberg_reopened_rate", "missing", "GitHub timeline events", "Existing issue export has current state and close date, not reopen transitions."),
            ]
        )
    if not fetched.get("wp_events"):
        gaps.append(
            (
                "meetups",
                "missing",
                "Meetup or WordPress events source",
                "WordCamp data is included; broader Meetup chapter activity is not.",
            )
        )
    if fetched.get("stack_overflow_tag_quarterly"):
        gaps.append(
            (
                "developer_interest_proxy",
                "partial",
                "Stack Exchange API question totals, Wikimedia Pageviews API, GitHub PR activity, and broader developer-community sources",
                "Quarterly Stack Overflow tag volume, Wikimedia pageviews, wordpress-develop PR activity, and a compact attention/demand summary are included as public attention and contribution proxies; they do not measure general search-query interest.",
            )
        )
    else:
        gaps.append(
            (
                "developer_interest_proxy",
                "missing",
                "Stack Exchange API question totals by Stack Overflow tag",
                "Needs quarterly tag-volume totals for WordPress and comparable builder/ecommerce tags.",
            )
        )
    if fetched.get("wikimedia_pageviews_quarterly"):
        gaps.append(
            (
                "search_interest",
                "partial",
                "Google Trends or another search-interest provider",
                "Wikimedia Pageviews API quarterly article-view trends, Stack Overflow tag-volume context, a compact attention/demand summary, and a search-interest companion view are included as public-interest proxies; true search-query interest still needs Google Trends or another search provider.",
            )
        )
    else:
        gaps.append(
            (
                "search_interest",
                "missing",
                "Google Trends or another search-interest provider",
                "No stable unattended public search-interest source is wired in; the report uses Stack Overflow tag volume only as a developer-interest proxy.",
            )
        )
    gaps.append(
        (
            "job_demand",
            "partial",
            "Hacker News monthly Who is hiring? threads plus hiring-platform exports",
            "HN Who is hiring WordPress/WooCommerce, PHP, and agency/studio mention counts, WordPress Jobs board open-listing snapshots, a compact proxy-direction summary, and a job-demand companion view are included; broader job-board demand still needs a labor-market source.",
        )
    )
    if not fetched.get("enterprise_vip_case_studies"):
        gaps.append(
            (
                "enterprise_adoption",
                "missing",
                "Public enterprise customer or case-study source",
                "The report needs a current enterprise adoption signal such as public WordPress VIP case studies.",
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
    if not fetched.get("translation_locale_snapshot"):
        gaps.append(
            (
                "translation_contributors",
                "missing",
                "translate.wordpress.org locale and Core project status pages",
                "Needs locale-level translation team and Core development translation status data.",
            )
        )
    if not fetched.get("directory_activity_snapshots"):
        gaps.append(
            (
                "plugin_theme_directory_activity",
                "missing",
                "WordPress.org plugin/theme directory browse APIs",
                "Needs current new, updated, and popular directory samples.",
            )
        )
    if fetched.get("major_plugin_install_snapshot"):
        if not fetched.get("major_plugin_install_history"):
            gaps.append(
                (
                    "major_plugin_install_base_growth",
                    "partial",
                    "WordPress.org plugin information API plus archived snapshots",
                    (
                        "Current major-plugin install-base snapshot is included, and WordPress.org daily download history "
                        "is included as a one-year demand trend. Historical active-install growth still needs repeated "
                        "snapshots or archived WordPress.org plugin metadata."
                    ),
                )
            )
    else:
        gaps.append(
            (
                "major_plugin_install_base_growth",
                "missing",
                "WordPress.org plugin information API plus archived snapshots",
                "Needs current major-plugin install-base data and a historical snapshot source for growth.",
            )
        )
    if not fetched.get("make_core_dev_notes"):
        gaps.append(
            (
                "dev_note_volume",
                "missing",
                "Make/Core REST API post tags",
                "Dev note volume needs Make/Core post tag IDs and dev-notes tag metadata.",
            )
        )
    if not fetched.get("make_core_comments"):
        gaps.append(
            (
                "make_core_commenters",
                "missing",
                "Make/Core REST API comments endpoint",
                "Needs Make/Core comment rows to distinguish publishing authors from discussion participants.",
            )
        )
    conn.executemany("INSERT INTO source_gaps VALUES (?,?,?,?)", gaps)
    conn.commit()
    conn.close()


def build_derived_metrics(data):
    core_q = data.get("core_quarterly", [])
    core_events = data.get("core_events", [])
    closed_by_quarter = {row.get("quarter"): num(row.get("closed")) for row in core_q}
    reopened_events = Counter()
    reopened_tickets = defaultdict(set)
    for event in core_events:
        if event.get("event_type") != "reopened":
            continue
        q = quarter_start(event.get("event_at"))
        if not q:
            continue
        reopened_events[q] += 1
        reopened_tickets[q].add(str(event.get("ticket_id", "")))
    rows = []
    for quarter in sorted(set(closed_by_quarter) | set(reopened_events)):
        closed = closed_by_quarter.get(quarter, 0)
        event_count = reopened_events.get(quarter, 0)
        ticket_count = len(reopened_tickets.get(quarter, set()))
        rows.append(
            {
                "quarter": quarter,
                "label": quarter_label(quarter),
                "closed": closed,
                "reopened_events": event_count,
                "reopened_tickets": ticket_count,
                "reopened_events_per_100_closed": round(event_count / closed * 100, 2) if closed else 0,
                "source": "Core Trac ticket RSS status-change events",
            }
        )
    support_topics = data.get("support_forum_topics", [])
    support_monthly, support_age = derive_support_forum_activity(support_topics)
    support_snapshot_summary, support_unanswered_by_forum = derive_support_forum_snapshot_tables(support_topics)
    return {
        "core_reopen_quarterly": rows,
        "support_forum_activity_monthly": support_monthly,
        "support_forum_age_buckets": support_age,
        "support_forum_snapshot_summary": support_snapshot_summary,
        "support_forum_unanswered_by_forum": support_unanswered_by_forum,
        "contributor_depth_buckets": derive_contributor_depth(data),
        "contributor_concentration_summary": derive_contributor_concentration_summary(data),
        "maintainer_participation_quarterly": derive_maintainer_participation_quarterly(data),
        "category_open_backlog_summary": derive_category_open_backlog_summary(data),
        "open_backlog_age_summary": derive_open_backlog_age_summary(data),
        "closure_age_summary": derive_closure_age_summary(data),
    }


def derive_builtwith_tier_share_snapshot(rows):
    if not rows:
        return []
    tier_defs = [
        ("top_1000", "Top 1k", 1),
        ("top_10k", "Top 10k", 2),
        ("top_100k", "Top 100k", 3),
        ("top_1m", "Top 1M", 4),
        ("long_tail", "Long tail", 5),
    ]
    by_tech = {row.get("technology"): row for row in rows}
    wordpress = by_tech.get("WordPress", {})
    collected_at = max([row.get("collected_at", "") for row in rows] or [""])
    result = []
    for field, label, order in tier_defs:
        if field == "long_tail":
            tracked_total = sum(max(num(row.get("total_live")) - num(row.get("top_1m")), 0) for row in rows)
            wordpress_count = max(num(wordpress.get("total_live")) - num(wordpress.get("top_1m")), 0)
        else:
            tracked_total = sum(num(row.get(field)) for row in rows)
            wordpress_count = num(wordpress.get(field))
        result.append(
            {
                "tier": field,
                "label": label,
                "tier_order": order,
                "wordpress_count": wordpress_count,
                "tracked_total": tracked_total,
                "wordpress_share_pct": round(wordpress_count / tracked_total * 100, 2) if tracked_total else 0,
                "tracked_technologies": ",".join(sorted(str(row.get("technology") or "") for row in rows if row.get("technology"))),
                "collected_at": collected_at,
                "source": "BuiltWith public technology pages current traffic-tier counts",
                "source_url": "https://trends.builtwith.com/cms/WordPress",
            }
        )
    return result


def derive_new_site_choice_summary(builtwith_rows, http_share_rows, tier_rows):
    rows = []
    collected_at = max([row.get("collected_at", "") for row in builtwith_rows if row.get("collected_at")] or [""])

    def add_row(signal, label, source_type, period, wordpress_value, tracked_total, unit, note, next_peer="", next_peer_value=0):
        wordpress_value = float(wordpress_value or 0)
        tracked_total = float(tracked_total or 0)
        next_peer_value = float(next_peer_value or 0)
        rows.append(
            {
                "signal": signal,
                "label": label,
                "source_type": source_type,
                "period": period,
                "wordpress_value": round(wordpress_value, 2),
                "tracked_total": round(tracked_total, 2),
                "wordpress_share_pct": round(wordpress_value / tracked_total * 100, 2) if tracked_total else 0,
                "next_peer": next_peer,
                "next_peer_value": round(next_peer_value, 2),
                "wordpress_to_next_peer_ratio": round(wordpress_value / next_peer_value, 2) if next_peer_value else 0,
                "unit": unit,
                "note": note,
                "collected_at": collected_at,
            }
        )

    pipeline_rows = [row for row in builtwith_rows if num(row.get("new_last_3_months")) > 0]
    if pipeline_rows:
        tracked_total = sum(num(row.get("new_last_3_months")) for row in pipeline_rows)
        wp_row = next((row for row in pipeline_rows if row.get("technology") == "WordPress"), {})
        next_peer = max([row for row in pipeline_rows if row.get("technology") != "WordPress"], key=lambda row: num(row.get("new_last_3_months")), default={})
        add_row(
            "builtwith_90_day_pipeline",
            "BuiltWith 90-day newly found pipeline",
            "current_new_site_proxy",
            "last 90 days",
            num(wp_row.get("new_last_3_months")),
            tracked_total,
            "newly found sites",
            "BuiltWith public Net New Pipeline across WordPress, Shopify, Wix, and Webflow. Squarespace does not expose comparable new-site counts on the fetched page.",
            next_peer.get("technology", ""),
            num(next_peer.get("new_last_3_months")),
        )
        tracked_30 = sum(num(row.get("new_last_month")) for row in pipeline_rows)
        next_peer_30 = max([row for row in pipeline_rows if row.get("technology") != "WordPress"], key=lambda row: num(row.get("new_last_month")), default={})
        add_row(
            "builtwith_30_day_pipeline",
            "BuiltWith 30-day newly found pipeline",
            "current_new_site_proxy",
            "last 30 days",
            num(wp_row.get("new_last_month")),
            tracked_30,
            "newly found sites",
            "Shorter current BuiltWith Net New Pipeline window across the tracked technologies with comparable public counts.",
            next_peer_30.get("technology", ""),
            num(next_peer_30.get("new_last_month")),
        )

    latest_http_date = max([row.get("date", "") for row in http_share_rows if row.get("date")] or [""])
    first_http_date = min([row.get("date", "") for row in http_share_rows if row.get("date")] or [""])
    if latest_http_date:
        latest_rows = [row for row in http_share_rows if row.get("date") == latest_http_date]
        wp_latest = next((row for row in latest_rows if row.get("technology") == "WordPress"), {})
        next_peer = max([row for row in latest_rows if row.get("technology") != "WordPress"], key=lambda row: float(row.get("mobile_tracked_share_pct") or 0), default={})
        add_row(
            "http_archive_latest_tracked_share",
            "HTTP Archive tracked share",
            "recurring_detected_origin_proxy",
            latest_http_date,
            float(wp_latest.get("mobile_tracked_share_pct") or 0),
            100,
            "tracked share pct",
            "Latest monthly HTTP Archive mobile detected-origin share among tracked WordPress and builder/ecommerce technologies.",
            next_peer.get("technology", ""),
            float(next_peer.get("mobile_tracked_share_pct") or 0),
        )
    if first_http_date and latest_http_date and first_http_date != latest_http_date:
        first_wp = next((row for row in http_share_rows if row.get("date") == first_http_date and row.get("technology") == "WordPress"), {})
        latest_wp = next((row for row in http_share_rows if row.get("date") == latest_http_date and row.get("technology") == "WordPress"), {})
        add_row(
            "http_archive_tracked_share_change",
            "HTTP Archive tracked-share change",
            "recurring_detected_origin_proxy",
            f"{first_http_date} to {latest_http_date}",
            float(latest_wp.get("mobile_tracked_share_pct") or 0) - float(first_wp.get("mobile_tracked_share_pct") or 0),
            100,
            "percentage-point change",
            "Change in WordPress share among the tracked HTTP Archive technology set from first to latest fetched month.",
        )

    top1m = next((row for row in tier_rows if row.get("tier") == "top_1m"), {})
    if top1m:
        add_row(
            "builtwith_top_1m_tracked_share",
            "BuiltWith Top 1M tracked share",
            "traffic_tier_presence",
            "current snapshot",
            float(top1m.get("wordpress_share_pct") or 0),
            100,
            "tracked share pct",
            "Current BuiltWith traffic-tier share among WordPress, Shopify, Wix, Squarespace, and Webflow.",
        )
    long_tail = next((row for row in tier_rows if row.get("tier") == "long_tail"), {})
    if long_tail:
        add_row(
            "builtwith_long_tail_tracked_share",
            "BuiltWith long-tail tracked share",
            "traffic_tier_presence",
            "current snapshot",
            float(long_tail.get("wordpress_share_pct") or 0),
            100,
            "tracked share pct",
            "Current BuiltWith tracked share outside the Top 1M traffic tier.",
        )
    return rows


def derive_support_forum_activity(topics):
    monthly = defaultdict(
        lambda: {
            "topics": 0,
            "resolved": 0,
            "unresolved": 0,
            "no_replies": 0,
            "replies": 0,
            "participants": 0,
            "forums": set(),
            "starters": set(),
        }
    )
    collected_dates = [parse_iso(row.get("collected_at")) for row in topics if parse_iso(row.get("collected_at"))]
    snapshot_at = max(collected_dates) if collected_dates else END
    age_bucket_defs = [
        ("0-7 days", 0, 7),
        ("8-30 days", 8, 30),
        ("31-90 days", 31, 90),
        ("91-180 days", 91, 180),
        ("181+ days", 181, None),
        ("unknown", None, None),
    ]
    age_buckets = {
        label: {
            "age_bucket": label,
            "topics": 0,
            "resolved": 0,
            "unresolved": 0,
            "no_replies": 0,
            "replies": 0,
            "participants": 0,
        }
        for label, _min_days, _max_days in age_bucket_defs
    }

    def age_bucket_for(days):
        if days is None:
            return "unknown"
        for label, min_days, max_days in age_bucket_defs:
            if min_days is None:
                continue
            if days >= min_days and (max_days is None or days <= max_days):
                return label
        return "unknown"

    for row in topics:
        active = parse_iso(row.get("last_activity_at"))
        is_resolved = num(row.get("is_resolved"))
        is_unresolved = num(row.get("is_unresolved"))
        has_no_replies = num(row.get("has_no_replies"))
        replies = num(row.get("replies"))
        participants = num(row.get("participants"))
        if active:
            month = month_start(active.isoformat())
            bucket = monthly[month]
            bucket["topics"] += 1
            bucket["resolved"] += is_resolved
            bucket["unresolved"] += is_unresolved
            bucket["no_replies"] += has_no_replies
            bucket["replies"] += replies
            bucket["participants"] += participants
            if row.get("forum_name"):
                bucket["forums"].add(row.get("forum_name"))
            if row.get("starter_slug"):
                bucket["starters"].add(row.get("starter_slug"))
            age_days = max(0, int((snapshot_at - active).total_seconds() // 86400))
        else:
            age_days = None
        age_bucket = age_buckets[age_bucket_for(age_days)]
        age_bucket["topics"] += 1
        age_bucket["resolved"] += is_resolved
        age_bucket["unresolved"] += is_unresolved
        age_bucket["no_replies"] += has_no_replies
        age_bucket["replies"] += replies
        age_bucket["participants"] += participants

    monthly_rows = []
    for month, values in sorted(monthly.items()):
        monthly_rows.append(
            {
                "month": month,
                "label": parse_iso(month).strftime("%b %Y") if parse_iso(month) else month,
                "topics": values["topics"],
                "resolved": values["resolved"],
                "unresolved": values["unresolved"],
                "no_replies": values["no_replies"],
                "replies": values["replies"],
                "participants": values["participants"],
                "forums": len(values["forums"]),
                "starters": len(values["starters"]),
                "source": "Current WordPress.org support queue snapshot, bucketed by last activity month",
            }
        )
    age_rows = []
    for index, (label, _min_days, _max_days) in enumerate(age_bucket_defs, start=1):
        row = dict(age_buckets[label])
        row["bucket_order"] = index
        row["snapshot_at"] = snapshot_at.isoformat().replace("+00:00", "Z")
        row["source"] = "Current WordPress.org support queue snapshot, bucketed by age since last activity"
        age_rows.append(row)
    return monthly_rows, age_rows


def derive_support_forum_snapshot_tables(topics):
    if not topics:
        return [], []
    collected_dates = [parse_iso(row.get("collected_at")) for row in topics if parse_iso(row.get("collected_at"))]
    snapshot_at = max(collected_dates) if collected_dates else END
    forums = defaultdict(
        lambda: {
            "topics": 0,
            "resolved": 0,
            "unresolved": 0,
            "no_replies": 0,
            "replies": 0,
            "participants": 0,
            "starters": set(),
        }
    )
    totals = {
        "topics": 0,
        "resolved": 0,
        "unresolved": 0,
        "no_replies": 0,
        "replies": 0,
        "participants": 0,
        "starters": set(),
    }
    oldest_activity = None
    latest_activity = None
    for row in topics:
        forum_name = row.get("forum_name") or "(unknown)"
        bucket = forums[forum_name]
        is_resolved = num(row.get("is_resolved"))
        is_unresolved = num(row.get("is_unresolved"))
        has_no_replies = num(row.get("has_no_replies"))
        replies = num(row.get("replies"))
        participants = num(row.get("participants"))
        for target in (bucket, totals):
            target["topics"] += 1
            target["resolved"] += is_resolved
            target["unresolved"] += is_unresolved
            target["no_replies"] += has_no_replies
            target["replies"] += replies
            target["participants"] += participants
            if row.get("starter_slug"):
                target["starters"].add(row.get("starter_slug"))
        activity = parse_iso(row.get("last_activity_at"))
        if activity and (oldest_activity is None or activity < oldest_activity):
            oldest_activity = activity
        if activity and (latest_activity is None or activity > latest_activity):
            latest_activity = activity

    def shares(values):
        topics_total = values["topics"]
        return {
            "resolved_share_pct": round(values["resolved"] / topics_total * 100, 2) if topics_total else 0,
            "unresolved_share_pct": round(values["unresolved"] / topics_total * 100, 2) if topics_total else 0,
            "no_reply_share_pct": round(values["no_replies"] / topics_total * 100, 2) if topics_total else 0,
        }

    total_shares = shares(totals)
    summary = [
        {
            "snapshot_at": snapshot_at.isoformat().replace("+00:00", "Z"),
            "topics": totals["topics"],
            "resolved": totals["resolved"],
            "unresolved": totals["unresolved"],
            "no_replies": totals["no_replies"],
            "replies": totals["replies"],
            "participants": totals["participants"],
            "unique_starters": len(totals["starters"]),
            "forum_count": len(forums),
            "oldest_last_activity_at": oldest_activity.isoformat().replace("+00:00", "Z") if oldest_activity else "",
            "latest_last_activity_at": latest_activity.isoformat().replace("+00:00", "Z") if latest_activity else "",
            "resolved_share_pct": total_shares["resolved_share_pct"],
            "unresolved_share_pct": total_shares["unresolved_share_pct"],
            "no_reply_share_pct": total_shares["no_reply_share_pct"],
            "source": "Current WordPress.org support queue snapshot deduplicated by topic",
        }
    ]
    by_forum = []
    for forum_name, values in sorted(forums.items(), key=lambda item: item[1]["unresolved"], reverse=True):
        row = {
            "snapshot_at": snapshot_at.isoformat().replace("+00:00", "Z"),
            "forum_name": forum_name,
            "topics": values["topics"],
            "resolved": values["resolved"],
            "unresolved": values["unresolved"],
            "no_replies": values["no_replies"],
            "replies": values["replies"],
            "participants": values["participants"],
            "unique_starters": len(values["starters"]),
            "source": "Current WordPress.org support queue snapshot deduplicated by topic",
        }
        row.update(shares(values))
        by_forum.append(row)
    return summary, by_forum


def contributor_depth_rows(label, rows, author_key, date_key, since=None):
    counts = Counter()
    for row in rows:
        if since and str(row.get(date_key, "")) < since:
            continue
        author = str(row.get(author_key) or "").strip() or "(unknown)"
        counts[author] += 1
    bucket_defs = [
        ("1 item", 1, 1),
        ("2-4 items", 2, 4),
        ("5-19 items", 5, 19),
        ("20+ items", 20, None),
    ]
    bucketed = {
        bucket: {"contributors": 0, "items": 0}
        for bucket, _min_count, _max_count in bucket_defs
    }
    for count in counts.values():
        for bucket, min_count, max_count in bucket_defs:
            if count >= min_count and (max_count is None or count <= max_count):
                bucketed[bucket]["contributors"] += 1
                bucketed[bucket]["items"] += count
                break
    total_contributors = sum(value["contributors"] for value in bucketed.values())
    total_items = sum(value["items"] for value in bucketed.values())
    window = f"since_{since[:4]}" if since else "all_time"
    rows_out = []
    for index, (bucket, _min_count, _max_count) in enumerate(bucket_defs, start=1):
        values = bucketed[bucket]
        contributors = values["contributors"]
        items = values["items"]
        rows_out.append(
            {
                "source": label,
                "window": window,
                "since": since or "",
                "bucket": bucket,
                "bucket_order": index,
                "contributors": contributors,
                "items": items,
                "total_contributors": total_contributors,
                "total_items": total_items,
                "contributor_share_pct": round(contributors / total_contributors * 100, 2) if total_contributors else 0,
                "item_share_pct": round(items / total_items * 100, 2) if total_items else 0,
            }
        )
    return rows_out


def derive_contributor_depth(data):
    rows = []
    sources = [
        ("Core Trac reporters", data.get("core_tickets", []), "reporter", "created_at"),
        ("Gutenberg issue creators", data.get("gutenberg_issues", []), "author_login", "created_at"),
        ("wordpress-develop PR authors", data.get("github_prs", []), "author_login", "created_at"),
    ]
    for label, source_rows, author_key, date_key in sources:
        rows.extend(contributor_depth_rows(label, source_rows, author_key, date_key))
        rows.extend(contributor_depth_rows(label, source_rows, author_key, date_key, "2024-01-01"))
    return rows


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


def difference_series(rows, date_col, minuend_col, subtrahend_col, start=None):
    out = []
    for row in rows:
        date_value = row.get(date_col)
        if start and date_value < start:
            continue
        value = max(0, float(row.get(minuend_col) or 0) - float(row.get(subtrahend_col) or 0))
        out.append((date_value, value))
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


def svg_line_chart(title, note, series_list, height=330, y_suffix="", start_zero=True, show_end_labels=True):
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
    terminal_labels = []
    for series in series_list:
        points = [(d, v) for d, v in series["points"] if d and v is not None]
        if not points:
            continue
        path = " ".join(("M" if i == 0 else "L") + f"{x(d):.1f},{y(v):.1f}" for i, (d, v) in enumerate(points))
        pieces.append(f'<path d="{path}" fill="none" stroke="{series["color"]}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />')
        if show_end_labels:
            for d, v in points[-1:]:
                pieces.append(f'<circle cx="{x(d):.1f}" cy="{y(v):.1f}" r="4" fill="{series["color"]}" />')
                terminal_labels.append(
                    {
                        "x": min(width - right - 70, x(d) + 8),
                        "y": y(v) - 8,
                        "color": series["color"],
                        "label": f"{compact(v)}{y_suffix}",
                    }
                )
    if show_end_labels:
        terminal_labels.sort(key=lambda item: item["y"])
        min_label_y = top + 12
        max_label_y = top + plot_h - 8
        previous_y = min_label_y - 16
        for item in terminal_labels:
            item["y"] = max(min_label_y, item["y"], previous_y + 16)
            previous_y = item["y"]
        next_y = max_label_y + 16
        for item in reversed(terminal_labels):
            item["y"] = min(max_label_y, item["y"], next_y - 16)
            next_y = item["y"]
        for item in terminal_labels:
            pieces.append(
                f'<text x="{item["x"]:.1f}" y="{item["y"]:.1f}" class="end-label" fill="{item["color"]}">{html.escape(item["label"])}</text>'
            )
    pieces.append("</svg>")
    return "\n".join(pieces)


def stat_card(label, value, note="", tone="neutral"):
    return f"""
    <div class="stat {tone}">
      <div class="stat-label">{html.escape(label)}</div>
      <div class="stat-value">{html.escape(str(value))}</div>
      <div class="stat-note">{html.escape(note)}</div>
    </div>
    """.strip()


def signal_card(title, verdict, detail, tone="neutral"):
    return f"""
    <article class="signal {tone}">
      <h3>{html.escape(title)}</h3>
      <strong>{html.escape(verdict)}</strong>
      <p>{html.escape(detail)}</p>
    </article>
    """.strip()


def horizontal_metric(label, value, max_value, color):
    width = 100 if max_value <= 0 else max(2, min(100, value / max_value * 100))
    return f"""
    <div class="hmetric">
      <div class="hmetric-top"><span>{html.escape(label)}</span><strong>{pct(value)}</strong></div>
      <div class="bar"><span style="width:{width:.1f}%;background:{color}"></span></div>
    </div>
    """.strip()


def horizontal_count_metric(label, value, max_value, color, suffix=""):
    width = 100 if max_value <= 0 else max(2, min(100, value / max_value * 100))
    value_label = f"{compact(value)}{suffix}"
    return f"""
    <div class="hmetric">
      <div class="hmetric-top"><span>{html.escape(label)}</span><strong>{html.escape(value_label)}</strong></div>
      <div class="bar"><span style="width:{width:.1f}%;background:{color}"></span></div>
    </div>
    """.strip()


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


def derive_closure_age_summary(data):
    rows = []
    core_tickets = data.get("core_tickets", [])
    core_events = data.get("core_events", [])
    created_by_id = {str(row.get("id")): parse_iso(row.get("created_at")) for row in core_tickets}
    close_events = defaultdict(list)
    core_by_quarter = defaultdict(list)
    for event in core_events:
        if event.get("event_type") != "closed":
            continue
        ticket_id = str(event.get("ticket_id"))
        closed = parse_iso(event.get("event_at"))
        if closed:
            close_events[ticket_id].append(closed)
    for ticket_id, closes in close_events.items():
        created = created_by_id.get(ticket_id)
        if not created or not closes:
            continue
        final_close = max(closes)
        core_by_quarter[quarter_start(final_close.isoformat())].append((final_close - created).total_seconds() / 86400)

    def add_rows(source, by_quarter, source_note):
        for quarter, values in sorted(by_quarter.items()):
            median_days = median(values)
            p75_days = percentile(values, 0.75)
            p90_days = percentile(values, 0.90)
            rows.append(
                {
                    "source": source,
                    "quarter": quarter,
                    "label": quarter_label(quarter),
                    "closed_count": len(values),
                    "median_days_to_close": round(median_days, 2) if median_days is not None else "",
                    "p75_days_to_close": round(p75_days, 2) if p75_days is not None else "",
                    "p90_days_to_close": round(p90_days, 2) if p90_days is not None else "",
                    "source_note": source_note,
                }
            )

    add_rows("Core", core_by_quarter, "Core Trac final closed-event age from ticket creation to close event")

    gutenberg_by_quarter = defaultdict(list)
    for issue in data.get("gutenberg_issues_jsonl", []):
        created = parse_iso(issue.get("created_at"))
        closed = parse_iso(issue.get("closed_at"))
        if not created or not closed:
            continue
        gutenberg_by_quarter[quarter_start(closed.isoformat())].append((closed - created).total_seconds() / 86400)
    add_rows("Gutenberg", gutenberg_by_quarter, "Gutenberg GitHub issue age from created_at to closed_at")
    return rows


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


def derive_contributor_concentration_summary(data):
    configs = [
        ("Core Trac reporters", data.get("core_tickets", []), "reporter", "created_at"),
        ("Gutenberg issue creators", data.get("gutenberg_issues", []), "author_login", "created_at"),
        ("wordpress-develop PR authors", data.get("github_prs", []), "author_login", "created_at"),
    ]
    rows = []
    for source, source_rows, author_key, date_key in configs:
        for window, since in [("all_time", None), ("since_2024", "2024-01-01")]:
            concentration = contributor_concentration(source_rows, author_key, date_key, since)
            rows.append(
                {
                    "source": source,
                    "window": window,
                    "since": since or "",
                    "total_items": concentration["total"],
                    "total_contributors": concentration["unique"],
                    "one_time_contributor_share_pct": round(concentration["one_time_share"], 2),
                    "top10_item_share_pct": round(concentration["top10"], 2),
                    "top25_item_share_pct": round(concentration["top25"], 2),
                    "top50_item_share_pct": round(concentration["top50"], 2),
                    "metric_note": "Share of source rows handled by the top N contributors in the selected window",
                }
            )
    return rows


PROJECT_MEMBER_ASSOCIATIONS = {"MEMBER", "OWNER", "COLLABORATOR"}


def participation_bucket(row):
    author_type = str(row.get("author_type") or "").strip().lower()
    if author_type == "bot":
        return "bot"
    association = str(row.get("author_association") or "").strip().upper()
    if association in PROJECT_MEMBER_ASSOCIATIONS:
        return "project_member"
    if association:
        return "outside"
    return "unknown"


def derive_maintainer_participation_quarterly(data):
    source_defs = [
        ("Gutenberg issues", data.get("gutenberg_issues", []), "created_at", "author_login"),
        ("wordpress-develop PRs", data.get("github_prs", []), "created_at", "author_login"),
    ]
    rows = []
    for source, source_rows, date_key, author_key in source_defs:
        buckets = defaultdict(
            lambda: {
                "project_member_items": 0,
                "outside_items": 0,
                "bot_items": 0,
                "unknown_items": 0,
                "project_member_authors": set(),
                "outside_authors": set(),
                "bot_authors": set(),
                "unknown_authors": set(),
            }
        )
        for item in source_rows:
            quarter = quarter_start(item.get(date_key))
            if not quarter:
                continue
            bucket = participation_bucket(item)
            author = str(item.get(author_key) or "").strip() or "(unknown)"
            values = buckets[quarter]
            values[f"{bucket}_items"] += 1
            values[f"{bucket}_authors"].add(author)
        for quarter, values in sorted(buckets.items()):
            known_human_items = values["project_member_items"] + values["outside_items"]
            total_items = known_human_items + values["bot_items"] + values["unknown_items"]
            rows.append(
                {
                    "source": source,
                    "quarter": quarter,
                    "label": quarter_label(quarter),
                    "project_member_items": values["project_member_items"],
                    "outside_items": values["outside_items"],
                    "bot_items": values["bot_items"],
                    "unknown_items": values["unknown_items"],
                    "known_human_items": known_human_items,
                    "total_items": total_items,
                    "project_member_authors": len(values["project_member_authors"]),
                    "outside_authors": len(values["outside_authors"]),
                    "bot_authors": len(values["bot_authors"]),
                    "unknown_authors": len(values["unknown_authors"]),
                    "project_member_share_pct": round(values["project_member_items"] / known_human_items * 100, 2) if known_human_items else 0,
                    "outside_share_pct": round(values["outside_items"] / known_human_items * 100, 2) if known_human_items else 0,
                    "bot_share_pct": round(values["bot_items"] / total_items * 100, 2) if total_items else 0,
                    "source_note": "GitHub author_association bucketed by quarter; project-member means MEMBER/OWNER/COLLABORATOR and excludes bots.",
                }
            )
    return rows


def derive_category_open_backlog_summary(data):
    sources = [
        ("Core", data.get("classification_summary_core", [])),
        ("Gutenberg", data.get("classification_summary_gutenberg", [])),
    ]
    rows = []
    combined = defaultdict(lambda: {"total": 0, "open_count": 0})
    for source, source_rows in sources:
        source_open_total = sum(num(row.get("open_count")) for row in source_rows)
        source_total = sum(num(row.get("total")) for row in source_rows)
        for row in source_rows:
            category = str(row.get("category") or "unknown")
            total = num(row.get("total"))
            open_count = num(row.get("open_count"))
            combined[category]["total"] += total
            combined[category]["open_count"] += open_count
            rows.append(
                {
                    "source": source,
                    "category": category,
                    "total": total,
                    "open_count": open_count,
                    "source_open_total": source_open_total,
                    "source_total": source_total,
                    "open_category_share_pct": round(open_count / source_open_total * 100, 2) if source_open_total else 0,
                    "category_open_rate_pct": round(open_count / total * 100, 2) if total else 0,
                    "source_note": "Open classified backlog share by category from ticket/issue classification summaries",
                }
            )
    combined_open_total = sum(value["open_count"] for value in combined.values())
    combined_total = sum(value["total"] for value in combined.values())
    for category, values in sorted(combined.items()):
        rows.append(
            {
                "source": "Combined",
                "category": category,
                "total": values["total"],
                "open_count": values["open_count"],
                "source_open_total": combined_open_total,
                "source_total": combined_total,
                "open_category_share_pct": round(values["open_count"] / combined_open_total * 100, 2) if combined_open_total else 0,
                "category_open_rate_pct": round(values["open_count"] / values["total"] * 100, 2) if values["total"] else 0,
                "source_note": "Open classified backlog share by category from ticket/issue classification summaries",
            }
        )
    return rows


def derive_open_backlog_age_summary(data):
    bucket_defs = [
        ("0-90 days", 1, 0, 90),
        ("91-365 days", 2, 91, 365),
        ("1-2 years", 3, 366, 730),
        ("2-5 years", 4, 731, 1825),
        ("5+ years", 5, 1826, None),
        ("unknown", 6, None, None),
    ]

    def bucket_for(days):
        if days is None:
            return "unknown"
        for label, _order, min_days, max_days in bucket_defs:
            if min_days is None:
                continue
            if days >= min_days and (max_days is None or days <= max_days):
                return label
        return "unknown"

    source_defs = [
        ("Core", data.get("core_tickets", []), "status", "modified_at", lambda row: str(row.get("status") or "").lower() != "closed"),
        ("Gutenberg", data.get("gutenberg_issues_jsonl", []), "state", "updated_at", lambda row: str(row.get("state") or "").lower() == "open"),
    ]
    rows = []
    for source, source_rows, status_field, activity_field, is_open in source_defs:
        buckets = {
            label: {
                "source": source,
                "age_bucket": label,
                "bucket_order": order,
                "open_count": 0,
                "bug_count": 0,
                "feature_request_count": 0,
                "enhancement_count": 0,
                "unknown_activity_count": 0,
            }
            for label, order, _min_days, _max_days in bucket_defs
        }
        open_rows = [row for row in source_rows if is_open(row)]
        for row in open_rows:
            last_activity = parse_iso(row.get(activity_field))
            days = max(0, int((END - last_activity).total_seconds() // 86400)) if last_activity else None
            bucket = buckets[bucket_for(days)]
            bucket["open_count"] += 1
            if days is None:
                bucket["unknown_activity_count"] += 1
            if source == "Core":
                ticket_type = str(row.get("type") or "").lower()
                if ticket_type == "defect (bug)":
                    bucket["bug_count"] += 1
                elif ticket_type == "feature request":
                    bucket["feature_request_count"] += 1
                elif ticket_type == "enhancement":
                    bucket["enhancement_count"] += 1
            else:
                labels = str(row.get("labels") or "").lower()
                if "type: bug" in labels or "bug" in labels:
                    bucket["bug_count"] += 1
                if "type: feature" in labels or "feature" in labels:
                    bucket["feature_request_count"] += 1
                if "type: enhancement" in labels or "enhancement" in labels:
                    bucket["enhancement_count"] += 1
        open_total = len(open_rows)
        for label, order, _min_days, _max_days in bucket_defs:
            row = dict(buckets[label])
            row["open_total"] = open_total
            row["open_share_pct"] = round(row["open_count"] / open_total * 100, 2) if open_total else 0
            row["snapshot_at"] = END.isoformat().replace("+00:00", "Z")
            row["activity_field"] = activity_field
            row["status_field"] = status_field
            row["source_note"] = "Currently open backlog bucketed by age since last activity/update"
            rows.append(row)
    return rows


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
        ("Core first-response activity", "covered" if SOURCE_FILES["core_response_quarterly"].exists() else "missing", "Trac RSS first non-reporter activity for 2021-2026 tickets"),
        ("Gutenberg GitHub issues", "covered", "32k issues with labels, state, authors, close dates"),
        ("Gutenberg response/reopen timelines", "covered" if SOURCE_FILES["gutenberg_timeline_quarterly"].exists() else "missing", "GitHub comment timestamps and reopened events"),
        ("wordpress-develop PRs", "covered", "12k PRs with authors, dates, Trac links"),
        ("Project-member/outside split", "covered" if fetched.get("maintainer_participation_quarterly") else "missing", "Quarterly GitHub author_association split for Gutenberg issues and wordpress-develop PRs"),
        ("Contributor depth buckets", "covered" if fetched.get("contributor_depth_buckets") else "missing", "One-time, repeat, and sustained contributors across Core, Gutenberg, and PR activity"),
        ("Contributor concentration", "covered" if fetched.get("contributor_concentration_summary") else "missing", "Top 10, 25, and 50 contributor work share across Core, Gutenberg, and PR activity"),
        ("Ticket category classification", "covered", "Bug, feature request, enhancement, task, and other categories"),
        ("Open category backlog", "covered" if fetched.get("category_open_backlog_summary") else "missing", "Open bug, enhancement, feature-request, and other category composition"),
        ("Open backlog age buckets", "covered" if fetched.get("open_backlog_age_summary") else "missing", "Current open Core/Gutenberg backlog by last-activity age bucket"),
        ("W3Techs adoption", "covered" if fetched.get("market_share") else "missing", "All-site usage and CMS market-share yearly trends"),
        ("HTTP Archive/Web Almanac", "covered", "2025 CMS adoption snapshot and high-traffic context"),
        ("HTTP Archive Technology Report API", "covered" if fetched.get("http_archive_adoption_monthly") else "missing", "Monthly origin counts, derived tracked-share trend, and rank-tier detected-origin adoption for WordPress, Shopify, Wix, Squarespace, and Webflow"),
        ("HTTP Archive Core Web Vitals", "covered" if fetched.get("http_archive_cwv_monthly") else "missing", "Monthly good Core Web Vitals rates by technology from the HTTP Archive Technology Report API"),
        ("BuiltWith ecommerce history", "covered" if fetched.get("builtwith_technology_history") else "missing", "Shopify and WooCommerce live-site counts by traffic tier"),
        ("BuiltWith traffic tiers", "covered" if fetched.get("builtwith_tier_share_snapshot") else "missing", "Current WordPress share by traffic tier across tracked CMS/builder technologies"),
        ("Stack Overflow tag volume", "covered" if fetched.get("stack_overflow_tag_quarterly") else "missing", "Quarterly public developer-attention proxy from Stack Exchange API tag totals"),
        ("Wikimedia pageviews", "covered" if fetched.get("wikimedia_pageviews_quarterly") else "missing", "Quarterly en.wikipedia article pageviews as a public-interest proxy, not search-query volume"),
        ("HN hiring mentions", "partial" if fetched.get("hn_hiring_wordpress_quarterly") else "missing", "WordPress/WooCommerce, PHP, and agency/studio mentions in monthly Hacker News Who is hiring threads from 2012 onward; not a broad job-board index"),
        ("WordPress Jobs board", "partial" if fetched.get("wordpress_jobs_board_snapshots") else "missing", "Open-listing snapshots from jobs.wordpress.net current page and annual Internet Archive captures; WordPress-specific, not a broad hiring-platform index"),
        ("Attention and demand summary", "covered" if fetched.get("attention_demand_summary") else "missing", "Derived compact comparison of Stack Overflow, Wikimedia, HN hiring, and WordPress Jobs proxy direction"),
        ("Enterprise adoption signal", "covered" if fetched.get("enterprise_vip_case_studies") else "missing", "Current public WordPress VIP case-study snapshot with industries and use cases"),
        ("WordPress.org plugin/theme directories", "covered" if fetched.get("directory_snapshots") else "missing", "Current plugin and theme counts"),
        ("WordPress.org ecosystem stats", "covered" if fetched.get("wporg_ecosystem_stats_snapshot") else "missing", "Current WordPress, PHP, and database version distribution from WordPress.org stats APIs"),
        ("Plugin/theme directory activity", "covered" if fetched.get("directory_activity_snapshots") else "missing", "Current new, updated, and popular samples from WordPress.org directory APIs"),
        (
            "Major plugin install base",
            "covered" if fetched.get("major_plugin_install_snapshot") and fetched.get("major_plugin_install_history") else "partial" if fetched.get("major_plugin_install_snapshot") else "missing",
            "Current fixed-slug plugin API snapshot plus annual Wayback snapshots of archived WordPress.org plugin active-install buckets",
        ),
        ("Stale popular plugin sample", "covered" if fetched.get("plugin_maintenance_summary") else "missing", "Derived WordPress.org popular-plugin sample showing 2+ year stale count, install reach, and detail rows"),
        ("Major plugin support snapshot", "covered" if fetched.get("major_plugin_install_snapshot") else "missing", "Current WordPress.org plugin API support-thread and resolved-thread counts for the fixed major-plugin list"),
        ("Major plugin download trend", "covered" if fetched.get("major_plugin_download_quarterly") else "missing", "WordPress.org daily plugin download stats for the fixed major-plugin list, aggregated quarterly"),
        ("WordCamp Central", "covered" if fetched.get("wordcamps") else "missing", "Historical WordCamp event records and anticipated-attendance fields where available"),
        ("WordPress Events", "covered" if fetched.get("wp_events") else "missing", "Current upcoming Meetup and WordCamp events"),
        ("Translate WordPress", "covered" if fetched.get("translation_locale_snapshot") else "missing", "Current locale team profile counts and Core dev translation status"),
        ("Make/Core posts", "covered" if fetched.get("make_core_posts") else "missing", "Post counts and author IDs"),
        ("Make/Core comments", "covered" if fetched.get("make_core_comments") else "missing", "Comment counts and commenter identities from Make/Core REST API"),
        ("Make/Core dev notes", "covered" if fetched.get("make_core_dev_notes") else "missing", "Dev-note tagged posts by quarter and release"),
        ("Core release credits", "covered" if fetched.get("core_release_credits") else "missing", "WordPress.org credits API props by major release"),
        ("Core committers per release", "covered" if fetched.get("core_release_committers") else "missing", "GitHub tag-to-tag compare ranges by major release"),
        ("Core reopen rate", "covered" if fetched.get("core_reopen_quarterly") else "missing", "Quarterly Core Trac reopened status-change events"),
        ("Closure age summary", "covered" if fetched.get("closure_age_summary") else "missing", "Median, p75, and p90 days-to-close by quarter for Core and Gutenberg"),
        ("Five for the Future", "covered" if fetched.get("fttf_pledges") else "missing", "Current pledge organizations, hours, and listed profiles"),
        (
            "Newly detected sites",
            "partial" if SOURCE_FILES["builtwith_new_site_snapshot"].exists() else "missing",
            "Current BuiltWith Net New Pipeline snapshot plus HTTP Archive monthly origin counts, derived tracked-share trend, rank-tier detected-origin adoption, and a dedicated new-site choice companion view; multi-year new-site creation still needs paid BuiltWith or cohort queries",
        ),
        (
            "New-site choice summary",
            "covered" if fetched.get("new_site_choice_summary") else "missing",
            "Compact current proxy readout across BuiltWith 30/90-day pipeline, HTTP Archive tracked share, and traffic-tier presence",
        ),
        (
            "Support forums",
            "partial" if SOURCE_FILES["support_forum_topics"].exists() else "missing",
            "Current WordPress.org support queue snapshot with forum, status, last-activity, and age buckets; historical trend still needs a fuller export",
        ),
        (
            "Support unanswered summary",
            "covered" if fetched.get("support_forum_snapshot_summary") else "missing",
            "Current support snapshot summarized into resolved, unresolved, no-reply, and forum-level unanswered tables",
        ),
        (
            "Search interest and job demand",
            "partial" if fetched.get("wikimedia_pageviews_quarterly") or fetched.get("hn_hiring_wordpress_quarterly") else "missing",
            "General web search trends and broad hiring-platform time series are not included; Wikimedia, Stack Overflow, and HN are narrower public/developer/demand proxies",
        ),
    ]
    return rows


def build_report(data, fetched):
    core_q = data["core_quarterly"]
    gut_q = data["gutenberg_quarterly"]
    core_tickets = data["core_tickets"]
    core_events = data["core_events"]
    core_response_q = data["core_response_quarterly"]
    gut_issues = data["gutenberg_issues"]
    gut_jsonl = data["gutenberg_issues_jsonl"]
    gut_timeline_q = data["gutenberg_timeline_quarterly"]
    github_q = data["github_pr_quarterly"]
    github_prs = data["github_prs"]
    classifications = data["classification_trend"]
    market_rows = fetched.get("market_share", [])
    http_archive_adoption = fetched.get("http_archive_adoption_monthly", [])
    http_archive_tracked_share = fetched.get("http_archive_tracked_share_monthly", [])
    http_archive_rank_adoption = fetched.get("http_archive_rank_adoption_snapshot", [])
    http_archive_cwv = fetched.get("http_archive_cwv_monthly", [])
    wporg_ecosystem_stats = fetched.get("wporg_ecosystem_stats_snapshot", [])
    stack_overflow_tags = fetched.get("stack_overflow_tag_quarterly", [])
    wikimedia_pageviews_q = fetched.get("wikimedia_pageviews_quarterly", [])
    hn_hiring_q = fetched.get("hn_hiring_wordpress_quarterly", [])
    hn_hiring_summary = fetched.get("hn_hiring_demand_summary", [])
    attention_demand_summary = fetched.get("attention_demand_summary", [])
    wordpress_jobs_snapshots = fetched.get("wordpress_jobs_board_snapshots", [])
    wordpress_jobs_categories = fetched.get("wordpress_jobs_board_category_snapshots", [])
    enterprise_vip_cases = fetched.get("enterprise_vip_case_studies", [])
    wordcamps = fetched.get("wordcamps", [])
    wordcamp_yearly = fetched.get("wordcamp_yearly", [])
    wp_event_snapshots = fetched.get("wp_event_snapshots", [])
    wp_events = fetched.get("wp_events", [])
    make_posts = fetched.get("make_core_posts", [])
    make_comments = fetched.get("make_core_comments", [])
    make_comment_quarterly = fetched.get("make_core_comment_quarterly", [])
    translation_snapshots = fetched.get("translation_snapshots", [])
    translation_locales = fetched.get("translation_locale_snapshot", [])
    translation_core_dev = fetched.get("translation_core_dev_status", [])
    make_dev_notes = fetched.get("make_core_dev_notes", [])
    make_dev_note_quarterly = fetched.get("make_core_dev_note_quarterly", [])
    make_dev_note_releases = fetched.get("make_core_dev_note_releases", [])
    release_credits = fetched.get("core_release_credits", [])
    release_committers = fetched.get("core_release_committers", [])
    core_reopen_q = fetched.get("core_reopen_quarterly", [])
    closure_age_summary = fetched.get("closure_age_summary", [])
    fttf_snapshots = fetched.get("fttf_snapshots", [])
    fttf_pledges = fetched.get("fttf_pledges", [])
    directory = {row["metric"]: row for row in fetched.get("directory_snapshots", [])}
    directory_activity = fetched.get("directory_activity_snapshots", [])
    plugin_activity_rows = fetched.get("plugin_directory_activity_sample", [])
    plugin_maintenance_summary = fetched.get("plugin_maintenance_summary", [])
    plugin_stale_popular_sample = fetched.get("plugin_stale_popular_sample", [])
    major_plugin_rows = fetched.get("major_plugin_install_snapshot", [])
    major_plugin_install_history = fetched.get("major_plugin_install_history", [])
    major_plugin_download_daily = fetched.get("major_plugin_download_daily", [])
    major_plugin_download_q = fetched.get("major_plugin_download_quarterly", [])
    theme_activity_rows = fetched.get("theme_directory_activity_sample", [])
    support_topics = data["support_forum_topics"]
    support_views = data["support_forum_view_snapshots"]
    support_forums = data["support_forum_forum_summary"]
    support_monthly = fetched.get("support_forum_activity_monthly", [])
    support_age_buckets = fetched.get("support_forum_age_buckets", [])
    support_snapshot_summary = fetched.get("support_forum_snapshot_summary", [])
    support_unanswered_by_forum = fetched.get("support_forum_unanswered_by_forum", [])
    builtwith_new_sites = data["builtwith_new_site_snapshot"]
    builtwith_tier_share = fetched.get("builtwith_tier_share_snapshot", [])
    new_site_choice_summary = fetched.get("new_site_choice_summary", [])
    builtwith_technology_snapshots = fetched.get("builtwith_technology_snapshots", [])
    builtwith_technology_history = fetched.get("builtwith_technology_history", [])
    contributor_depth = fetched.get("contributor_depth_buckets", [])
    contributor_concentration_summary = fetched.get("contributor_concentration_summary", [])
    maintainer_participation = fetched.get("maintainer_participation_quarterly", [])
    category_open_backlog = fetched.get("category_open_backlog_summary", [])
    open_backlog_age = fetched.get("open_backlog_age_summary", [])

    core_latest = current_latest(core_q)
    gut_latest = current_latest(gut_q)
    pr_latest = current_latest(github_q)

    core_created_prev = average(core_q, "created", "2021-01-01", "2024-01-01")
    core_created_recent = average(core_q, "created", "2024-01-01")
    core_closed_recent = average(core_q, "closed", "2024-01-01")
    core_first_prev = average(core_q, "first_time_reporters", "2021-01-01", "2024-01-01")
    core_first_recent = average(core_q, "first_time_reporters", "2024-01-01")
    gut_created_prev = average(gut_q, "created", "2021-01-01", "2024-01-01")
    gut_created_recent = average(gut_q, "created", "2024-01-01")
    gut_closed_recent = average(gut_q, "closed", "2024-01-01")
    gut_first_prev = average(gut_q, "first_time_creators", "2021-01-01", "2024-01-01")
    gut_first_recent = average(gut_q, "first_time_creators", "2024-01-01")
    pr_created_prev = average(github_q, "created", "2021-01-01", "2024-01-01")
    pr_created_recent = average(github_q, "created", "2024-01-01")
    core_first_retention = core_first_recent / core_first_prev * 100 if core_first_prev else 0
    gut_first_retention = gut_first_recent / gut_first_prev * 100 if gut_first_prev else 0
    pr_flow_ratio = pr_created_recent / pr_created_prev * 100 if pr_created_prev else 0
    core_closure_ratio = core_closed_recent / core_created_recent * 100 if core_created_recent else 0
    gut_closure_ratio = gut_closed_recent / gut_created_recent * 100 if gut_created_recent else 0

    core_close_age, core_reopened, core_closed_ids = compute_close_age_core(core_tickets, core_events)
    gut_close_age = compute_close_age_gutenberg(gut_jsonl)
    core_stale, core_open, core_stale_pct = stale_open_share_core(core_tickets)
    gut_stale, gut_open, gut_stale_pct = stale_open_share_gutenberg(gut_jsonl)
    reopened_pct = len(core_reopened) / len(core_closed_ids) * 100 if core_closed_ids else 0

    def as_float(value, default=0.0):
        try:
            if value in (None, ""):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    closure_rows_by_source = {
        source: sorted(
            [row for row in closure_age_summary if row.get("source") == source],
            key=lambda row: row.get("quarter", ""),
        )
        for source in ("Core", "Gutenberg")
    }
    latest_core_closure_age = closure_rows_by_source["Core"][-1] if closure_rows_by_source["Core"] else {}
    latest_gut_closure_age = closure_rows_by_source["Gutenberg"][-1] if closure_rows_by_source["Gutenberg"] else {}
    core_recent_closure_median = median(
        [
            as_float(row.get("median_days_to_close"))
            for row in closure_rows_by_source["Core"]
            if row.get("quarter", "") >= "2024-01-01"
        ]
    )
    gut_recent_closure_median = median(
        [
            as_float(row.get("median_days_to_close"))
            for row in closure_rows_by_source["Gutenberg"]
            if row.get("quarter", "") >= "2024-01-01"
        ]
    )
    max_latest_closure_days = max(
        as_float(latest_core_closure_age.get("p90_days_to_close")),
        as_float(latest_gut_closure_age.get("p90_days_to_close")),
        as_float(latest_core_closure_age.get("median_days_to_close")),
        as_float(latest_gut_closure_age.get("median_days_to_close")),
        core_recent_closure_median or 0,
        gut_recent_closure_median or 0,
        1,
    )

    concentration_by_key = {
        (row.get("source"), row.get("window")): row
        for row in contributor_concentration_summary
    }

    def conc_metric(source, window, field):
        return float(concentration_by_key.get((source, window), {}).get(field) or 0)

    depth_by_key = {
        (row.get("source"), row.get("window"), row.get("bucket")): row
        for row in contributor_depth
    }

    def depth_metric(source, bucket, field, window="since_2024"):
        return float(depth_by_key.get((source, window, bucket), {}).get(field) or 0)

    depth_sources = [
        ("Core Trac reporters", "Core", COLORS["core"]),
        ("Gutenberg issue creators", "Gutenberg", COLORS["gutenberg"]),
        ("wordpress-develop PR authors", "PRs", COLORS["prs"]),
    ]
    maintainer_latest_by_source = {
        source: max(
            [row for row in maintainer_participation if row.get("source") == source],
            key=lambda row: row.get("quarter", ""),
            default={},
        )
        for source in ("Gutenberg issues", "wordpress-develop PRs")
    }

    def maintainer_points(source, field, start="2021-01-01"):
        return [
            (row.get("quarter"), num(row.get(field)))
            for row in sorted(maintainer_participation, key=lambda item: (item.get("source", ""), item.get("quarter", "")))
            if row.get("source") == source and row.get("quarter", "") >= start
        ]

    wp_usage_latest = market_latest(market_rows, "all_sites_usage", "WordPress")
    wp_usage_2025 = next((r for r in market_rows if r["metric"] == "all_sites_usage" and r["technology"] == "WordPress" and r["date"] == "2025-01-01"), None)
    wp_cms_latest = market_latest(market_rows, "cms_market_share", "WordPress")
    wp_cms_2025 = next((r for r in market_rows if r["metric"] == "cms_market_share" and r["technology"] == "WordPress" and r["date"] == "2025-01-01"), None)
    usage_delta = (wp_usage_latest["value"] - wp_usage_2025["value"]) if wp_usage_latest and wp_usage_2025 else None
    cms_delta = (wp_cms_latest["value"] - wp_cms_2025["value"]) if wp_cms_latest and wp_cms_2025 else None

    member_points = point_series(gut_q, "quarter", "member_created", "2021-01-01")
    community_points = point_series(gut_q, "quarter", "community_created", "2021-01-01")
    core_repeat_reporter_points = difference_series(core_q, "quarter", "unique_reporters", "first_time_reporters", "2021-01-01")
    gut_repeat_creator_points = difference_series(gut_q, "quarter", "unique_creators", "first_time_creators", "2021-01-01")
    pr_repeat_author_points = difference_series(github_q, "quarter", "unique_authors", "first_time_authors", "2021-01-01")
    core_make_posts = count_by_quarter(make_posts, "date")
    core_make_authors = count_by_quarter(make_posts, "date", distinct_key="author")
    make_comment_points = point_series(make_comment_quarterly, "quarter", "comments", "2009-01-01")
    make_commenter_points = point_series(make_comment_quarterly, "quarter", "unique_commenters", "2009-01-01")
    make_comment_post_points = point_series(make_comment_quarterly, "quarter", "posts_commented_on", "2009-01-01")
    latest_make_comment_quarter = max(make_comment_quarterly, key=lambda row: row.get("quarter", "")) if make_comment_quarterly else {}
    make_comment_conc_recent = contributor_concentration(make_comments, "commenter_key", "date", "2024-01-01")
    dev_note_quarter_points = point_series(make_dev_note_quarterly, "quarter", "dev_notes", "2008-01-01")
    dev_note_author_points = point_series(make_dev_note_quarterly, "quarter", "unique_authors", "2008-01-01")
    wordcamp_years = count_by_year(wordcamps, "start_date")
    wordcamp_attendance_points = point_series(wordcamp_yearly, "year", "anticipated_attendance", "2006-01-01")
    wordcamp_attendance_coverage_points = point_series(wordcamp_yearly, "year", "events_with_attendance_estimate", "2006-01-01")
    latest_wordcamp_year = max(wordcamp_yearly, key=lambda row: row.get("year", "")) if wordcamp_yearly else {}
    latest_complete_wordcamp_year = max(
        [row for row in wordcamp_yearly if row.get("year", "") <= f"{END.year - 1:04d}-01-01"],
        key=lambda row: row.get("year", ""),
    ) if wordcamp_yearly else {}
    max_wordcamp_year_events = max([num(row.get("events")) for row in wordcamp_yearly] or [1])
    max_wordcamp_year_attendance = max([num(row.get("anticipated_attendance")) for row in wordcamp_yearly] or [1])
    translation_snapshot = translation_snapshots[0] if translation_snapshots else {}
    top_translation_locales = sorted(translation_locales, key=lambda row: num(row.get("contributors")), reverse=True)[:8]
    max_translation_contributors = max([num(row.get("contributors")) for row in top_translation_locales] or [0])
    translation_locale_count = max(1, num(translation_snapshot.get("locale_count")))
    translation_core_count = max(1, num(translation_snapshot.get("core_dev_locale_count")))
    release_credit_points = [(row["release_date"], num(row.get("props_count"))) for row in release_credits]
    release_noteworthy_points = [(row["release_date"], num(row.get("noteworthy_count"))) for row in release_credits]
    latest_release_credit = max(release_credits, key=lambda row: row.get("release_date", "")) if release_credits else {}
    release_committer_points = [(row["release_date"], num(row.get("committer_count"))) for row in release_committers]
    latest_release_committer = max(release_committers, key=lambda row: row.get("release_date", "")) if release_committers else {}
    release_dates = {str(row.get("version")): str(row.get("release_date")) for row in fetched.get("core_releases", [])}
    dev_note_release_points = [
        (release_dates.get(str(row.get("version")), str(row.get("last_post_date", ""))[:10]), num(row.get("dev_notes")))
        for row in make_dev_note_releases
        if release_dates.get(str(row.get("version"))) or row.get("last_post_date")
    ]
    latest_dev_note_release = max(
        make_dev_note_releases,
        key=lambda row: release_dates.get(str(row.get("version")), str(row.get("last_post_date", ""))),
    ) if make_dev_note_releases else {}
    latest_core_reopen = max(core_reopen_q, key=lambda row: row.get("quarter", "")) if core_reopen_q else {}
    latest_core_response = max(core_response_q, key=lambda row: row.get("quarter", "")) if core_response_q else {}
    latest_gut_timeline = max(gut_timeline_q, key=lambda row: row.get("quarter", "")) if gut_timeline_q else {}
    core_reopen_rate_points = point_series(core_reopen_q, "quarter", "reopened_events_per_100_closed", "2021-01-01")
    gut_reopen_rate_points = point_series(gut_timeline_q, "quarter", "reopened_events_per_100_closed", "2021-01-01")
    core_first_response_points = point_series(core_response_q, "quarter", "median_first_non_reporter_activity_hours", "2021-01-01")
    gut_first_response_points = point_series(gut_timeline_q, "quarter", "median_first_non_author_response_hours", "2021-01-01")
    gut_maintainer_response_points = point_series(gut_timeline_q, "quarter", "median_first_maintainer_response_hours", "2021-01-01")
    max_reopen_rate = max(
        [value for _date, value in core_reopen_rate_points + gut_reopen_rate_points] or [1]
    )
    max_gut_response_hours = max(
        [value for _date, value in core_first_response_points + gut_first_response_points + gut_maintainer_response_points] or [1]
    )
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
    support_view_by_name = {row.get("view"): row for row in support_views}
    support_topic_count = len(support_topics)
    support_resolved_count = sum(1 for row in support_topics if row.get("is_resolved") == "1")
    support_unresolved_count = sum(1 for row in support_topics if row.get("is_unresolved") == "1")
    support_no_reply_count = sum(1 for row in support_topics if row.get("has_no_replies") == "1")
    support_recent_count = num(support_view_by_name.get("all_topics", {}).get("unique_topics"))
    support_view_count = len([row for row in support_views if row.get("view")])
    support_oldest = min([row.get("last_activity_at") for row in support_topics if row.get("last_activity_at")] or [""])
    support_latest = max([row.get("last_activity_at") for row in support_topics if row.get("last_activity_at")] or [""])
    support_queue_max = max(support_resolved_count, support_unresolved_count, support_no_reply_count, support_recent_count, 1)
    support_month_topic_points = point_series(support_monthly, "month", "topics")
    support_month_unresolved_points = point_series(support_monthly, "month", "unresolved")
    support_month_resolved_points = point_series(support_monthly, "month", "resolved")
    support_month_no_reply_points = point_series(support_monthly, "month", "no_replies")
    support_age_ordered = sorted(support_age_buckets, key=lambda row: num(row.get("bucket_order")))
    support_age_max = max([num(row.get("topics")) for row in support_age_ordered] or [1])
    support_unresolved_age_max = max([num(row.get("unresolved")) for row in support_age_ordered] or [1])
    support_unresolved_31_plus = sum(
        num(row.get("unresolved"))
        for row in support_age_ordered
        if row.get("age_bucket") in {"31-90 days", "91-180 days", "181+ days"}
    )
    support_unresolved_91_plus = sum(
        num(row.get("unresolved"))
        for row in support_age_ordered
        if row.get("age_bucket") in {"91-180 days", "181+ days"}
    )
    support_unresolved_share = (
        support_unresolved_count / support_topic_count * 100
        if support_topic_count
        else 0
    )
    support_summary = support_snapshot_summary[0] if support_snapshot_summary else {}
    support_resolved_share = float(support_summary.get("resolved_share_pct") or (support_resolved_count / support_topic_count * 100 if support_topic_count else 0))
    support_no_reply_share = float(support_summary.get("no_reply_share_pct") or (support_no_reply_count / support_topic_count * 100 if support_topic_count else 0))
    top_support_unanswered_forums = sorted(
        support_unanswered_by_forum or support_forums,
        key=lambda row: (num(row.get("unresolved") or row.get("unresolved_topics")), num(row.get("no_replies") or row.get("no_reply_topics"))),
        reverse=True,
    )[:8]
    max_support_unanswered_forum = max([num(row.get("unresolved") or row.get("unresolved_topics")) for row in top_support_unanswered_forums] or [1])
    builtwith_by_tech = {row.get("technology"): row for row in builtwith_new_sites}
    builtwith_new_rows = [row for row in builtwith_new_sites if num(row.get("new_last_3_months")) > 0]
    builtwith_max_90 = max([num(row.get("new_last_3_months")) for row in builtwith_new_rows] or [1])
    builtwith_total_90 = sum(num(row.get("new_last_3_months")) for row in builtwith_new_rows)
    builtwith_total_30 = sum(num(row.get("new_last_month")) for row in builtwith_new_rows)
    builtwith_wp_90 = num(builtwith_by_tech.get("WordPress", {}).get("new_last_3_months"))
    builtwith_wp_30 = num(builtwith_by_tech.get("WordPress", {}).get("new_last_month"))
    builtwith_wp_90_share = builtwith_wp_90 / builtwith_total_90 * 100 if builtwith_total_90 else 0
    builtwith_wp_30_share = builtwith_wp_30 / builtwith_total_30 * 100 if builtwith_total_30 else 0
    new_site_summary_by_signal = {row.get("signal"): row for row in new_site_choice_summary}
    new_site_summary_rows = [
        new_site_summary_by_signal[key]
        for key in [
            "builtwith_90_day_pipeline",
            "builtwith_30_day_pipeline",
            "http_archive_latest_tracked_share",
            "http_archive_tracked_share_change",
            "builtwith_top_1m_tracked_share",
            "builtwith_long_tail_tracked_share",
        ]
        if key in new_site_summary_by_signal
    ]
    new_site_summary_cards = []
    new_site_summary_bars = []
    for row in new_site_summary_rows:
        signal = str(row.get("signal") or "")
        share_value = float(row.get("wordpress_share_pct") or 0)
        wp_value = float(row.get("wordpress_value") or 0)
        unit = str(row.get("unit") or "")
        if signal == "http_archive_tracked_share_change":
            card_value = f"{wp_value:+.1f} pts"
            tone = "watch" if wp_value < 0 else "soft"
            bar_value = abs(wp_value)
            bar_max = max(10, bar_value)
            suffix = " pts"
        elif "tracked_share" in signal:
            card_value = pct(wp_value)
            tone = "good" if wp_value >= 70 else "soft"
            bar_value = wp_value
            bar_max = 100
            suffix = "%"
        else:
            card_value = pct(share_value)
            tone = "soft"
            bar_value = share_value
            bar_max = 100
            suffix = "%"
        note = str(row.get("period") or "")
        if row.get("next_peer"):
            note = f"{note}; next: {row.get('next_peer')} {compact(float(row.get('next_peer_value') or 0))}"
        new_site_summary_cards.append(stat_card(str(row.get("label", "")), card_value, note, tone))
        new_site_summary_bars.append(
            horizontal_count_metric(
                str(row.get("label", "")),
                bar_value,
                bar_max,
                COLORS["green"] if tone == "good" else COLORS["core"] if tone == "soft" else COLORS["orange"],
                suffix,
            )
        )
    builtwith_top_tiers = ["top_1000", "top_10k", "top_100k", "top_1m"]
    builtwith_tier_share_ordered = sorted(builtwith_tier_share, key=lambda row: num(row.get("tier_order")))
    builtwith_live_by_tech = {row.get("technology"): row for row in builtwith_technology_snapshots}
    builtwith_live_rows = [row for row in builtwith_technology_snapshots if num(row.get("total_live")) > 0]
    builtwith_live_max = max([num(row.get("total_live")) for row in builtwith_live_rows] or [1])
    builtwith_ecommerce_history_techs = [
        ("Shopify", COLORS["shopify"]),
        ("WooCommerce", COLORS["purple"]),
    ]
    builtwith_ecommerce_live_rows = [row for row in builtwith_live_rows if row.get("category") == "eCommerce"]
    builtwith_ecommerce_live_max = max([num(row.get("total_live")) for row in builtwith_ecommerce_live_rows] or [1])
    builtwith_total_live_series = [
        {
            "label": tech,
            "color": color,
            "points": sorted(
                (row["date"], num(row.get("entire_internet")))
                for row in builtwith_technology_history
                if row.get("technology") == tech and row.get("date") >= "2010-01-01"
            ),
        }
        for tech, color in builtwith_ecommerce_history_techs
    ]
    builtwith_top1m_series = [
        {
            "label": tech,
            "color": color,
            "points": sorted(
                (row["date"], num(row.get("top_1m")))
                for row in builtwith_technology_history
                if row.get("technology") == tech and row.get("date") >= "2010-01-01"
            ),
        }
        for tech, color in builtwith_ecommerce_history_techs
    ]
    woocommerce_builtwith = builtwith_live_by_tech.get("WooCommerce", {})
    woocommerce_plugin = max(
        [row for row in plugin_activity_rows if row.get("slug") == "woocommerce"],
        key=lambda row: num(row.get("active_installs")),
        default={},
    )

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

    def category_points(source, category):
        return sorted(
            (date_value, value)
            for (row_source, row_category, date_value), value in classification_by_source_cat.items()
            if row_source == source and row_category == category and date_value >= "2021-01-01"
        )

    core_category_series = [
        {"label": "All Core tickets", "color": COLORS["core"], "points": point_series(core_q, "quarter", "created", "2021-01-01")},
        {"label": "Core bugs", "color": COLORS["red"], "points": category_points("core", "bug")},
        {"label": "Core feature requests", "color": COLORS["purple"], "points": category_points("core", "feature_request")},
    ]
    gut_category_series = [
        {"label": "All Gutenberg issues", "color": COLORS["gutenberg"], "points": point_series(gut_q, "quarter", "created", "2021-01-01")},
        {"label": "Gutenberg bugs", "color": COLORS["red"], "points": category_points("gutenberg", "bug")},
        {"label": "Gutenberg feature requests", "color": COLORS["purple"], "points": category_points("gutenberg", "feature_request")},
    ]
    category_colors = {
        "bug": COLORS["red"],
        "enhancement": COLORS["community"],
        "feature_request": COLORS["purple"],
        "task_maintenance": COLORS["neutral"],
        "documentation": COLORS["core"],
        "support_question": COLORS["orange"],
        "other": COLORS["neutral"],
    }
    core_open_category_rows = sorted(
        [row for row in category_open_backlog if row.get("source") == "Core"],
        key=lambda row: num(row.get("open_count")),
        reverse=True,
    )
    gut_open_category_rows = sorted(
        [row for row in category_open_backlog if row.get("source") == "Gutenberg"],
        key=lambda row: num(row.get("open_count")),
        reverse=True,
    )
    category_open_max = max(
        [num(row.get("open_count")) for row in core_open_category_rows + gut_open_category_rows] or [1]
    )
    core_open_total = sum(num(row.get("open_count")) for row in core_open_category_rows)
    gut_open_total = sum(num(row.get("open_count")) for row in gut_open_category_rows)
    core_bug_open_share = next(
        (float(row.get("open_category_share_pct") or 0) for row in core_open_category_rows if row.get("category") == "bug"),
        0,
    )
    gut_bug_open_share = next(
        (float(row.get("open_category_share_pct") or 0) for row in gut_open_category_rows if row.get("category") == "bug"),
        0,
    )
    core_open_age_rows = sorted(
        [row for row in open_backlog_age if row.get("source") == "Core"],
        key=lambda row: num(row.get("bucket_order")),
    )
    gut_open_age_rows = sorted(
        [row for row in open_backlog_age if row.get("source") == "Gutenberg"],
        key=lambda row: num(row.get("bucket_order")),
    )
    open_age_max = max([num(row.get("open_count")) for row in core_open_age_rows + gut_open_age_rows] or [1])
    core_open_2y_plus = sum(
        num(row.get("open_count")) for row in core_open_age_rows if row.get("age_bucket") in {"2-5 years", "5+ years"}
    )
    gut_open_2y_plus = sum(
        num(row.get("open_count")) for row in gut_open_age_rows if row.get("age_bucket") in {"2-5 years", "5+ years"}
    )
    core_open_2y_share = core_open_2y_plus / core_open * 100 if core_open else 0
    gut_open_2y_share = gut_open_2y_plus / gut_open * 100 if gut_open else 0

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
    http_archive_adoption_series = [
        {
            "label": row["label"],
            "color": row["color"],
            "points": sorted(
                (item["date"], num(item.get("mobile_origins")))
                for item in http_archive_adoption
                if item.get("technology") == row["technology"]
            ),
        }
        for row in HTTP_ARCHIVE_ADOPTION_TECHNOLOGIES
    ]
    http_archive_share_series = [
        {
            "label": row["label"],
            "color": row["color"],
            "points": sorted(
                (item["date"], float(item.get("mobile_tracked_share_pct") or 0))
                for item in http_archive_tracked_share
                if item.get("technology") == row["technology"]
            ),
        }
        for row in HTTP_ARCHIVE_ADOPTION_TECHNOLOGIES
    ]
    http_share_dates = sorted({row.get("date", "") for row in http_archive_tracked_share if row.get("date")})
    http_share_first_date = http_share_dates[0] if http_share_dates else ""
    http_share_latest_date = http_share_dates[-1] if http_share_dates else ""
    http_share_latest_rows = [
        row for row in http_archive_tracked_share
        if row.get("date") == http_share_latest_date
    ]
    http_share_first_wp = next(
        (
            row for row in http_archive_tracked_share
            if row.get("technology") == "WordPress" and row.get("date") == http_share_first_date
        ),
        {},
    )
    http_share_latest_wp = next(
        (row for row in http_share_latest_rows if row.get("technology") == "WordPress"),
        {},
    )
    http_share_latest_peer = max(
        [row for row in http_share_latest_rows if row.get("technology") != "WordPress"],
        key=lambda row: float(row.get("mobile_tracked_share_pct") or 0),
        default={},
    )
    http_share_wp_delta = (
        float(http_share_latest_wp.get("mobile_tracked_share_pct") or 0)
        - float(http_share_first_wp.get("mobile_tracked_share_pct") or 0)
        if http_share_latest_wp and http_share_first_wp
        else None
    )
    http_share_latest_wp_label = pct(float(http_share_latest_wp.get("mobile_tracked_share_pct") or 0)) if http_share_latest_wp else "n/a"
    http_share_wp_delta_label = f"{http_share_wp_delta:+.1f} pts" if http_share_wp_delta is not None else "n/a"
    http_archive_dates = sorted({row.get("date", "") for row in http_archive_adoption if row.get("date")})
    http_archive_latest_date = http_archive_dates[-1] if http_archive_dates else ""
    http_archive_first_date = http_archive_dates[0] if http_archive_dates else ""
    http_archive_latest_rows = {
        technology: max(
            [row for row in http_archive_adoption if row.get("technology") == technology],
            key=lambda row: row.get("date", ""),
            default={},
        )
        for technology in [row["technology"] for row in HTTP_ARCHIVE_ADOPTION_TECHNOLOGIES]
    }
    http_wp_latest = http_archive_latest_rows.get("WordPress", {})
    http_next_peer = max(
        [row for tech, row in http_archive_latest_rows.items() if tech != "WordPress"],
        key=lambda row: num(row.get("mobile_origins")),
        default={},
    )
    http_peer_ratio = (
        num(http_wp_latest.get("mobile_origins")) / num(http_next_peer.get("mobile_origins"))
        if num(http_next_peer.get("mobile_origins"))
        else 0
    )
    http_archive_cwv_series = [
        {
            "label": row["label"],
            "color": row["color"],
            "points": sorted(
                (item["date"], float(item.get("mobile_good_pct") or 0))
                for item in http_archive_cwv
                if item.get("technology") == row["technology"] and item.get("metric") == "overall"
            ),
        }
        for row in HTTP_ARCHIVE_ADOPTION_TECHNOLOGIES
    ]
    http_cwv_dates = sorted({row.get("date", "") for row in http_archive_cwv if row.get("date")})
    http_cwv_latest_date = http_cwv_dates[-1] if http_cwv_dates else ""
    http_cwv_latest_rows = {
        technology: max(
            [
                row for row in http_archive_cwv
                if row.get("technology") == technology and row.get("metric") == "overall"
            ],
            key=lambda row: row.get("date", ""),
            default={},
        )
        for technology in [row["technology"] for row in HTTP_ARCHIVE_ADOPTION_TECHNOLOGIES]
    }
    http_cwv_wp_latest = http_cwv_latest_rows.get("WordPress", {})
    http_cwv_best_peer = max(
        [row for tech, row in http_cwv_latest_rows.items() if tech != "WordPress"],
        key=lambda row: float(row.get("mobile_good_pct") or 0),
        default={},
    )
    http_cwv_gap = (
        float(http_cwv_wp_latest.get("mobile_good_pct") or 0) - float(http_cwv_best_peer.get("mobile_good_pct") or 0)
        if http_cwv_wp_latest and http_cwv_best_peer
        else 0
    )
    http_rank_summary = []
    for rank_config in HTTP_ARCHIVE_RANKS:
        rank_rows = [
            row for row in http_archive_rank_adoption
            if row.get("rank") == rank_config["rank"]
        ]
        if not rank_rows:
            continue
        tracked_mobile = sum(num(row.get("mobile_origins")) for row in rank_rows)
        wp_rank_row = next((row for row in rank_rows if row.get("technology") == "WordPress"), {})
        peer_rank_row = max(
            [row for row in rank_rows if row.get("technology") != "WordPress"],
            key=lambda row: num(row.get("mobile_origins")),
            default={},
        )
        wp_mobile = num(wp_rank_row.get("mobile_origins"))
        peer_mobile = num(peer_rank_row.get("mobile_origins"))
        http_rank_summary.append(
            {
                "rank": rank_config["rank"],
                "rank_order": rank_config["rank_order"],
                "date": wp_rank_row.get("date") or max([row.get("date", "") for row in rank_rows] or [""]),
                "wp_mobile_origins": wp_mobile,
                "tracked_mobile_origins": tracked_mobile,
                "wp_tracked_share_pct": wp_mobile / tracked_mobile * 100 if tracked_mobile else 0,
                "next_peer": peer_rank_row.get("technology", ""),
                "next_peer_mobile_origins": peer_mobile,
                "wp_peer_ratio": wp_mobile / peer_mobile if peer_mobile else 0,
            }
        )
    http_rank_summary = sorted(http_rank_summary, key=lambda row: num(row.get("rank_order")))
    http_rank_latest_date = max([row.get("date", "") for row in http_rank_summary if row.get("date")] or [""])
    http_rank_max_wp = max([num(row.get("wp_mobile_origins")) for row in http_rank_summary] or [1])
    http_rank_top1m = next((row for row in http_rank_summary if row.get("rank") == "Top 1M"), {})
    wporg_stats_by_metric = defaultdict(list)
    for row in wporg_ecosystem_stats:
        wporg_stats_by_metric[row.get("metric")].append(row)
    top_wp_versions = sorted(wporg_stats_by_metric.get("wordpress_version", []), key=lambda row: float(row.get("share_pct") or 0), reverse=True)[:8]
    top_php_versions = sorted(wporg_stats_by_metric.get("php_version", []), key=lambda row: float(row.get("share_pct") or 0), reverse=True)[:8]
    db_family_share = Counter()
    for row in wporg_stats_by_metric.get("database_version", []):
        db_family_share[row.get("family") or "Other"] += float(row.get("share_pct") or 0)
    db_family_rows = [
        {"family": family, "share_pct": round(share, 1)}
        for family, share in sorted(db_family_share.items(), key=lambda item: item[1], reverse=True)
    ]
    top_wp_version = top_wp_versions[0] if top_wp_versions else {}
    top_php_version = top_php_versions[0] if top_php_versions else {}
    php_81_plus_share = sum(
        float(row.get("share_pct") or 0)
        for row in wporg_stats_by_metric.get("php_version", [])
        if re.match(r"^8\.[1-9]", str(row.get("label") or ""))
    )
    mariadb_share = db_family_share.get("MariaDB", 0)
    mysql_share = db_family_share.get("MySQL", 0)
    wporg_stats_snapshot_date = max([row.get("snapshot_date", "") for row in wporg_ecosystem_stats if row.get("snapshot_date")] or [""])
    stack_overflow_tag_series = [
        {
            "label": tag_config["label"],
            "color": tag_config["color"],
            "points": sorted(
                (row["quarter"], num(row.get("question_count")))
                for row in stack_overflow_tags
                if row.get("tag") == tag_config["tag"]
            ),
        }
        for tag_config in STACK_OVERFLOW_TAGS
    ]
    latest_so_wp = max(
        [row for row in stack_overflow_tags if row.get("tag") == "wordpress"],
        key=lambda row: row.get("quarter", ""),
        default={},
    )
    previous_so_wp = max(
        [row for row in stack_overflow_tags if row.get("tag") == "wordpress" and row.get("quarter", "") < "2024-01-01"],
        key=lambda row: row.get("quarter", ""),
        default={},
    )
    so_wp_delta = num(latest_so_wp.get("question_count")) - num(previous_so_wp.get("question_count")) if latest_so_wp and previous_so_wp else None
    so_expected_quarters = [quarter.strftime("%Y-%m-%d") for quarter, _ in quarter_ranges(STACK_OVERFLOW_TAG_START, END)]
    so_expected_set = set(so_expected_quarters)
    so_expected_label = (
        f"{quarter_label(so_expected_quarters[0])} to {quarter_label(so_expected_quarters[-1])}"
        if so_expected_quarters
        else "expected range"
    )
    so_full_history_labels = []
    so_partial_history_labels = []
    for tag_config in STACK_OVERFLOW_TAGS:
        observed = {
            row.get("quarter")
            for row in stack_overflow_tags
            if row.get("tag") == tag_config["tag"] and row.get("quarter")
        }
        if observed and observed == so_expected_set:
            so_full_history_labels.append(tag_config["label"])
        elif observed:
            so_partial_history_labels.append(f"{tag_config['label']} {len(observed)}/{len(so_expected_quarters)}")
        else:
            so_partial_history_labels.append(f"{tag_config['label']} 0/{len(so_expected_quarters)}")
    so_coverage_detail = (
        f"Full {so_expected_label} coverage: {', '.join(so_full_history_labels) if so_full_history_labels else 'none'}. "
        f"Partial coverage: {', '.join(so_partial_history_labels) if so_partial_history_labels else 'none'}."
    )
    wikimedia_pageview_series = [
        {
            "label": config["label"],
            "color": config["color"],
            "points": sorted(
                (row["quarter"], num(row.get("views")))
                for row in wikimedia_pageviews_q
                if row.get("article") == config["article"] and row.get("quarter") >= "2016-01-01"
            ),
        }
        for config in WIKIMEDIA_PAGEVIEW_ARTICLES
    ]
    latest_wikimedia_wp = max(
        [row for row in wikimedia_pageviews_q if row.get("article") == "WordPress"],
        key=lambda row: row.get("quarter", ""),
        default={},
    )
    previous_wikimedia_wp = max(
        [row for row in wikimedia_pageviews_q if row.get("article") == "WordPress" and row.get("quarter", "") < "2024-01-01"],
        key=lambda row: row.get("quarter", ""),
        default={},
    )
    wikimedia_wp_delta = (
        num(latest_wikimedia_wp.get("views")) - num(previous_wikimedia_wp.get("views"))
        if latest_wikimedia_wp and previous_wikimedia_wp
        else None
    )
    hn_hiring_series = [
        {
            "label": "WordPress/WooCommerce",
            "color": COLORS["wordpress"],
            "points": point_series(hn_hiring_q, "quarter", "wordpress_or_woocommerce_comments"),
        },
        {
            "label": "PHP",
            "color": COLORS["purple"],
            "points": point_series(hn_hiring_q, "quarter", "php_comments"),
        },
        {
            "label": "Agency/studio",
            "color": COLORS["orange"],
            "points": point_series(hn_hiring_q, "quarter", "agency_comments"),
        },
    ]
    hn_hiring_rate_series = [
        {
            "label": "WP/Woo mentions per 100 posts",
            "color": COLORS["wordpress"],
            "points": point_series(hn_hiring_q, "quarter", "wordpress_or_woocommerce_per_100_comments"),
        },
        {
            "label": "PHP mentions per 100 posts",
            "color": COLORS["purple"],
            "points": point_series(hn_hiring_q, "quarter", "php_per_100_comments"),
        },
        {
            "label": "Agency/studio mentions per 100 posts",
            "color": COLORS["orange"],
            "points": point_series(hn_hiring_q, "quarter", "agency_per_100_comments"),
        }
    ]
    latest_hn_hiring = max(hn_hiring_q, key=lambda row: row.get("quarter", ""), default={})
    hn_hiring_summary_by_window = {row.get("window"): row for row in hn_hiring_summary}
    hn_since_2024 = hn_hiring_summary_by_window.get("since_2024", {})
    hn_latest_4q = hn_hiring_summary_by_window.get("latest_4q", {})
    hn_hiring_months = sum(num(row.get("months_with_thread")) for row in hn_hiring_q)
    hn_hiring_first = min([row.get("quarter", "") for row in hn_hiring_q if row.get("quarter")], default="")
    hn_hiring_latest = max([row.get("quarter", "") for row in hn_hiring_q if row.get("quarter")], default="")
    hn_hiring_range_label = (
        f"{quarter_label(hn_hiring_first)} to {quarter_label(hn_hiring_latest)}"
        if hn_hiring_first and hn_hiring_latest
        else "not fetched"
    )
    hn_demand_mentions_max = max(
        num(hn_latest_4q.get("wordpress_or_woocommerce_comments")),
        num(hn_latest_4q.get("php_comments")),
        num(hn_latest_4q.get("agency_comments")),
        1,
    )
    wordpress_jobs_series = [
        {
            "label": "Open listings",
            "color": COLORS["wordpress"],
            "points": point_series(wordpress_jobs_snapshots, "snapshot_date", "total_jobs", "2016-01-01"),
        },
        {
            "label": "Development",
            "color": COLORS["core"],
            "points": point_series(wordpress_jobs_snapshots, "snapshot_date", "development_jobs", "2016-01-01"),
        },
        {
            "label": "Project/freelance-style",
            "color": COLORS["orange"],
            "points": point_series(wordpress_jobs_snapshots, "snapshot_date", "project_jobs", "2016-01-01"),
        },
        {
            "label": "Support",
            "color": COLORS["green"],
            "points": point_series(wordpress_jobs_snapshots, "snapshot_date", "support_jobs", "2016-01-01"),
        },
    ]
    latest_jobs_snapshot = max(wordpress_jobs_snapshots, key=lambda row: row.get("snapshot_date", ""), default={})
    jobs_archive_snapshots = [row for row in wordpress_jobs_snapshots if row.get("source_type") == "wayback_archive"]
    jobs_snapshot_dates = sorted(row.get("snapshot_date", "") for row in wordpress_jobs_snapshots if row.get("snapshot_date"))
    jobs_range_label = (
        f"{jobs_snapshot_dates[0]} to {jobs_snapshot_dates[-1]}"
        if jobs_snapshot_dates
        else "not fetched"
    )
    latest_jobs_categories = sorted(
        [row for row in wordpress_jobs_categories if row.get("snapshot_date") == latest_jobs_snapshot.get("snapshot_date")],
        key=lambda row: num(row.get("open_jobs")),
        reverse=True,
    )
    max_latest_jobs_category = max([num(row.get("open_jobs")) for row in latest_jobs_categories] or [1])
    latest_jobs_total = num(latest_jobs_snapshot.get("total_jobs"))
    latest_project_jobs = num(latest_jobs_snapshot.get("project_jobs"))
    latest_development_jobs = num(latest_jobs_snapshot.get("development_jobs"))
    latest_jobs_project_share = latest_project_jobs / latest_jobs_total * 100 if latest_jobs_total else 0
    latest_jobs_development_share = latest_development_jobs / latest_jobs_total * 100 if latest_jobs_total else 0
    attention_rows = sorted(attention_demand_summary, key=lambda row: str(row.get("label", "")))
    attention_change_max = max([abs(float(row.get("change_pct") or 0)) for row in attention_rows] or [1])

    def attention_value(row, field):
        value = float(row.get(field) or 0)
        if "per 100" in str(row.get("unit", "")):
            return f"{value:.2f}"
        return compact(value)

    def attention_tone(row):
        direction = str(row.get("direction") or "")
        if direction == "lower":
            return "watch", COLORS["red"], "Lower"
        if direction == "higher":
            return "good", COLORS["green"], "Higher"
        if direction == "flat":
            return "soft", COLORS["core"], "Flat"
        return "soft", COLORS["neutral"], "No baseline"

    attention_stat_cards = []
    attention_change_bars = []
    for row in attention_rows:
        tone, color, direction_label = attention_tone(row)
        unit = str(row.get("unit") or "")
        note = f"{attention_value(row, 'latest_value')} vs {attention_value(row, 'baseline_value')} {unit}"
        attention_stat_cards.append(stat_card(str(row.get("label", "")), direction_label, note, tone))
        attention_change_bars.append(
            horizontal_count_metric(
                f"{direction_label}: {row.get('label', '')}",
                abs(float(row.get("change_pct") or 0)),
                max(1, attention_change_max),
                color,
                "%",
            )
        )
    enterprise_recent_cases = sum(1 for row in enterprise_vip_cases if str(row.get("date", "")) >= "2024-01-01")
    enterprise_industry_counts = Counter()
    enterprise_use_case_counts = Counter()
    for row in enterprise_vip_cases:
        for industry in str(row.get("industries") or "").split(" | "):
            if industry:
                enterprise_industry_counts[industry] += 1
        for use_case in str(row.get("use_cases") or "").split(" | "):
            if use_case:
                enterprise_use_case_counts[use_case] += 1
    top_enterprise_industries = enterprise_industry_counts.most_common(6)
    top_enterprise_use_cases = enterprise_use_case_counts.most_common(6)
    max_enterprise_industry_count = max([count for _name, count in top_enterprise_industries] or [1])
    max_enterprise_use_case_count = max([count for _name, count in top_enterprise_use_cases] or [1])
    latest_enterprise_cases = sorted(enterprise_vip_cases, key=lambda row: str(row.get("date", "")), reverse=True)[:5]

    plugin_count = num(directory.get("plugin_directory_plugins", {}).get("value"))
    theme_count = num(directory.get("theme_directory_themes", {}).get("value"))
    directory_activity_snapshot = directory_activity[0] if directory_activity else {}
    plugins_added_complete = num(directory_activity_snapshot.get("plugins_added_complete_90d")) == 1
    plugins_updated_complete = num(directory_activity_snapshot.get("plugins_updated_complete_90d")) == 1
    plugins_added_90 = num(directory_activity_snapshot.get("plugins_added_90d"))
    plugins_updated_90 = num(directory_activity_snapshot.get("plugins_updated_90d"))
    plugins_added_30 = num(directory_activity_snapshot.get("plugins_added_30d"))
    plugins_updated_30 = num(directory_activity_snapshot.get("plugins_updated_30d"))
    plugins_added_90_label = f"{compact(plugins_added_90)}" if plugins_added_complete else f">= {compact(plugins_added_90)}"
    plugins_updated_90_label = f"{compact(plugins_updated_90)}" if plugins_updated_complete else f">= {compact(plugins_updated_90)}"
    plugin_activity_max = max(plugins_added_90, plugins_updated_90, 1)
    popular_plugin_sample = max(1, num(directory_activity_snapshot.get("popular_plugin_sample_size")))
    popular_plugin_stale = num(directory_activity_snapshot.get("popular_plugin_stale_2y"))
    plugin_maintenance = plugin_maintenance_summary[0] if plugin_maintenance_summary else {}
    stale_plugin_sample_size = max(1, num(plugin_maintenance.get("sample_size")) or popular_plugin_sample)
    stale_plugin_count = num(plugin_maintenance.get("stale_2y_count")) or popular_plugin_stale
    stale_plugin_install_share = float(plugin_maintenance.get("stale_2y_active_install_share_pct") or 0)
    stale_plugin_sample_share = float(plugin_maintenance.get("stale_2y_sample_share_pct") or 0)
    stale_plugin_median_age = float(plugin_maintenance.get("median_days_since_update") or 0)
    stale_plugin_p90_age = float(plugin_maintenance.get("p90_days_since_update") or 0)
    top_stale_popular_plugins = sorted(
        plugin_stale_popular_sample,
        key=lambda row: num(row.get("active_installs")),
        reverse=True,
    )[:8]
    max_stale_plugin_installs = max([num(row.get("active_installs")) for row in top_stale_popular_plugins] or [1])
    top_major_plugins = sorted(
        major_plugin_rows,
        key=lambda row: num(row.get("active_installs")),
        reverse=True,
    )
    max_major_plugin_installs = max([num(row.get("active_installs")) for row in top_major_plugins] or [1])
    total_major_plugin_installs = sum(num(row.get("active_installs")) for row in major_plugin_rows)
    recently_updated_major_plugins = 0
    for row in major_plugin_rows:
        updated_at = parse_iso(row.get("last_updated_date"))
        if updated_at and updated_at >= END - dt.timedelta(days=90):
            recently_updated_major_plugins += 1
    major_plugin_support_rows = []
    for row in major_plugin_rows:
        support_threads = num(row.get("support_threads"))
        support_resolved = num(row.get("support_threads_resolved"))
        support_unresolved = max(0, support_threads - support_resolved)
        enriched = dict(row)
        enriched["support_unresolved"] = support_unresolved
        enriched["support_resolved_pct"] = support_resolved / support_threads * 100 if support_threads else 0
        major_plugin_support_rows.append(enriched)
    top_support_plugins = sorted(
        [row for row in major_plugin_support_rows if num(row.get("support_threads")) > 0],
        key=lambda row: num(row.get("support_threads")),
        reverse=True,
    )[:8]
    top_unresolved_plugins = sorted(
        [row for row in major_plugin_support_rows if num(row.get("support_unresolved")) > 0],
        key=lambda row: num(row.get("support_unresolved")),
        reverse=True,
    )[:8]
    max_major_plugin_support_threads = max([num(row.get("support_threads")) for row in top_support_plugins] or [1])
    max_major_plugin_unresolved = max([num(row.get("support_unresolved")) for row in top_unresolved_plugins] or [1])
    total_major_plugin_support_threads = sum(num(row.get("support_threads")) for row in major_plugin_support_rows)
    total_major_plugin_support_resolved = sum(num(row.get("support_threads_resolved")) for row in major_plugin_support_rows)
    total_major_plugin_support_unresolved = max(0, total_major_plugin_support_threads - total_major_plugin_support_resolved)
    total_major_plugin_support_resolved_pct = (
        total_major_plugin_support_resolved / total_major_plugin_support_threads * 100
        if total_major_plugin_support_threads
        else 0
    )
    plugin_name_by_slug = dict(MAJOR_PLUGIN_DISPLAY_NAMES)
    plugin_name_by_slug.update({
        str(row.get("slug") or ""): str(row.get("name") or row.get("slug") or "")
        for row in major_plugin_rows
        if row.get("slug")
    })
    for slug, label in MAJOR_PLUGIN_DISPLAY_NAMES.items():
        plugin_name_by_slug[slug] = label
    for row in major_plugin_download_q:
        if row.get("slug") and row.get("plugin_name"):
            plugin_name_by_slug.setdefault(str(row.get("slug")), str(row.get("plugin_name")))
    plugin_download_colors = [COLORS["core"], COLORS["purple"], COLORS["green"], COLORS["orange"], COLORS["neutral"]]
    install_history_slugs = [
        str(row.get("slug"))
        for row in top_major_plugins
        if row.get("slug") and any(hist.get("slug") == row.get("slug") for hist in major_plugin_install_history)
    ][:5]
    major_plugin_install_history_series = [
        {
            "label": plugin_name_by_slug.get(slug, slug),
            "color": plugin_download_colors[index % len(plugin_download_colors)],
            "points": sorted(
                (row.get("snapshot_date"), num(row.get("active_installs")))
                for row in major_plugin_install_history
                if row.get("slug") == slug and row.get("snapshot_date", "") >= "2018-01-01" and num(row.get("active_installs")) > 0
            ),
        }
        for index, slug in enumerate(install_history_slugs)
    ]
    install_history_archive_rows = [
        row for row in major_plugin_install_history if row.get("source_type") == "wayback_archive"
    ]
    install_history_latest_rows = [
        row for row in major_plugin_install_history if row.get("source_type") == "current_api"
    ]
    install_history_plugin_count = len({row.get("slug") for row in major_plugin_install_history if row.get("slug")})
    install_history_year_count = len({row.get("year") for row in install_history_archive_rows if row.get("year")})
    install_history_years = sorted({row.get("year") for row in install_history_archive_rows if row.get("year")})
    install_history_year_range = (
        f"{install_history_years[0]} to {install_history_years[-1]}"
        if install_history_years
        else "not fetched"
    )
    plugin_download_totals = Counter()
    for row in major_plugin_download_q:
        plugin_download_totals[str(row.get("slug") or "")] += num(row.get("downloads"))
    top_download_slugs = [slug for slug, _downloads in plugin_download_totals.most_common(5) if slug]
    major_plugin_download_series = [
        {
            "label": plugin_name_by_slug.get(slug, slug),
            "color": plugin_download_colors[index % len(plugin_download_colors)],
            "points": point_series(
                [row for row in major_plugin_download_q if row.get("slug") == slug],
                "quarter",
                "downloads",
            ),
        }
        for index, slug in enumerate(top_download_slugs)
    ]
    latest_plugin_download_quarter = max(
        [row.get("quarter", "") for row in major_plugin_download_q if row.get("quarter")],
        default="",
    )
    latest_plugin_download_rows = [
        row for row in major_plugin_download_q if row.get("quarter") == latest_plugin_download_quarter
    ]
    latest_plugin_download_total = sum(num(row.get("downloads")) for row in latest_plugin_download_rows)
    latest_plugin_download_days = max([num(row.get("days_covered")) for row in latest_plugin_download_rows] or [0])
    major_plugin_download_plugin_count = len({row.get("slug") for row in major_plugin_download_daily if row.get("slug")})
    top_popular_themes = sorted(
        [row for row in theme_activity_rows if row.get("browse") == "popular"],
        key=lambda row: num(row.get("num_ratings")),
        reverse=True,
    )[:8]
    max_popular_theme_ratings = max([num(row.get("num_ratings")) for row in top_popular_themes] or [1])

    adoption_detail = "Still dominant"
    if usage_delta is not None and cms_delta is not None:
        adoption_detail = f"W3Techs has WordPress at {pct(wp_usage_latest['value'])} of all sites and {pct(wp_cms_latest['value'])} of CMS sites, down {abs(usage_delta):.1f} and {abs(cms_delta):.1f} points since Jan 2025."

    source_rows = source_status_rows(fetched)
    source_status_counts = Counter(status for _name, status, _note in source_rows)
    local_source_file_count = sum(1 for key, path in SOURCE_FILES.items() if path.exists() and data.get(key) is not None)
    local_source_row_count = sum(
        len(data.get(key, []))
        for key, path in SOURCE_FILES.items()
        if path.exists() and data.get(key) is not None
    )
    fetched_nonempty_tables = [
        (name, rows)
        for name, rows in fetched.items()
        if isinstance(rows, list) and rows
    ]
    fetched_row_count = sum(len(rows) for _name, rows in fetched_nonempty_tables)
    source_attention_rows = [
        (name, status, note)
        for name, status, note in source_rows
        if status != "covered"
    ][:5]

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
.lane-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin:18px 0 24px; }}
.lane-card {{ border:1px solid var(--line); border-radius:8px; padding:16px; background:#fff; }}
.lane-card h3 {{ display:flex; align-items:center; gap:8px; margin-bottom:10px; }}
.lane-dot {{ width:11px; height:11px; border-radius:50%; display:inline-block; background:var(--blue); flex:0 0 auto; }}
.lane-card.ticket .lane-dot {{ background:var(--blue); }}
.lane-card.ecosystem .lane-dot {{ background:var(--green); }}
.lane-card.market .lane-dot {{ background:var(--orange); }}
.lane-card p {{ color:var(--muted); margin-bottom:10px; }}
.lane-list {{ display:grid; gap:7px; margin:0; padding:0; list-style:none; color:#334155; font-size:14px; }}
.lane-list li {{ display:flex; gap:8px; }}
.lane-list li::before {{ content:""; width:6px; height:6px; border-radius:50%; background:#b8c2d1; margin-top:.65em; flex:0 0 auto; }}
.answer-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin:24px 0 26px; }}
.question-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; margin:18px 0 24px; }}
.question-card {{ border:1px solid var(--line); border-left:5px solid var(--blue); border-radius:8px; padding:14px 15px; background:#fff; min-height:148px; }}
.question-card strong {{ display:block; font-size:22px; line-height:1.15; margin:5px 0 7px; }}
.question-card p {{ color:var(--muted); margin:0; }}
.question-card .tag {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.07em; font-weight:800; }}
.question-card .source {{ display:block; margin-top:11px; color:#475569; font-size:12px; font-weight:800; }}
.question-card.good {{ border-left-color:var(--green); }}
.question-card.watch {{ border-left-color:var(--orange); }}
.question-card.soft {{ border-left-color:var(--blue); }}
.question-card.slower {{ border-left-color:var(--red); }}
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
.decision-stats {{ grid-template-columns:repeat(5,minmax(0,1fr)); }}
.stat {{ border:1px solid var(--line); border-radius:8px; padding:14px; background:var(--soft); }}
.stat-label {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; font-weight:700; }}
.stat-value {{ font-size:28px; font-weight:800; margin:4px 0; }}
.stat-note {{ color:var(--muted); font-size:13px; }}
.card {{ border:1px solid var(--line); border-radius:8px; padding:16px; background:#fff; }}
.card .stats {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
.small-note {{ color:var(--muted); font-size:13px; margin-top:2px; }}
.chart {{ width:100%; height:auto; display:block; border:1px solid var(--line); border-radius:8px; background:#fff; margin:14px 0; }}
.chart-title {{ font-size:20px; font-weight:800; fill:var(--ink); }}
.chart-note {{ font-size:13px; fill:var(--muted); }}
.axis, .legend, .end-label {{ font-size:12px; fill:var(--muted); }}
.end-label {{ font-weight:800; }}
.grid {{ stroke:#e8edf4; stroke-width:1; }}
.axis-line {{ stroke:#b8c2d1; stroke-width:1; }}
.hmetric {{ margin:11px 0; }}
.hmetric-top {{ display:flex; justify-content:space-between; gap:12px; font-size:13px; }}
.hmetric-top span {{ color:var(--muted); min-width:0; padding-right:8px; }}
.hmetric-top strong {{ flex:0 0 auto; text-align:right; white-space:nowrap; }}
.bar {{ height:9px; border-radius:999px; background:#eef2f7; overflow:hidden; margin-top:5px; }}
.bar span {{ display:block; height:100%; border-radius:999px; }}
.callout {{ border-left:5px solid var(--blue); background:#f7fbff; padding:14px 16px; border-radius:8px; color:#334155; }}
.status-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }}
.status {{ border:1px solid var(--line); border-radius:8px; padding:13px; background:#fff; }}
.status b {{ display:block; }}
.status span {{ color:var(--muted); font-size:13px; }}
.pill {{ display:inline-block; border-radius:999px; padding:2px 8px; font-size:12px; font-weight:800; margin-bottom:7px; }}
.covered .pill {{ background:#dcfce7; color:#166534; }}
.partial .pill {{ background:#fef3c7; color:#92400e; }}
.missing .pill {{ background:#fee2e2; color:#991b1b; }}
.readout-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin-top:14px; }}
.readout-card {{ border:1px solid var(--line); border-radius:8px; padding:16px; background:#fff; }}
.readout-card strong {{ display:block; font-size:24px; line-height:1.15; margin-bottom:8px; }}
.readout-card p {{ color:var(--muted); }}
.evidence-strength-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:14px 0 16px; }}
.evidence-strength-card {{ border:1px solid var(--line); border-left:5px solid var(--blue); border-radius:8px; padding:14px; background:#fff; min-height:142px; }}
.evidence-strength-card span {{ display:block; color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; font-weight:800; margin-bottom:4px; }}
.evidence-strength-card strong {{ display:block; font-size:18px; line-height:1.2; margin-bottom:7px; }}
.evidence-strength-card p {{ color:var(--muted); margin:0; font-size:14px; }}
.evidence-strength-card.good {{ border-left-color:var(--green); }}
.evidence-strength-card.soft {{ border-left-color:var(--blue); }}
.evidence-strength-card.watch {{ border-left-color:var(--orange); }}
.scorecard-verdict {{ border:1px solid var(--line); border-left:6px solid var(--green); border-radius:8px; padding:16px; background:#fff; margin:16px 0 12px; }}
.scorecard-verdict strong {{ display:block; font-size:22px; line-height:1.2; margin-bottom:6px; }}
.scorecard-verdict p {{ color:var(--muted); margin:0; }}
.score-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }}
.score-card {{ border:1px solid var(--line); border-top:5px solid var(--blue); border-radius:8px; padding:14px; background:#fff; min-height:142px; }}
.score-card .score-chip {{ display:inline-block; border-radius:999px; padding:3px 8px; font-size:12px; font-weight:800; margin-bottom:9px; background:#dbeafe; color:#1e40af; }}
.score-card b {{ display:block; font-size:13px; color:var(--muted); margin-bottom:3px; }}
.score-card strong {{ display:block; font-size:24px; line-height:1.1; margin-bottom:8px; }}
.score-card p {{ color:var(--muted); margin:0; font-size:14px; }}
.score-card.good {{ border-top-color:var(--green); }}
.score-card.good .score-chip {{ background:#dcfce7; color:#166534; }}
.score-card.slower {{ border-top-color:var(--red); }}
.score-card.slower .score-chip {{ background:#fee2e2; color:#991b1b; }}
.score-card.watch {{ border-top-color:var(--orange); }}
.score-card.watch .score-chip {{ background:#fef3c7; color:#92400e; }}
.goal-map {{ display:grid; gap:10px; margin-top:16px; }}
.goal-row {{ display:grid; grid-template-columns:minmax(160px,1.1fr) minmax(135px,.7fr) minmax(260px,2fr); gap:14px; align-items:start; border:1px solid var(--line); border-left:6px solid var(--blue); border-radius:8px; padding:13px 14px; background:#fff; }}
.goal-row strong {{ display:block; line-height:1.2; }}
.goal-row p {{ margin:3px 0 0; color:var(--muted); font-size:13px; line-height:1.35; }}
.goal-status {{ display:inline-flex; align-items:center; width:max-content; border-radius:999px; padding:4px 9px; font-size:12px; font-weight:800; }}
.goal-row.good {{ border-left-color:var(--green); }}
.goal-row.good .goal-status {{ background:#dcfce7; color:#166534; }}
.goal-row.soft {{ border-left-color:var(--blue); }}
.goal-row.soft .goal-status {{ background:#dbeafe; color:#1e40af; }}
.goal-row.watch {{ border-left-color:var(--orange); }}
.goal-row.watch .goal-status {{ background:#fef3c7; color:#92400e; }}
.goal-row.partial {{ border-left-color:#ef4444; }}
.goal-row.partial .goal-status {{ background:#fee2e2; color:#991b1b; }}
.link-list {{ display:grid; gap:8px; margin-top:12px; }}
.link-list a {{ line-height:1.25; }}
.link-list code {{ display:block; white-space:normal; overflow-wrap:anywhere; line-height:1.35; }}
.watchlist-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; margin-top:12px; }}
.footer {{ color:var(--muted); font-size:13px; margin-top:32px; border-top:1px solid var(--line); padding-top:18px; }}
@media (max-width:900px) {{
  h1 {{ font-size:34px; }}
  .lane-grid, .answer-grid, .grid-2, .stats, .decision-stats, .status-grid, .readout-grid, .evidence-strength-grid, .score-grid {{ grid-template-columns:1fr; }}
  .goal-row {{ grid-template-columns:1fr; }}
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
    <a href="#decision-questions">Decision Questions</a>
    <a href="#scorecard">Scorecard</a>
    <a href="#goal-map">Coverage Map</a>
    <a href="#coverage">Source Coverage</a>
    <a href="data_inventory.html">Data Inventory</a>
    <a href="#companion-docs">Report Docs</a>
    <a href="#readout">Decision Readout</a>
  </nav>

  <section class="lane-grid" aria-label="Evidence lanes">
    <article class="lane-card ticket">
      <h3><span class="lane-dot"></span>Ticket-derived signals</h3>
      <p>Core Trac, Gutenberg GitHub issues, and wordpress-develop PRs explain project participation and maintenance load. See the <a href="project_load.html">project load view</a> for the compact workload readout.</p>
      <ul class="lane-list">
        <li>Best for new/closed flow, backlog, response time, bug/feature mix, and contributor concentration.</li>
        <li>Not enough by itself to say whether people are choosing WordPress for new sites.</li>
      </ul>
    </article>
    <article class="lane-card ecosystem">
      <h3><span class="lane-dot"></span>Ecosystem signals</h3>
      <p>WordPress.org APIs, Make/Core, WordCamp, Events, Translate, Five for the Future, and support snapshots show community activity outside trackers. See the <a href="ecosystem_activity.html">ecosystem activity view</a> for the compact digest and the <a href="support_load.html">support load view</a> for the current support-queue readout.</p>
      <ul class="lane-list">
        <li>Best for release credits, committers, events, translation, support load, plugin/theme activity, and pledged work.</li>
        <li>Mostly snapshots or release-level series, so they complement rather than replace ticket trends.</li>
      </ul>
    </article>
    <article class="lane-card market">
      <h3><span class="lane-dot"></span>Adoption and demand signals</h3>
      <p>W3Techs, HTTP Archive, BuiltWith, Stack Overflow, Wikimedia, Hacker News, jobs, and plugin history show market position and demand proxies. See the <a href="market_position.html">market position view</a> for the compact decision readout, the <a href="new_site_choice.html">new-site choice view</a> for current pipeline and crawl proxies, the <a href="search_interest.html">search interest view</a> for public-attention proxies, the <a href="developer_interest.html">developer interest view</a> for help-seeking and PR activity, and the <a href="job_demand.html">job demand view</a> for hiring proxies.</p>
      <ul class="lane-list">
        <li>Best for installed share, CMS share, traffic-tier presence, current newly found-site proxy, and demand direction.</li>
        <li>Search and broad job-market demand remain partial; current proxies are labeled as such.</li>
      </ul>
    </article>
  </section>

  <section id="scorecard" class="section">
    <h2>Relevance Scorecard</h2>
    <div class="scorecard-verdict">
      <strong>Overall: still in a good place, with softer momentum.</strong>
      <p>WordPress remains the default CMS on installed-share and ecosystem evidence. The softer parts are new-site momentum, first-time tracker participation, and demand signals that currently rely on public proxies.</p>
    </div>
    <div class="score-grid" aria-label="WordPress relevance scorecard">
      <article class="score-card good">
        <span class="score-chip">Strong</span>
        <b>Installed reach</b>
        <strong>{pct(wp_usage_latest['value']) if wp_usage_latest else 'n/a'} / {pct(wp_cms_latest['value']) if wp_cms_latest else 'n/a'}</strong>
        <p>All-site share and CMS share still make WordPress the default CMS.</p>
      </article>
      <article class="score-card watch">
        <span class="score-chip">Softer</span>
        <b>Recent share direction</b>
        <strong>{f"{usage_delta:+.1f} pts" if usage_delta is not None else "n/a"}</strong>
        <p>All-site W3Techs change since Jan 2025; CMS share also moved {f"{cms_delta:+.1f} pts" if cms_delta is not None else "n/a"}.</p>
      </article>
      <article class="score-card watch">
        <span class="score-chip">Current proxy</span>
        <b>New-site choice</b>
        <strong>{pct(builtwith_wp_90_share)}</strong>
        <p>Share of the tracked 90-day BuiltWith pipeline across WordPress, Shopify, Wix, and Webflow.</p>
      </article>
      <article class="score-card slower">
        <span class="score-chip">Slower</span>
        <b>New community entry</b>
        <strong>{pct(core_first_retention)} / {pct(gut_first_retention)}</strong>
        <p>Core and Gutenberg first-time reporter retention versus the 2021-2023 quarterly average.</p>
      </article>
      <article class="score-card good">
        <span class="score-chip">Mostly keeping up</span>
        <b>Project throughput</b>
        <strong>{pct(core_closure_ratio)} / {pct(gut_closure_ratio)}</strong>
        <p>Core and Gutenberg closure/new ratios since 2024.</p>
      </article>
      <article class="score-card good">
        <span class="score-chip">Deep</span>
        <b>Ecosystem base</b>
        <strong>{compact(plugin_count)} / {compact(theme_count)}</strong>
        <p>Current WordPress.org plugin and theme directory counts, plus active releases, events, translations, and pledges elsewhere in the report.</p>
      </article>
    </div>
  </section>

  <section class="answer-grid">
    {signal_card("Adoption", "Dominant, softer recently", adoption_detail, "watch")}
    {signal_card("Participation", "Fewer new reporters", f"Core first-time reporters averaged {compact(core_first_prev)} per quarter in 2021-2023 and {compact(core_first_recent)} since 2024. Gutenberg moved from {compact(gut_first_prev)} to {compact(gut_first_recent)}.", "slower")}
    {signal_card("Project load", "Closer to balanced", f"Since 2024, Core closures slightly exceed new tickets on average. Gutenberg is close to flat, with the latest sampled quarter closing {compact(num(gut_latest.get('closed')))} against {compact(num(gut_latest.get('created')))} new issues.", "soft")}
    {signal_card("Code review", "PR flow is higher", f"wordpress-develop PR creation averaged {compact(pr_created_prev)} per quarter in 2021-2023 and {compact(pr_created_recent)} since 2024.", "good")}
  </section>

  <section id="decision-questions" class="section">
    <h2>Decision Questions</h2>
    <p class="callout">These are the plain-English answers the report is meant to support. Each card points to the kind of evidence behind the answer, so this can be used as a quick briefing before reading the charts.</p>
    <div class="question-grid" aria-label="Plain-English decision answers">
    <article class="question-card good">
      <span class="tag">Still widely chosen?</span>
      <strong>Yes.</strong>
      <p>Installed-share evidence has WordPress at {pct(wp_usage_latest['value']) if wp_usage_latest else 'n/a'} of all sites and {pct(wp_cms_latest['value']) if wp_cms_latest else 'n/a'} of CMS sites.</p>
      <span class="source">W3Techs + HTTP Archive</span>
    </article>
    <article class="question-card watch">
      <span class="tag">Adoption direction?</span>
      <strong>Flat-to-down recently.</strong>
      <p>{f"W3Techs is down {abs(usage_delta):.1f} all-site points and {abs(cms_delta):.1f} CMS-share points since Jan 2025." if usage_delta is not None and cms_delta is not None else "The latest installed-share trend is flatter than the historical climb."}</p>
      <span class="source">W3Techs yearly trend</span>
    </article>
    <article class="question-card slower">
      <span class="tag">Participation?</span>
      <strong>Fewer new reporters.</strong>
      <p>Core first-time reporter retention is {pct(core_first_retention)} of the 2021-2023 average; Gutenberg is {pct(gut_first_retention)}. PR creation is higher.</p>
      <span class="source">Core Trac + Gutenberg + PRs</span>
    </article>
    <article class="question-card soft">
      <span class="tag">Keeping up?</span>
      <strong>Mostly.</strong>
      <p>Since 2024, closure/new ratios are Core {pct(core_closure_ratio)} and Gutenberg {pct(gut_closure_ratio)}.</p>
      <span class="source">Quarterly ticket flow</span>
    </article>
    <article class="question-card watch">
      <span class="tag">Backlog age?</span>
      <strong>Aged.</strong>
      <p>Open stale share is Core {pct(core_stale_pct)} and Gutenberg {pct(gut_stale_pct)}; 2+ year open share is Core {pct(core_open_2y_share)} and Gutenberg {pct(gut_open_2y_share)}.</p>
      <span class="source">Current open backlog</span>
    </article>
    <article class="question-card soft">
      <span class="tag">Contributor spread?</span>
      <strong>Broad entry, concentrated work.</strong>
      <p>Since 2024, top-50 work share is Core {pct(conc_metric("Core Trac reporters", "since_2024", "top50_item_share_pct"))}, Gutenberg {pct(conc_metric("Gutenberg issue creators", "since_2024", "top50_item_share_pct"))}, and PRs {pct(conc_metric("wordpress-develop PR authors", "since_2024", "top50_item_share_pct"))}.</p>
      <span class="source">Contributor concentration</span>
    </article>
    <article class="question-card watch">
      <span class="tag">Builders gaining?</span>
      <strong>Some share, yes.</strong>
      <p>HTTP Archive tracked share has WordPress at {http_share_latest_wp_label}, {http_share_wp_delta_label} since {http_share_first_date or 'the first HTTP Archive month'}; WordPress still leads the current tracked BuiltWith 90-day pipeline at {pct(builtwith_wp_90_share)}.</p>
      <span class="source">HTTP Archive + BuiltWith proxy</span>
    </article>
    </div>
  </section>

  <section class="stats">
    {stat_card("Core open tickets", compact(num(core_latest.get("open_at_end"))), f"latest quarter {core_latest.get('label','')}", "soft")}
    {stat_card("Gutenberg open issues", compact(num(gut_latest.get("open_at_end"))), f"latest quarter {quarter_label(gut_latest.get('quarter',''))}", "soft")}
    {stat_card("Open Core stale share", pct(core_stale_pct), f"{compact(core_stale)} of {compact(core_open)} open tickets", "watch")}
    {stat_card("Open Gutenberg stale share", pct(gut_stale_pct), f"{compact(gut_stale)} of {compact(gut_open)} open issues", "watch")}
  </section>

  <section id="participation" class="section">
    <h2>Participation</h2>
    <p class="callout">The main participation change is not a collapse. It is fewer first-time and unique reporters in the trackers, while PR authorship is steadier and recent PR volume is higher. The companion <a href="contributor_depth.html">contributor depth view</a> breaks this down into drive-by, returning, regular, and sustained participation.</p>
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
    {svg_line_chart("Repeat participation by quarter", "People who had already appeared before in the same tracker or PR stream.", [
        {"label": "Core repeat reporters", "color": COLORS["core"], "points": core_repeat_reporter_points},
        {"label": "Gutenberg repeat creators", "color": COLORS["gutenberg"], "points": gut_repeat_creator_points},
        {"label": "PR repeat authors", "color": COLORS["prs"], "points": pr_repeat_author_points},
    ])}
    <div class="grid-2">
      <div>
        {svg_line_chart("Project-member share of GitHub work", "Quarterly split from GitHub author_association. Project-member means MEMBER/OWNER/COLLABORATOR; bots are excluded from the share.", [
            {"label": "Gutenberg issues", "color": COLORS["gutenberg"], "points": maintainer_points("Gutenberg issues", "project_member_share_pct")},
            {"label": "Core PRs", "color": COLORS["prs"], "points": maintainer_points("wordpress-develop PRs", "project_member_share_pct")},
        ], y_suffix="%")}
      </div>
      <div class="card">
        <h3>Project-member vs outside work</h3>
        <p>This is the closest available maintainer/non-maintainer split for GitHub-originated activity. It is based on the author's relationship to the repository at collection time, not on who reviewed or merged the work.</p>
        <div class="stats">
          {stat_card("Gutenberg member share", pct(num(maintainer_latest_by_source.get("Gutenberg issues", {}).get("project_member_share_pct"))), quarter_label(maintainer_latest_by_source.get("Gutenberg issues", {}).get("quarter", "")), "soft")}
          {stat_card("Gutenberg outside authors", compact(num(maintainer_latest_by_source.get("Gutenberg issues", {}).get("outside_authors"))), "latest quarter", "good")}
          {stat_card("Core PR member share", pct(num(maintainer_latest_by_source.get("wordpress-develop PRs", {}).get("project_member_share_pct"))), quarter_label(maintainer_latest_by_source.get("wordpress-develop PRs", {}).get("quarter", "")), "soft")}
          {stat_card("Core PR outside authors", compact(num(maintainer_latest_by_source.get("wordpress-develop PRs", {}).get("outside_authors"))), "latest quarter", "good")}
        </div>
        {horizontal_metric("Latest Gutenberg outside share", num(maintainer_latest_by_source.get("Gutenberg issues", {}).get("outside_share_pct")), 100, COLORS["community"])}
        {horizontal_metric("Latest Core PR outside share", num(maintainer_latest_by_source.get("wordpress-develop PRs", {}).get("outside_share_pct")), 100, COLORS["community"])}
      </div>
    </div>
    <div class="grid-2">
      <div>
        {svg_line_chart("Gutenberg issue origin", "GitHub exposes author association, so this can split member and community-created issues.", [
            {"label": "Member-created", "color": COLORS["member"], "points": member_points},
            {"label": "Community-created", "color": COLORS["community"], "points": community_points},
        ])}
      </div>
      <div class="card">
        <h3>Contributor concentration</h3>
        <p>Share of work since 2024 handled by the top 10, 25, and 50 people in each source.</p>
        {''.join(horizontal_metric(f"{short_label} top {rank}", conc_metric(source, "since_2024", f"top{rank}_item_share_pct"), 100, color) for source, short_label, color in depth_sources for rank in (10, 25, 50))}
      </div>
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>Drive-by participation</h3>
        <p>Share of contributors since 2024 who opened exactly one ticket, issue, or PR.</p>
        {''.join(horizontal_metric(f"{short_label} one-time contributors", depth_metric(source, "1 item", "contributor_share_pct"), 100, color) for source, short_label, color in depth_sources)}
      </div>
      <div class="card">
        <h3>Sustained participation</h3>
        <p>Share of work since 2024 coming from people with 20 or more tickets, issues, or PRs in that same window.</p>
        {''.join(horizontal_metric(f"{short_label} 20+ contributor work share", depth_metric(source, "20+ items", "item_share_pct"), 100, color) for source, short_label, color in depth_sources)}
      </div>
    </div>
    <div class="grid-2">
      {svg_line_chart("Make/Core publishing activity", "Posts and unique author IDs per quarter from make.wordpress.org/core.", [
          {"label": "Posts", "color": COLORS["core"], "points": core_make_posts},
          {"label": "Authors", "color": COLORS["community"], "points": core_make_authors},
      ])}
      {svg_line_chart("Make/Core discussion activity", "Comments, unique commenters, and posts receiving comments per quarter.", [
          {"label": "Comments", "color": COLORS["core"], "points": make_comment_points},
          {"label": "Commenters", "color": COLORS["community"], "points": make_commenter_points},
          {"label": "Posts discussed", "color": COLORS["prs"], "points": make_comment_post_points},
      ])}
    </div>
    <div class="grid-2">
      {svg_line_chart("WordCamp records by year", "WordCamp Central event records by start year. Recent future/scheduled records may be incomplete.", [
          {"label": "WordCamps", "color": COLORS["gutenberg"], "points": wordcamp_years},
      ])}
      <div class="card">
        <h3>Make/Core discussion readout</h3>
        <p>Comments show who is participating in Make/Core discussion, which is separate from who publishes posts.</p>
        <div class="stats">
          {stat_card("Comments fetched", compact(len(make_comments)), "Make/Core REST API", "good")}
          {stat_card("Latest quarter", compact(num(latest_make_comment_quarter.get("comments"))), latest_make_comment_quarter.get("label", ""), "soft")}
          {stat_card("Commenters", compact(num(latest_make_comment_quarter.get("unique_commenters"))), "latest quarter", "soft")}
          {stat_card("Posts discussed", compact(num(latest_make_comment_quarter.get("posts_commented_on"))), "latest quarter", "soft")}
        </div>
        {horizontal_metric("Top 10 commenters since 2024", make_comment_conc_recent["top10"], 100, COLORS["community"])}
        {horizontal_metric("Top 25 commenters since 2024", make_comment_conc_recent["top25"], 100, COLORS["core"])}
      </div>
    </div>
    <div class="grid-2">
      {svg_line_chart("WordCamp anticipated attendance by year", "Summed Number of Anticipated Attendees from WordCamp Central records. Current and future years are incomplete.", [
          {"label": "Anticipated attendees", "color": COLORS["community"], "points": wordcamp_attendance_points},
      ])}
      <div class="card">
        <h3>WordCamp attendance coverage</h3>
        <p>Attendance is not populated on every record. This uses the API's anticipated-attendee field when present.</p>
        <div class="stats">
          {stat_card("Latest full year", compact(num(latest_complete_wordcamp_year.get("anticipated_attendance"))), f"{latest_complete_wordcamp_year.get('label', '')} anticipated", "soft")}
          {stat_card("Events with estimate", compact(num(latest_complete_wordcamp_year.get("events_with_attendance_estimate"))), f"{compact(num(latest_complete_wordcamp_year.get('events')))} events in {latest_complete_wordcamp_year.get('label', '')}", "soft")}
          {stat_card("Latest record year", compact(num(latest_wordcamp_year.get("anticipated_attendance"))), f"{latest_wordcamp_year.get('label', '')} scheduled/recorded", "soft")}
          {stat_card("Coverage", pct(float(latest_complete_wordcamp_year.get("attendance_estimate_coverage_pct") or 0)), "latest full year", "soft")}
        </div>
        {horizontal_count_metric("Events in latest full year", num(latest_complete_wordcamp_year.get("events")), max_wordcamp_year_events, COLORS["gutenberg"], "")}
        {horizontal_count_metric("Events with attendee estimate", num(latest_complete_wordcamp_year.get("events_with_attendance_estimate")), max_wordcamp_year_events, COLORS["community"], "")}
        {horizontal_count_metric("Anticipated attendance", num(latest_complete_wordcamp_year.get("anticipated_attendance")), max_wordcamp_year_attendance, COLORS["orange"], "")}
      </div>
    </div>
    <div class="grid-2">
      {svg_line_chart("Make/Core dev notes by quarter", "Developer-note tagged Make/Core posts and unique author IDs per quarter.", [
          {"label": "Dev notes", "color": COLORS["purple"], "points": dev_note_quarter_points},
          {"label": "Authors", "color": COLORS["community"], "points": dev_note_author_points},
      ])}
      {svg_line_chart("Dev notes by release", "Developer-note tagged posts grouped by explicit release tag, plotted on release date when available.", [
          {"label": "Dev notes", "color": COLORS["purple"], "points": dev_note_release_points},
      ])}
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>Translate WordPress snapshot</h3>
        <p>Current translate.wordpress.org locale directory. Contributor counts are locale-team profile counts, not globally deduplicated people.</p>
        <div class="stats">
          {stat_card("Locales", compact(num(translation_snapshot.get("locale_count"))), "listed locale teams", "good")}
          {stat_card("Profile counts", compact(num(translation_snapshot.get("locale_contributor_profile_sum"))), "sum across locale teams", "good")}
          {stat_card("90%+ locales", compact(num(translation_snapshot.get("locales_90_plus"))), "locale directory completion", "good")}
          {stat_card("Core dev 90%+", compact(num(translation_snapshot.get("core_dev_90_plus"))), "WordPress dev project", "soft")}
        </div>
        {horizontal_count_metric("Locale directory 90%+", num(translation_snapshot.get("locales_90_plus")), translation_locale_count, COLORS["green"], " locales")}
        {horizontal_count_metric("Locale directory 50-89%", num(translation_snapshot.get("locales_50_to_89")), translation_locale_count, COLORS["orange"], " locales")}
        {horizontal_count_metric("Locale directory under 50%", num(translation_snapshot.get("locales_under_50")), translation_locale_count, COLORS["red"], " locales")}
      </div>
      <div class="card">
        <h3>Core dev translation status</h3>
        <p>Current WordPress Core development project translation status by locale.</p>
        {horizontal_count_metric("100% complete", num(translation_snapshot.get("core_dev_100")), translation_core_count, COLORS["green"], " locales")}
        {horizontal_count_metric("90%+ complete", num(translation_snapshot.get("core_dev_90_plus")), translation_core_count, COLORS["core"], " locales")}
        {horizontal_count_metric("50-89% complete", num(translation_snapshot.get("core_dev_50_to_89")), translation_core_count, COLORS["orange"], " locales")}
        {horizontal_count_metric("Under 50%", num(translation_snapshot.get("core_dev_under_50")), translation_core_count, COLORS["red"], " locales")}
        {stat_card("Waiting strings", compact(num(translation_snapshot.get("core_dev_waiting_strings"))), "all Core dev locales", "watch")}
      </div>
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>Largest locale teams</h3>
        <p>Top locale teams by listed profile count in the current Translate WordPress directory.</p>
        {''.join(horizontal_count_metric(str(row.get("locale", "")), num(row.get("contributors")), max_translation_contributors, COLORS["member"], " profiles") for row in top_translation_locales)}
      </div>
      <div class="card">
        <h3>Translation readout</h3>
        <p>Translation activity is broad and ongoing. The current snapshot shows many locale teams, but Core development coverage is uneven because every active development branch creates new strings.</p>
      </div>
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
      <div class="card">
        <h3>Support forum queue snapshot</h3>
        <p>Current public WordPress.org support views. This is a live queue snapshot, not a historical forum trend.</p>
        <div class="stats">
          {stat_card("Queue topics", compact(support_topic_count), f"{support_oldest[:10]} to {support_latest[:10]}", "soft")}
          {stat_card("Unresolved", compact(support_unresolved_count), "current unresolved view", "watch")}
          {stat_card("Resolved", compact(support_resolved_count), "current resolved view", "good")}
          {stat_card("No replies", compact(support_no_reply_count), "deduplicated zero-reply topics", "watch")}
          {stat_card("Resolved share", pct(support_resolved_share), "of deduplicated queue topics", "good")}
          {stat_card("No-reply share", pct(support_no_reply_share), "of deduplicated queue topics", "watch")}
          {stat_card("Views covered", compact(support_view_count), "all, unresolved, resolved, no replies", "soft")}
        </div>
        {horizontal_count_metric("Recent topics view", support_recent_count, support_queue_max, COLORS["core"], "")}
        {horizontal_count_metric("Unresolved queue", support_unresolved_count, support_queue_max, COLORS["orange"], "")}
        {horizontal_count_metric("Resolved queue", support_resolved_count, support_queue_max, COLORS["green"], "")}
        {horizontal_count_metric("No-reply topics", support_no_reply_count, support_queue_max, COLORS["red"], "")}
      </div>
      <div class="card">
        <h3>Where unanswered support sits</h3>
        <p>Deduplicated topics across the current public queue views, grouped by forum and sorted by unresolved topics.</p>
        {''.join(horizontal_count_metric(str(row.get("forum_name", "")), num(row.get("unresolved") or row.get("unresolved_topics")), max_support_unanswered_forum, COLORS["orange"], " unresolved") for row in top_support_unanswered_forums)}
      </div>
    </div>
    <div class="grid-2">
      {svg_line_chart("Support queue last-activity month", "Current public support queue snapshot, grouped by each topic's last activity month.", [
          {"label": "All queue topics", "color": COLORS["core"], "points": support_month_topic_points},
          {"label": "Unresolved", "color": COLORS["orange"], "points": support_month_unresolved_points},
          {"label": "Resolved", "color": COLORS["green"], "points": support_month_resolved_points},
          {"label": "No replies", "color": COLORS["red"], "points": support_month_no_reply_points},
      ])}
      <div class="card">
        <h3>Unresolved support age</h3>
        <p>How old the unresolved queue is, measured from each topic's last activity date at collection time.</p>
        <div class="stats">
          {stat_card("Unresolved share", pct(support_unresolved_share), "of deduplicated queue topics", "watch")}
          {stat_card("31+ days", compact(support_unresolved_31_plus), "unresolved topics", "watch")}
          {stat_card("91+ days", compact(support_unresolved_91_plus), "unresolved topics", "watch")}
          {stat_card("No replies", compact(support_no_reply_count), "current zero-reply topics", "watch")}
        </div>
        {''.join(horizontal_count_metric(f"{row.get('age_bucket', '')} unresolved", num(row.get("unresolved")), support_unresolved_age_max, COLORS["orange"] if num(row.get("unresolved")) else COLORS["neutral"], " topics") for row in support_age_ordered)}
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
        {stat_card("Latest dev-note release", latest_dev_note_release.get("version", "n/a"), "explicit Make/Core dev-notes tag", "soft")}
        {stat_card("Dev notes", compact(num(latest_dev_note_release.get("dev_notes"))), "for that release tag", "good")}
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
      {svg_line_chart("First response by quarter", "Median hours. Core uses first non-reporter Trac activity; Gutenberg uses first non-author and maintainer comments.", [
          {"label": "Core non-reporter activity", "color": COLORS["core"], "points": core_first_response_points},
          {"label": "Gutenberg non-author comment", "color": COLORS["gutenberg"], "points": gut_first_response_points},
          {"label": "Gutenberg maintainer comment", "color": COLORS["prs"], "points": gut_maintainer_response_points},
      ], y_suffix="h")}
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>Closure-age readout</h3>
        <p>Latest closure quarter: median is the typical closed ticket or issue; p90 shows older work that was still being closed.</p>
        <div class="stats">
          {stat_card("Core median", f"{compact(as_float(latest_core_closure_age.get('median_days_to_close')))} days", latest_core_closure_age.get("label", "latest quarter"), "soft")}
          {stat_card("Core p90", f"{compact(as_float(latest_core_closure_age.get('p90_days_to_close')))} days", f"{compact(num(latest_core_closure_age.get('closed_count')))} closed", "watch")}
          {stat_card("Gutenberg median", f"{compact(as_float(latest_gut_closure_age.get('median_days_to_close')))} days", latest_gut_closure_age.get("label", "latest quarter"), "soft")}
          {stat_card("Gutenberg p90", f"{compact(as_float(latest_gut_closure_age.get('p90_days_to_close')))} days", f"{compact(num(latest_gut_closure_age.get('closed_count')))} closed", "watch")}
        </div>
      </div>
      <div class="card">
        <h3>Recent closure speed</h3>
        <p>Median of quarterly median days-to-close since 2024, which smooths out single cleanup pulses.</p>
        {horizontal_count_metric("Core recent median", core_recent_closure_median or 0, max_latest_closure_days, COLORS["core"], " days")}
        {horizontal_count_metric("Gutenberg recent median", gut_recent_closure_median or 0, max_latest_closure_days, COLORS["gutenberg"], " days")}
        {horizontal_count_metric("Core latest p90", as_float(latest_core_closure_age.get("p90_days_to_close")), max_latest_closure_days, COLORS["orange"], " days")}
        {horizontal_count_metric("Gutenberg latest p90", as_float(latest_gut_closure_age.get("p90_days_to_close")), max_latest_closure_days, COLORS["red"], " days")}
      </div>
    </div>
    <div class="grid-2">
      {svg_line_chart("Reopen pressure by quarter", "Reopened events per 100 closed tickets or issues. Lower means fewer items coming back after closure.", [
          {"label": "Core", "color": COLORS["core"], "points": core_reopen_rate_points},
          {"label": "Gutenberg", "color": COLORS["red"], "points": gut_reopen_rate_points},
      ], y_suffix="/100")}
      <div class="card">
        <h3>Response timeline coverage</h3>
        <p>Core uses Trac RSS entries for tickets created since 2021. Gutenberg uses GitHub GraphQL comments and reopen timelines for the existing issue inventory.</p>
        {horizontal_count_metric("Core RSS ticket rows", len(data["core_response_metrics"]), len([row for row in core_tickets if row.get("created_at", "") >= "2021-01-01"]) or 1, COLORS["core"], "")}
        {horizontal_count_metric("Issue timeline rows", len(data["gutenberg_timeline_metrics"]), len(gut_jsonl) or 1, COLORS["gutenberg"], "")}
        {horizontal_count_metric("Latest Core first response", float(latest_core_response.get("median_first_non_reporter_activity_hours") or 0), max_gut_response_hours, COLORS["core"], "h")}
        {horizontal_count_metric("Latest median first response", float(latest_gut_timeline.get("median_first_non_author_response_hours") or 0), max_gut_response_hours, COLORS["gutenberg"], "h")}
        {horizontal_count_metric("Latest Gutenberg maintainer response", float(latest_gut_timeline.get("median_first_maintainer_response_hours") or 0), max_gut_response_hours, COLORS["prs"], "h")}
      </div>
    </div>
    <div class="card">
      <h3>Backlog and reopen readout</h3>
      <p>These are direct tracker-derived signals, not adoption signals.</p>
      <div class="grid-2">
        <div>
          {horizontal_metric("Core open stale share", core_stale_pct, 100, COLORS["orange"])}
          {horizontal_metric("Gutenberg open stale share", gut_stale_pct, 100, COLORS["orange"])}
          {horizontal_metric("Core tickets ever reopened", reopened_pct, 100, COLORS["red"])}
        </div>
        <div>
          {horizontal_count_metric("Latest Core reopen events", num(latest_core_reopen.get("reopened_events")), max([num(row.get("reopened_events")) for row in core_reopen_q] or [1]), COLORS["red"], "")}
          {horizontal_count_metric("Latest Core reopens per 100 closes", float(latest_core_reopen.get("reopened_events_per_100_closed") or 0), max_reopen_rate, COLORS["core"], " /100 closes")}
          {horizontal_count_metric("Latest Gutenberg reopens per 100 closes", float(latest_gut_timeline.get("reopened_events_per_100_closed") or 0), max_reopen_rate, COLORS["red"], " /100 closes")}
        </div>
      </div>
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>Core open backlog age</h3>
        <p>Currently open Trac tickets grouped by time since last modification.</p>
        <div class="stats">
          {stat_card("Open tickets", compact(core_open), "current Core backlog", "soft")}
          {stat_card("2+ years", compact(core_open_2y_plus), f"{pct(core_open_2y_share)} of open tickets", "watch")}
        </div>
        {''.join(horizontal_count_metric(str(row.get('age_bucket', '')), num(row.get("open_count")), open_age_max, COLORS["orange"] if row.get("age_bucket") in {"2-5 years", "5+ years"} else COLORS["core"], " open") for row in core_open_age_rows)}
      </div>
      <div class="card">
        <h3>Gutenberg open backlog age</h3>
        <p>Currently open GitHub issues grouped by time since last update.</p>
        <div class="stats">
          {stat_card("Open issues", compact(gut_open), "current Gutenberg backlog", "soft")}
          {stat_card("2+ years", compact(gut_open_2y_plus), f"{pct(gut_open_2y_share)} of open issues", "watch")}
        </div>
        {''.join(horizontal_count_metric(str(row.get('age_bucket', '')), num(row.get("open_count")), open_age_max, COLORS["orange"] if row.get("age_bucket") in {"2-5 years", "5+ years"} else COLORS["gutenberg"], " open") for row in gut_open_age_rows)}
      </div>
    </div>
    {svg_line_chart("Large ticket categories by quarter", "Combined Core plus Gutenberg classified issue/ticket categories since 2021.", cat_series)}
    <div class="grid-2">
      {svg_line_chart("Core bugs, feature requests, and all tickets", "Quarterly Trac tickets by classified category. All tickets are direct created-ticket counts.", core_category_series)}
      {svg_line_chart("Gutenberg bugs, feature requests, and all issues", "Quarterly GitHub issues by classified category. All issues are direct created-issue counts.", gut_category_series)}
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>Core open backlog by category</h3>
        <p>Open classified Trac tickets by category. Bars show open counts; percentages are category share of the open Core backlog.</p>
        <div class="stats">
          {stat_card("Open classified", compact(core_open_total), "Core Trac tickets", "soft")}
          {stat_card("Bug share", pct(core_bug_open_share), "of open Core backlog", "watch")}
        </div>
        {''.join(horizontal_count_metric(f"{category_label(row.get('category'))} ({pct(float(row.get('open_category_share_pct') or 0))})", num(row.get("open_count")), category_open_max, category_colors.get(row.get("category"), COLORS["neutral"]), " open") for row in core_open_category_rows[:6])}
      </div>
      <div class="card">
        <h3>Gutenberg open backlog by category</h3>
        <p>Open classified GitHub issues by category. Bars show open counts; percentages are category share of the open Gutenberg backlog.</p>
        <div class="stats">
          {stat_card("Open classified", compact(gut_open_total), "Gutenberg issues", "soft")}
          {stat_card("Bug share", pct(gut_bug_open_share), "of open Gutenberg backlog", "watch")}
        </div>
        {''.join(horizontal_count_metric(f"{category_label(row.get('category'))} ({pct(float(row.get('open_category_share_pct') or 0))})", num(row.get("open_count")), category_open_max, category_colors.get(row.get("category"), COLORS["neutral"]), " open") for row in gut_open_category_rows[:7])}
      </div>
    </div>
  </section>

  <section id="market" class="section">
    <h2>Market Position</h2>
    <p class="callout">The market signal is: WordPress is still far ahead, but its share has flattened and recently declined while hosted builders gained small, distributed share. Read this section as three evidence layers: measured installed share, current newly found-site proxy, and demand/attention proxies.</p>
    <div class="stats">
      {stat_card("W3Techs all-site share", pct(wp_usage_latest["value"]) if wp_usage_latest else "n/a", f"{wp_usage_latest['date'] if wp_usage_latest else 'not fetched'}", "soft")}
      {stat_card("W3Techs CMS share", pct(wp_cms_latest["value"]) if wp_cms_latest else "n/a", f"{wp_cms_latest['date'] if wp_cms_latest else 'not fetched'}", "soft")}
      {stat_card("HTTP Archive mobile CMS share", "64.3%", "WordPress in 2025 Web Almanac", "soft")}
      {stat_card("Top 10k CMS usage", "about 58%", "HTTP Archive 2025", "soft")}
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>Evidence map</h3>
        <p>These signals answer different questions. Installed-share sources are the strongest adoption evidence. BuiltWith's 90-day pipeline is useful for current direction, but it is not a multi-year new-site cohort. Developer, hiring, and public-interest sources are demand proxies.</p>
        <div class="stats">
          {stat_card("Installed share", "Strong", "W3Techs + HTTP Archive", "good")}
          {stat_card("Current new-site proxy", "Useful", "BuiltWith 30/90-day pipeline", "soft")}
          {stat_card("Demand proxies", "Directional", "SO, HN, jobs, pageviews", "soft")}
          {stat_card("True new-site history", "Partial", "not yet multi-year", "watch")}
        </div>
      </div>
      <div class="card">
        <h3>Decision framing</h3>
        <p>If the question is whether WordPress is still widely chosen, use W3Techs, HTTP Archive, and traffic-tier presence. If the question is whether new builders are choosing it right now, use BuiltWith cautiously and compare it with hosted-builder momentum. If the question is developer mindshare, use the demand proxies below.</p>
        {horizontal_metric("Installed-share confidence", 90, 100, COLORS["green"])}
        {horizontal_metric("Current new-site confidence", 62, 100, COLORS["core"])}
        {horizontal_metric("Demand-proxy confidence", 55, 100, COLORS["orange"])}
      </div>
    </div>
    <div class="grid-2">
      {svg_line_chart("Share of all websites", "W3Techs yearly usage trend. This includes sites with no known CMS.", market_usage_series, y_suffix="%")}
      {svg_line_chart("Share among CMS sites", "W3Techs yearly CMS market-share trend.", market_cms_series, y_suffix="%")}
    </div>
    <div class="grid-2">
      {svg_line_chart("HTTP Archive mobile origins", "Monthly mobile-crawl origin counts from the HTTP Archive Technology Report API. This is independent crawl coverage, not newly created sites.", http_archive_adoption_series)}
      <div class="card">
        <h3>HTTP Archive readout</h3>
        <p>HTTP Archive adds a monthly crawl-based adoption view. It is useful for direction and comparison, but it counts detected origins in the crawl rather than new site creation.</p>
        <div class="stats">
          {stat_card("WordPress origins", compact(num(http_wp_latest.get("mobile_origins"))), http_archive_latest_date or "not fetched", "good" if http_wp_latest else "watch")}
          {stat_card("Next peer", compact(num(http_next_peer.get("mobile_origins"))), http_next_peer.get("technology", "not fetched"), "soft" if http_next_peer else "watch")}
          {stat_card("WP vs next", f"{http_peer_ratio:.1f}x" if http_peer_ratio else "n/a", "mobile origins", "soft")}
          {stat_card("Monthly rows", compact(len(http_archive_adoption)), f"{http_archive_first_date} to {http_archive_latest_date}" if http_archive_dates else "not fetched", "good" if http_archive_adoption else "watch")}
        </div>
      </div>
    </div>
    <div class="grid-2">
      {svg_line_chart("Tracked technology share over time", "HTTP Archive mobile-crawl share among tracked WordPress and builder technologies. Recurring crawl signal; not a new-site cohort.", http_archive_share_series, y_suffix="%")}
      <div class="card">
        <h3>Builder-share readout</h3>
        <p>This is not a new-site cohort, but it is a recurring crawl-based comparison of WordPress against hosted builders and ecommerce platforms in the same detected-origin dataset.</p>
        <div class="stats">
          {stat_card("Latest WP tracked share", pct(float(http_share_latest_wp.get("mobile_tracked_share_pct") or 0)), http_share_latest_date or "not fetched", "good" if http_share_latest_wp else "watch")}
          {stat_card("Change since first month", f"{http_share_wp_delta:+.1f} pts" if http_share_wp_delta is not None else "n/a", f"{http_share_first_date} to {http_share_latest_date}" if http_share_dates else "not fetched", "watch" if http_share_wp_delta is not None and http_share_wp_delta < 0 else "soft")}
          {stat_card("Largest current peer", pct(float(http_share_latest_peer.get("mobile_tracked_share_pct") or 0)), http_share_latest_peer.get("technology", "not fetched"), "soft" if http_share_latest_peer else "watch")}
          {stat_card("Derived rows", compact(len(http_archive_tracked_share)), "stored in SQLite", "good" if http_archive_tracked_share else "watch")}
        </div>
      </div>
    </div>
    <div class="grid-2">
      {svg_line_chart("Good Core Web Vitals on mobile", "Monthly share of mobile origins passing Core Web Vitals in the HTTP Archive Technology Report API.", http_archive_cwv_series, y_suffix="%")}
      <div class="card">
        <h3>Experience-quality readout</h3>
        <p>Core Web Vitals adds a field-quality view next to adoption. This measures the share of crawled origins with good mobile user-experience signals, not project ticket volume.</p>
        <div class="stats">
          {stat_card("WordPress good CWV", pct(float(http_cwv_wp_latest.get("mobile_good_pct") or 0)), http_cwv_latest_date or "not fetched", "soft" if http_cwv_wp_latest else "watch")}
          {stat_card("Best tracked peer", pct(float(http_cwv_best_peer.get("mobile_good_pct") or 0)), http_cwv_best_peer.get("technology", "not fetched"), "soft" if http_cwv_best_peer else "watch")}
          {stat_card("WP gap", f"{http_cwv_gap:+.1f} pts" if http_cwv_wp_latest and http_cwv_best_peer else "n/a", "vs best tracked peer", "watch" if http_cwv_gap < 0 else "soft")}
          {stat_card("Monthly rows", compact(len(http_archive_cwv)), "CWV metric rows in SQLite", "good" if http_archive_cwv else "watch")}
        </div>
      </div>
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>HTTP Archive top-site tiers</h3>
        <p>Latest mobile-crawl origin counts by HTTP Archive rank tier. The percentages are WordPress share among the five tracked technologies, not share of the entire tier.</p>
        <div class="stats">
          {stat_card("Snapshot", http_rank_latest_date or "not fetched", "HTTP Archive API", "soft")}
          {stat_card("Top 1M WP origins", compact(num(http_rank_top1m.get("wp_mobile_origins"))), "mobile crawl", "good" if http_rank_top1m else "watch")}
          {stat_card("Top 1M tracked share", pct(float(http_rank_top1m.get("wp_tracked_share_pct") or 0)), "among tracked technologies", "soft" if http_rank_top1m else "watch")}
        </div>
        {''.join(horizontal_count_metric(f"{row.get('rank')} WordPress", num(row.get("wp_mobile_origins")), http_rank_max_wp, COLORS["wordpress"], " origins") for row in http_rank_summary)}
      </div>
      <div class="card">
        <h3>WordPress vs peers by tier</h3>
        <p>Peer comparison within the tracked set: WordPress, Shopify, Wix, Squarespace, and Webflow. This shows whether WordPress remains ahead in higher-traffic tiers.</p>
        {''.join(horizontal_metric(f"{row.get('rank')} tracked share", float(row.get("wp_tracked_share_pct") or 0), 100, COLORS["green"] if float(row.get("wp_tracked_share_pct") or 0) >= 70 else COLORS["core"]) for row in http_rank_summary)}
        {''.join(horizontal_count_metric(f"{row.get('rank')} next peer: {row.get('next_peer')}", num(row.get("next_peer_mobile_origins")), max(1, num(row.get("wp_mobile_origins"))), COLORS["neutral"], " origins") for row in http_rank_summary[:4])}
      </div>
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>WordPress.org install mix</h3>
        <p>Current WordPress.org stats API distribution. This is an installed-base snapshot from update checks, not a history of new sites.</p>
        <div class="stats">
          {stat_card("Top WP version", str(top_wp_version.get("label", "n/a")), pct(float(top_wp_version.get("share_pct") or 0)), "good" if top_wp_version else "watch")}
          {stat_card("Top PHP version", str(top_php_version.get("label", "n/a")), pct(float(top_php_version.get("share_pct") or 0)), "soft" if top_php_version else "watch")}
          {stat_card("PHP 8.1+", pct(php_81_plus_share), "reported installs", "soft")}
          {stat_card("Snapshot", wporg_stats_snapshot_date or "not fetched", "WordPress.org stats API", "soft")}
        </div>
        {''.join(horizontal_metric(f"WordPress {row.get('label')}", float(row.get("share_pct") or 0), 100, COLORS["wordpress"]) for row in top_wp_versions[:6])}
      </div>
      <div class="card">
        <h3>Hosting runtime mix</h3>
        <p>Current PHP and database distribution from WordPress.org stats. This adds deployment-context evidence for performance and compatibility decisions.</p>
        {''.join(horizontal_metric(f"PHP {row.get('label')}", float(row.get("share_pct") or 0), 100, COLORS["green"] if str(row.get("label", "")).startswith("8.") else COLORS["orange"]) for row in top_php_versions[:6])}
        {''.join(horizontal_metric(str(row.get("family")), float(row.get("share_pct") or 0), 100, COLORS["purple"] if row.get("family") == "MariaDB" else COLORS["core"]) for row in db_family_rows)}
        <div class="stats">
          {stat_card("MariaDB", pct(mariadb_share), "database share", "soft")}
          {stat_card("MySQL", pct(mysql_share), "database share", "soft")}
        </div>
      </div>
    </div>
    <div class="card">
      <h3>Attention and demand proxy readout</h3>
      <p>Compact direction check across the report's public attention, developer-help, hiring, and WordPress-specific job-board proxies. These rows are directional; they do not replace Google Trends or a broad labor-market export.</p>
      <div class="stats">
        {''.join(attention_stat_cards)}
      </div>
      <div class="grid-2">
        <div>
          {''.join(attention_change_bars)}
        </div>
        <p class="small-note">Rows are stored in SQLite as <code>attention_demand_summary</code>. Baselines use the latest available pre-2024 quarter or archived snapshot where the source supports it.</p>
      </div>
    </div>
    <div class="grid-2">
      {svg_line_chart("Stack Overflow developer attention", "Quarterly Stack Overflow questions by tag from the Stack Exchange API. This is a developer-help signal, not general web search demand.", stack_overflow_tag_series)}
      <div class="card">
        <h3>Developer-interest readout</h3>
        <p>Stack Overflow tag volume is much narrower than overall site-builder demand, but it shows whether developers are asking for help with WordPress and comparable builder/ecommerce ecosystems.</p>
        <div class="stats">
          {stat_card("Latest WordPress tag", compact(num(latest_so_wp.get("question_count"))), latest_so_wp.get("label", "not fetched"), "soft")}
          {stat_card("Change vs pre-2024", f"{so_wp_delta:+,}" if so_wp_delta is not None else "n/a", "latest quarter minus last pre-2024 quarter", "watch" if so_wp_delta is not None and so_wp_delta < 0 else "soft")}
          {stat_card("Coverage", compact(len(stack_overflow_tags)), "tag-quarter rows in SQLite", "good" if stack_overflow_tags else "watch")}
          {stat_card("Full-history tags", f"{len(so_full_history_labels)}/{len(STACK_OVERFLOW_TAGS)}", so_expected_label, "soft")}
        </div>
        <p class="small-note">{html.escape(so_coverage_detail)}</p>
      </div>
    </div>
    <div class="grid-2">
      {svg_line_chart("Public attention proxy", "Quarterly en.wikipedia article pageviews from the Wikimedia Pageviews API. This is not search volume, but it is a stable public-interest signal.", wikimedia_pageview_series)}
      <div class="card">
        <h3>Public-interest readout</h3>
        <p>Wikimedia article views help separate broad public attention from developer-help and hiring signals. They are a proxy, not a direct measure of site-builder selection.</p>
        <div class="stats">
          {stat_card("Latest WordPress views", compact(num(latest_wikimedia_wp.get("views"))), latest_wikimedia_wp.get("label", "not fetched"), "soft")}
          {stat_card("Change vs pre-2024", f"{wikimedia_wp_delta:+,}" if wikimedia_wp_delta is not None else "n/a", "latest quarter minus last pre-2024 quarter", "watch" if wikimedia_wp_delta is not None and wikimedia_wp_delta < 0 else "soft")}
          {stat_card("Coverage", compact(len(wikimedia_pageviews_q)), "article-quarter rows in SQLite", "good" if wikimedia_pageviews_q else "watch")}
        </div>
      </div>
    </div>
    <div class="grid-2">
      {svg_line_chart("HN Who is hiring mentions", "Quarterly top-level comments in Hacker News monthly Who is hiring threads that mention WordPress, WooCommerce, PHP, or agencies/studios.", hn_hiring_series)}
      {svg_line_chart("HN hiring mentions per 100 comments", "Quarterly mention rates within Hacker News monthly Who is hiring threads. This normalizes for thread size.", hn_hiring_rate_series)}
    </div>
    <div class="card">
      <h3>Hiring-proxy readout</h3>
      <p>This is a narrow startup-hiring proxy from HN threads, not a complete job-market view. Direct WordPress/WooCommerce mentions are small; PHP and agency/studio mentions give useful adjacent context.</p>
      <div class="stats">
        {stat_card("Since 2024 WP/Woo rate", per_100(hn_since_2024.get("wordpress_or_woocommerce_per_100_comments")), hn_since_2024.get("quarter_range", "not fetched"), "soft")}
        {stat_card("Latest 4Q WP/Woo", compact(num(hn_latest_4q.get("wordpress_or_woocommerce_comments"))), per_100(hn_latest_4q.get("wordpress_or_woocommerce_per_100_comments")), "watch")}
        {stat_card("Latest 4Q PHP", compact(num(hn_latest_4q.get("php_comments"))), per_100(hn_latest_4q.get("php_per_100_comments")), "soft")}
        {stat_card("Latest 4Q agency/studio", compact(num(hn_latest_4q.get("agency_comments"))), per_100(hn_latest_4q.get("agency_per_100_comments")), "soft")}
        {stat_card("Thread coverage", compact(hn_hiring_months), "monthly hiring threads parsed", "good" if hn_hiring_months else "watch")}
        {stat_card("Coverage range", hn_hiring_range_label, "HN monthly threads", "soft")}
      </div>
      <div class="grid-2">
        <div>
          {horizontal_count_metric("Latest 4Q WP/Woo mentions", num(hn_latest_4q.get("wordpress_or_woocommerce_comments")), hn_demand_mentions_max, COLORS["wordpress"], "")}
          {horizontal_count_metric("Latest 4Q PHP mentions", num(hn_latest_4q.get("php_comments")), hn_demand_mentions_max, COLORS["purple"], "")}
          {horizontal_count_metric("Latest 4Q agency/studio mentions", num(hn_latest_4q.get("agency_comments")), hn_demand_mentions_max, COLORS["orange"], "")}
        </div>
        <p class="small-note">Summary rows are stored in SQLite as <code>hn_hiring_demand_summary</code>, with all-time, pre-2024, since-2024, latest-four-quarter, and latest-quarter windows.</p>
      </div>
    </div>
    <div class="grid-2">
      {svg_line_chart("WordPress Jobs board open listings", "Annual archived snapshots plus the current jobs.wordpress.net page. This is WordPress-specific open-listing demand, not a broad labor-market index.", wordpress_jobs_series)}
      <div class="card">
        <h3>Jobs-board readout</h3>
        <p>Open listings on jobs.wordpress.net add a WordPress-specific demand signal. The series is a snapshot view: it counts visible open listings on captured pages, not total postings over the whole year.</p>
        <div class="stats">
          {stat_card("Latest open listings", compact(latest_jobs_total), latest_jobs_snapshot.get("snapshot_date", "not fetched"), "soft")}
          {stat_card("Development share", pct(latest_jobs_development_share), f"{compact(latest_development_jobs)} current listings", "soft")}
          {stat_card("Project-style share", pct(latest_jobs_project_share), f"{compact(latest_project_jobs)} current listings", "soft")}
          {stat_card("Archive snapshots", compact(len(jobs_archive_snapshots)), jobs_range_label, "good" if jobs_archive_snapshots else "watch")}
        </div>
        {''.join(horizontal_count_metric(str(row.get("category", "")), num(row.get("open_jobs")), max_latest_jobs_category, COLORS["community"] if row.get("category_slug") == "project" else COLORS["core"], " listings") for row in latest_jobs_categories[:6])}
      </div>
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>Enterprise adoption snapshot</h3>
        <p>Current public WordPress VIP case-study records. This is a curated enterprise evidence source, not a count of all enterprise WordPress sites.</p>
        <div class="stats">
          {stat_card("VIP case studies", compact(len(enterprise_vip_cases)), "public REST API rows", "good" if enterprise_vip_cases else "watch")}
          {stat_card("Since 2024", compact(enterprise_recent_cases), "published case-study rows", "soft")}
        </div>
        {''.join(horizontal_count_metric(name, count, max_enterprise_industry_count, COLORS["core"], "") for name, count in top_enterprise_industries)}
      </div>
      <div class="card">
        <h3>Recent enterprise case studies</h3>
        <p>Latest public case-study posts from WordPress VIP. Use-case terms are sparse in the API, so industry mix is the better structured view.</p>
        {''.join(horizontal_count_metric(name, count, max_enterprise_use_case_count, COLORS["purple"], "") for name, count in top_enterprise_use_cases)}
        <div class="link-list">{''.join(f'<a href="{html.escape(str(row.get("link", "")))}">{html.escape(str(row.get("title", "")))}</a>' for row in latest_enterprise_cases)}</div>
      </div>
    </div>
    <div class="card">
      <h3>New-site choice proxy readout</h3>
      <p>Compact current-direction summary from BuiltWith newly found-site counts, HTTP Archive tracked-share history, and BuiltWith traffic-tier presence. See the <a href="new_site_choice.html">new-site choice view</a> for the easier visual readout.</p>
      <div class="stats">
        {''.join(new_site_summary_cards)}
      </div>
      <div class="grid-2">
        <div>
          {''.join(new_site_summary_bars)}
        </div>
        <p class="small-note">Rows are stored in SQLite as <code>new_site_choice_summary</code>. Use this as a decision summary, then inspect the BuiltWith and HTTP Archive charts below for source context.</p>
      </div>
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>Newly found site pipeline</h3>
        <p>BuiltWith public Net New Pipeline counts for the last 90 days. Squarespace's top-level CMS page does not expose new-site counts, so it is excluded from this share.</p>
        <div class="stats">
          {stat_card("WordPress share", pct(builtwith_wp_90_share), "of tracked 90-day new-site counts", "soft")}
          {stat_card("WordPress 90 days", compact(builtwith_wp_90), "BuiltWith newly found sites", "good")}
          {stat_card("WordPress 30 days", compact(builtwith_wp_30), f"{pct(builtwith_wp_30_share)} of tracked set", "good")}
          {stat_card("Tracked set", compact(builtwith_total_90), "WordPress, Shopify, Wix, Webflow", "soft")}
        </div>
        {''.join(horizontal_count_metric(str(row.get("technology", "")), num(row.get("new_last_3_months")), builtwith_max_90, COLORS.get(str(row.get("technology", "")).lower(), COLORS["neutral"]), "") for row in builtwith_new_rows)}
      </div>
      <div class="card">
        <h3>Top-site presence</h3>
        <p>BuiltWith traffic-tier counts show where each technology appears among higher-traffic sites.</p>
        {''.join(horizontal_count_metric(f"{tech} top 1M", num(row.get("top_1m")), max([num(r.get("top_1m")) for r in builtwith_new_sites] or [1]), COLORS.get(str(tech).lower(), COLORS["neutral"]), "") for tech, row in builtwith_by_tech.items())}
      </div>
    </div>
    <div class="card">
      <h3>WordPress share by site size tier</h3>
      <p>BuiltWith current counts across WordPress, Shopify, Wix, Squarespace, and Webflow. Long tail means live sites outside the Top 1M tier.</p>
      <div class="grid-2">
        <div>
          {''.join(horizontal_metric(str(row.get("label", "")), float(row.get("wordpress_share_pct") or 0), 100, COLORS["wordpress"]) for row in builtwith_tier_share_ordered)}
        </div>
        <div class="stats">
          {stat_card("Top 1M share", pct(float(next((row.get("wordpress_share_pct") for row in builtwith_tier_share_ordered if row.get("tier") == "top_1m"), 0) or 0)), "among tracked technologies", "soft")}
          {stat_card("Long-tail share", pct(float(next((row.get("wordpress_share_pct") for row in builtwith_tier_share_ordered if row.get("tier") == "long_tail"), 0) or 0)), "outside BuiltWith Top 1M", "soft")}
        </div>
      </div>
    </div>
    <div class="grid-2">
      {svg_line_chart("BuiltWith ecommerce live sites", "Historical live-site counts from BuiltWith ecommerce technology pages. This is installed-site presence, not new-site creation.", builtwith_total_live_series)}
      {svg_line_chart("BuiltWith ecommerce Top 1M presence", "Historical live-site counts among the Top 1M traffic tier.", builtwith_top1m_series)}
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>WooCommerce ecommerce signal</h3>
        <p>WooCommerce appears in both BuiltWith ecommerce tracking and the WordPress.org plugin directory.</p>
        <div class="stats">
          {stat_card("BuiltWith live", compact(num(woocommerce_builtwith.get("total_live"))), "WooCommerce ecommerce page", "good")}
          {stat_card("BuiltWith 90 days", compact(num(woocommerce_builtwith.get("new_last_3_months"))), "recently found sites", "good")}
          {stat_card("Top 1M", compact(num(woocommerce_builtwith.get("top_1m"))), "BuiltWith traffic tier", "soft")}
          {stat_card("Plugin installs", compact(num(woocommerce_plugin.get("active_installs"))), "WordPress.org active installs", "good")}
        </div>
        {horizontal_count_metric("WooCommerce live sites", num(woocommerce_builtwith.get("total_live")), builtwith_ecommerce_live_max, COLORS["purple"], "")}
        {horizontal_count_metric("WooCommerce Top 1M", num(woocommerce_builtwith.get("top_1m")), max([num(row.get("top_1m")) for row in builtwith_ecommerce_live_rows] or [1]), COLORS["purple"], "")}
      </div>
      <div class="card">
        <h3>BuiltWith ecommerce footprint</h3>
        <p>Current live-site totals from the fetched BuiltWith ecommerce pages.</p>
        {''.join(horizontal_count_metric(str(row.get("technology", "")), num(row.get("total_live")), builtwith_ecommerce_live_max, COLORS.get(str(row.get("technology", "")).lower(), COLORS["purple"] if row.get("technology") == "WooCommerce" else COLORS["neutral"]), "") for row in sorted(builtwith_ecommerce_live_rows, key=lambda item: num(item.get("total_live")), reverse=True))}
      </div>
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>Plugin directory activity</h3>
        <p>Current WordPress.org plugin directory browse samples. The 90-day counts show a prefix when the API sample hit the page cap before passing 90 days.</p>
        <div class="stats">
          {stat_card("Added 30 days", compact(plugins_added_30), "new plugin browse", "good")}
          {stat_card("Added 90 days", plugins_added_90_label, f"{num(directory_activity_snapshot.get('plugins_added_pages_fetched'))} pages fetched", "good")}
          {stat_card("Updated 30 days", compact(plugins_updated_30), "updated plugin browse", "soft")}
          {stat_card("Updated 90 days", plugins_updated_90_label, f"{num(directory_activity_snapshot.get('plugins_updated_pages_fetched'))} pages fetched", "soft")}
        </div>
        {horizontal_count_metric("Plugins added in sampled 90 days", plugins_added_90, plugin_activity_max, COLORS["green"], "")}
        {horizontal_count_metric("Plugins updated in sampled 90 days", plugins_updated_90, plugin_activity_max, COLORS["core"], "")}
      </div>
      <div class="card">
        <h3>Stale popular plugin sample</h3>
        <p>Popular plugin pages from the WordPress.org API. Stale here means last updated more than two years before the snapshot date.</p>
        <div class="stats">
          {stat_card("Popular sample", compact(stale_plugin_sample_size), "plugins fetched", "soft")}
          {stat_card("Stale 2y", compact(stale_plugin_count), "popular plugins", "watch")}
          {stat_card("Install share", pct(stale_plugin_install_share), "active installs on stale sample", "watch")}
          {stat_card("Median age", f"{compact(stale_plugin_median_age)} days", "since last update", "soft")}
        </div>
        {horizontal_metric("Stale share of popular sample", stale_plugin_sample_share, 100, COLORS["orange"])}
        {horizontal_metric("Active-install share on stale sample", stale_plugin_install_share, 100, COLORS["red"])}
        {horizontal_count_metric("P90 days since update", stale_plugin_p90_age, max(1825, stale_plugin_p90_age), COLORS["orange"], " days")}
        {''.join(horizontal_count_metric(str(row.get("name", "")), num(row.get("active_installs")), max_stale_plugin_installs, COLORS["prs"], " installs") for row in top_stale_popular_plugins[:5])}
      </div>
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>Major plugin install-base snapshot</h3>
        <p>Fixed-slug WordPress.org plugin API snapshot for widely used plugins. Active installs are rounded and overlap across sites, so they show ecosystem reach, not unique adoption.</p>
        <div class="stats">
          {stat_card("Plugins tracked", compact(len(major_plugin_rows)), "fixed major-plugin list", "soft")}
          {stat_card("Reported installs", compact(total_major_plugin_installs), "summed, overlapping active installs", "good")}
          {stat_card("Updated 90 days", compact(recently_updated_major_plugins), "of tracked plugins", "soft")}
        </div>
        {''.join(horizontal_count_metric(str(row.get("name", "")), num(row.get("active_installs")), max_major_plugin_installs, COLORS["core"], " installs") for row in top_major_plugins[:8])}
      </div>
      <div class="card">
        <h3>Major plugin download trend</h3>
        <p>WordPress.org daily download stats for the same fixed major-plugin list. Downloads show update and demand activity; they are not active installs.</p>
        <div class="stats">
          {stat_card("Daily rows", compact(len(major_plugin_download_daily)), "WordPress.org stats API", "good" if major_plugin_download_daily else "watch")}
          {stat_card("Latest sampled quarter", compact(latest_plugin_download_total), latest_plugin_download_quarter or "not fetched", "soft")}
          {stat_card("Days in latest quarter", compact(latest_plugin_download_days), "maximum per tracked plugin", "soft")}
        </div>
      </div>
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>Major plugin support load</h3>
        <p>Current WordPress.org plugin API support-thread counts for the fixed major-plugin list. This is a snapshot of visible support load, not a long-term forum trend.</p>
        <div class="stats">
          {stat_card("Support threads", compact(total_major_plugin_support_threads), "tracked major plugins", "soft")}
          {stat_card("Unresolved", compact(total_major_plugin_support_unresolved), "support threads", "watch")}
          {stat_card("Resolved share", pct(total_major_plugin_support_resolved_pct), "of support threads", "good" if total_major_plugin_support_resolved_pct >= 80 else "soft")}
        </div>
        {''.join(horizontal_count_metric(plugin_name_by_slug.get(str(row.get("slug") or ""), str(row.get("name", ""))), num(row.get("support_threads")), max_major_plugin_support_threads, COLORS["community"], " threads") for row in top_support_plugins)}
      </div>
      <div class="card">
        <h3>Support resolution snapshot</h3>
        <p>Resolved share for the highest-load tracked plugins. Unresolved counts highlight where current visible support queues are heavier.</p>
        {''.join(horizontal_metric(plugin_name_by_slug.get(str(row.get("slug") or ""), str(row.get("name", ""))), float(row.get("support_resolved_pct") or 0), 100, COLORS["green"] if float(row.get("support_resolved_pct") or 0) >= 80 else COLORS["orange"]) for row in top_support_plugins[:6])}
        {''.join(horizontal_count_metric(f"{plugin_name_by_slug.get(str(row.get('slug') or ''), str(row.get('name', '')))} unresolved", num(row.get("support_unresolved")), max_major_plugin_unresolved, COLORS["red"], " open") for row in top_unresolved_plugins[:4])}
      </div>
    </div>
    {svg_line_chart("Major plugin install-base history", "Annual Wayback snapshots plus the current WordPress.org API snapshot. Rounded active-install buckets, not exact counts.", major_plugin_install_history_series, show_end_labels=False)}
    <div class="card">
      <h3>Active-install history readout</h3>
      <p>These archived plugin-page values are rounded active-install buckets, but they add direction to the current snapshot and help separate mature install reach from short-term download activity.</p>
      <div class="stats">
        {stat_card("Archived rows", compact(len(install_history_archive_rows)), "Wayback plugin snapshots", "good" if install_history_archive_rows else "watch")}
        {stat_card("Plugins covered", f"{install_history_plugin_count}/{len(MAJOR_PLUGIN_SLUGS)}", "tracked major plugins", "good" if install_history_plugin_count == len(MAJOR_PLUGIN_SLUGS) else "watch")}
        {stat_card("Archive years", compact(install_history_year_count), install_history_year_range, "soft")}
        {stat_card("Current rows", compact(len(install_history_latest_rows)), "WordPress.org API snapshot", "soft")}
      </div>
      {horizontal_count_metric("Current install snapshot coverage", len(major_plugin_rows), max(1, len(MAJOR_PLUGIN_SLUGS)), COLORS["green"], " plugins")}
      {horizontal_count_metric("Historical install-history coverage", install_history_plugin_count, max(1, len(MAJOR_PLUGIN_SLUGS)), COLORS["core"], " plugins")}
      {horizontal_count_metric("Download trend coverage", major_plugin_download_plugin_count, max(1, len(MAJOR_PLUGIN_SLUGS)), COLORS["core"], " plugins")}
    </div>
    {svg_line_chart("Major plugin downloads by quarter", "WordPress.org daily download stats, aggregated quarterly for the highest-download tracked plugins. Latest quarter may be partial.", major_plugin_download_series)}
    <div class="grid-2">
      <div class="card">
        <h3>Theme directory browse sample</h3>
        <p>The theme API exposes browse lists but not add/update dates in the sampled rows, so this is a current directory shape snapshot rather than a trend.</p>
        <div class="stats">
          {stat_card("New sample", compact(num(directory_activity_snapshot.get("theme_new_sample_size"))), f"{compact(num(directory_activity_snapshot.get('theme_new_results')))} total browse results", "good")}
          {stat_card("Updated sample", compact(num(directory_activity_snapshot.get("theme_updated_sample_size"))), f"{compact(num(directory_activity_snapshot.get('theme_updated_results')))} total browse results", "soft")}
          {stat_card("Popular sample", compact(num(directory_activity_snapshot.get("theme_popular_sample_size"))), f"{compact(num(directory_activity_snapshot.get('theme_popular_results')))} total browse results", "soft")}
          {stat_card("Theme directory", compact(theme_count), "current WordPress.org API result", "good")}
        </div>
      </div>
      <div class="card">
        <h3>Popular themes by ratings</h3>
        <p>Top sampled popular themes ranked by rating count in the current WordPress.org theme API response.</p>
        {''.join(horizontal_count_metric(str(row.get("name", "")), num(row.get("num_ratings")), max_popular_theme_ratings, COLORS["community"], " ratings") for row in top_popular_themes)}
      </div>
    </div>
    <div class="stats">
      {stat_card("Plugin directory", compact(plugin_count), "current WordPress.org API result", "good")}
      {stat_card("Theme directory", compact(theme_count), "current WordPress.org API result", "good")}
      {stat_card("WordCamp records", compact(len(wordcamps)), "WordCamp Central records fetched", "good")}
      {stat_card("Five for the Future", compact(num(fttf_snapshot.get("pledges_fetched"))), "current pledges fetched", "good")}
    </div>
  </section>

  <section id="goal-map" class="section">
    <h2>Goal Coverage Map</h2>
    <p class="callout">This is the quick read on how much weight to put on each part of the report. The strongest areas have direct quarterly data. Softer areas use snapshots or public proxies because a full historical market export is not available here.</p>
    <div class="goal-map" aria-label="Goal coverage map">
      <div class="goal-row good">
        <div><strong>Ticket flow and backlog</strong><p>Core Trac, Gutenberg issues, and wordpress-develop PRs.</p></div>
        <div><span class="goal-status">Strong</span></div>
        <div><p>Use for new vs closed work, net flow, open backlog, response time, close time, stale share, and reopened rate.</p></div>
      </div>
      <div class="goal-row good">
        <div><strong>Participation funnel</strong><p>Reporters, first-time people, repeat people, PR authors, and contributor depth.</p></div>
        <div><span class="goal-status">Strong</span></div>
        <div><p>Use for whether participation is broadening or narrowing. The current answer is fewer new tracker reporters, while PR flow is steadier.</p></div>
      </div>
      <div class="goal-row good">
        <div><strong>Bug and feature mix</strong><p>Classified Core and Gutenberg tickets/issues.</p></div>
        <div><span class="goal-status">Strong</span></div>
        <div><p>Use the separate bug, feature-request, enhancement, task, and all-ticket views instead of a stacked total.</p></div>
      </div>
      <div class="goal-row soft">
        <div><strong>Ecosystem participation</strong><p>Props, committers, Make/Core, WordCamps, translations, Five for the Future, plugins, and themes.</p></div>
        <div><span class="goal-status">Directional</span></div>
        <div><p>Good for showing activity outside ticket trackers. Some series are historical; others are current snapshots.</p></div>
      </div>
      <div class="goal-row good">
        <div><strong>Installed market position</strong><p>W3Techs, HTTP Archive, BuiltWith traffic tiers, WordPress.org stats.</p></div>
        <div><span class="goal-status">Strong</span></div>
        <div><p>Use for whether WordPress is still widely used. It is still the default CMS, but recent share signals are softer.</p></div>
      </div>
      <div class="goal-row watch">
        <div><strong>New-site choice</strong><p>BuiltWith 30/90-day pipeline plus recurring HTTP Archive origin counts.</p></div>
        <div><span class="goal-status">Current proxy</span></div>
        <div><p>Use for current direction only. It is not a multi-year newly created site cohort.</p></div>
      </div>
      <div class="goal-row partial">
        <div><strong>Demand and mindshare</strong><p>Stack Overflow, Wikimedia, HN hiring, and WordPress Jobs snapshots.</p></div>
        <div><span class="goal-status">Partial proxy</span></div>
        <div><p>Useful for public/developer attention, but not a replacement for Google Trends or a broad hiring-platform export.</p></div>
      </div>
      <div class="goal-row watch">
        <div><strong>Support load</strong><p>Current WordPress.org support queues and major-plugin support counts.</p></div>
        <div><span class="goal-status">Snapshot</span></div>
        <div><p>Use for where support load sits now. A full historical forum export would make trend claims stronger.</p></div>
      </div>
    </div>
  </section>

  <section id="coverage" class="section">
    <h2>Source Coverage</h2>
    <p class="callout">The SQLite database stores imported source tables, fetched ecosystem/adoption records, file hashes, and explicit source gaps. Download: <a href="community_health.sqlite.gz">community_health.sqlite.gz</a>. Inventory: <a href="data_inventory.html">data_inventory.html</a>. Source gap plan: <a href="source_gap_plan.html">source_gap_plan.html</a>. Goal audit: <a href="goal_audit.html">goal_audit.html</a>.</p>
    <div class="grid-2">
      <div class="card">
        <h3>Refresh provenance</h3>
        <p>The report is built from local ticket exports plus public-source fetches. The SQLite database stores source-file paths, row counts, and SHA-256 hashes for local imports, so a later refresh can verify whether the underlying exports changed. The <a href="data_inventory.html">data inventory</a> lists the current tables, source hashes, and partial-source gaps.</p>
        <div class="stats">
          {stat_card("Local source files", compact(local_source_file_count), f"{compact(local_source_row_count)} imported rows", "good")}
          {stat_card("Fetched tables", compact(len(fetched_nonempty_tables)), f"{compact(fetched_row_count)} fetched/derived rows", "good")}
          {stat_card("Covered signals", compact(source_status_counts.get("covered", 0)), "source coverage cards", "good")}
          {stat_card("Partial signals", compact(source_status_counts.get("partial", 0)), "explicitly labeled", "watch")}
        </div>
      </div>
      <div class="card">
        <h3>Refresh path</h3>
        <p>Run the report generator to refresh public sources, or use cached data when validating layout and wording. After any database change, regenerate the data inventory too. The supporting fetch scripts keep Core response metrics, Gutenberg timelines, and support snapshots reproducible.</p>
        <div class="link-list">
          <code>python3 make_community_health_report.py</code>
          <code>python3 make_community_health_report.py --skip-network</code>
          <code>python3 refresh_report_artifacts.py</code>
          <code>python3 make_goal_audit.py</code>
          <code>python3 make_data_inventory.py</code>
          <code>fetch_core_response_metrics.py</code>
          <code>fetch_gutenberg_timeline_metrics.py</code>
          <code>fetch_support_forum_snapshot.py</code>
        </div>
      </div>
    </div>
    <div id="companion-docs" class="card">
      <h3>Companion documents</h3>
      <p>Use these alongside the main report depending on whether the reader needs a short decision brief, current progress, source audit, or refresh instructions.</p>
      <div class="link-list">
        <a href="decision_brief.html">Decision brief</a>
        <a href="progress_summary.html">Progress summary</a>
        <a href="project_load.html">Project load</a>
        <a href="market_position.html">Market position</a>
        <a href="new_site_choice.html">New-site choice</a>
        <a href="search_interest.html">Search interest</a>
        <a href="developer_interest.html">Developer interest</a>
        <a href="job_demand.html">Job demand</a>
        <a href="support_load.html">Support load</a>
        <a href="contributor_depth.html">Contributor depth</a>
        <a href="ecosystem_activity.html">Ecosystem activity</a>
        <a href="goal_audit.html">Goal audit</a>
        <a href="data_inventory.html">Data inventory</a>
        <a href="source_gap_plan.html">Source gap plan</a>
        <a href="refresh_runbook.html">Refresh runbook</a>
      </div>
    </div>
    <div class="card">
      <h3>Partial-source watchlist</h3>
      <p>These are the main places where the report uses a proxy or snapshot instead of a full historical source.</p>
      <div class="watchlist-grid">
        {''.join(f'<div class="status {status}"><span class="pill">{html.escape(status)}</span><b>{html.escape(name)}</b><span>{html.escape(note)}</span></div>' for name, status, note in source_attention_rows)}
      </div>
    </div>
    <div class="status-grid">
      {''.join(f'<div class="status {status}"><span class="pill">{html.escape(status)}</span><b>{html.escape(name)}</b><span>{html.escape(note)}</span></div>' for name, status, note in source_rows)}
    </div>
  </section>

  <section id="readout" class="section">
    <h2>Decision Readout</h2>
    <p class="callout">Short version: WordPress is still widely chosen on installed-share evidence; current new-site and demand proxies are softer; ticket participation has fewer new reporters; project load is closer to balanced than the backlog size alone suggests.</p>
    <div class="evidence-strength-grid">
      <div class="evidence-strength-card good">
        <span>Measured directly</span>
        <strong>Installed share and tracker flow</strong>
        <p>W3Techs, Core Trac, Gutenberg issues, PRs, releases, and WordPress.org APIs support the strongest claims.</p>
      </div>
      <div class="evidence-strength-card soft">
        <span>Derived from recurring data</span>
        <strong>Builder-share direction</strong>
        <p>HTTP Archive monthly origin counts show WordPress at {http_share_latest_wp_label} of the tracked set, {http_share_wp_delta_label} since {http_share_first_date or 'the first month'}.</p>
      </div>
      <div class="evidence-strength-card watch">
        <span>Proxy-led</span>
        <strong>New-site and demand signals</strong>
        <p>BuiltWith pipeline, Wikimedia, Stack Overflow, HN hiring, and Jobs snapshots point to direction but are not complete market measures.</p>
      </div>
      <div class="evidence-strength-card watch">
        <span>Broader source needed</span>
        <strong>Search, jobs, support history</strong>
        <p>Google Trends or similar, labor-market exports, and a fuller support-forum history would make those signals stronger.</p>
      </div>
    </div>
    <div class="readout-grid">
      <div class="readout-card">
        <strong>Community health: active, narrower entry funnel</strong>
        <p>Core and Gutenberg still get steady participation, but fewer first-time reporters are entering the trackers than in 2021-2023. Code review activity is not showing the same drop.</p>
        {horizontal_metric("Core first-time reporter retention", core_first_retention, 100, COLORS["red"])}
        {horizontal_metric("Gutenberg first-time creator retention", gut_first_retention, 100, COLORS["red"])}
        {horizontal_metric("PR creation vs 2021-2023", pr_flow_ratio, max(160, pr_flow_ratio), COLORS["green"])}
      </div>
      <div class="readout-card">
        <strong>Project load: mostly keeping up, backlog still aged</strong>
        <p>Since 2024, Core closures are slightly above new tickets on average, and Gutenberg is near balanced with a recent cleanup quarter. The remaining open backlog still contains a large older share.</p>
        {horizontal_metric("Core closure balance since 2024", core_closure_ratio, max(140, core_closure_ratio, gut_closure_ratio), COLORS["core"])}
        {horizontal_metric("Gutenberg closure balance since 2024", gut_closure_ratio, max(140, core_closure_ratio, gut_closure_ratio), COLORS["gutenberg"])}
        {horizontal_metric("Core stale open share", core_stale_pct, 100, COLORS["orange"])}
        {horizontal_metric("Gutenberg stale open share", gut_stale_pct, 100, COLORS["orange"])}
      </div>
      <div class="readout-card">
        <strong>Market position: dominant, recently softer</strong>
        <p>{html.escape(adoption_detail)} BuiltWith's current 90-day pipeline still shows WordPress with the largest tracked new-site count among WordPress, Shopify, Wix, and Webflow, but that is a current proxy rather than a historical new-site trend.</p>
        {horizontal_metric("W3Techs all-site share", float(wp_usage_latest["value"]) if wp_usage_latest else 0, 100, COLORS["wordpress"])}
        {horizontal_metric("W3Techs CMS share", float(wp_cms_latest["value"]) if wp_cms_latest else 0, 100, COLORS["wordpress"])}
        {horizontal_metric("HTTP Archive tracked share", float(http_share_latest_wp.get("mobile_tracked_share_pct") or 0), 100, COLORS["wordpress"])}
        {horizontal_metric("Tracked 90-day new-site share", builtwith_wp_90_share, 100, COLORS["green"])}
      </div>
    </div>
    <div class="stats decision-stats">
      {stat_card("Still widely chosen?", "Yes", f"{pct(wp_usage_latest['value']) if wp_usage_latest else 'n/a'} of all sites; {pct(wp_cms_latest['value']) if wp_cms_latest else 'n/a'} of CMS sites", "good")}
      {stat_card("Adoption direction", "Softer", f"{usage_delta:+.1f} all-site pts and {cms_delta:+.1f} CMS pts since Jan 2025" if usage_delta is not None and cms_delta is not None else "latest W3Techs trend fetched", "watch")}
      {stat_card("New-site evidence", "Current proxy", f"{pct(builtwith_wp_90_share)} of tracked 90-day BuiltWith pipeline; no multi-year cohort yet", "soft")}
      {stat_card("Participation direction", "Fewer reporters", f"Core first-time reporters retained {pct(core_first_retention)} of the 2021-2023 average; Gutenberg retained {pct(gut_first_retention)}.", "watch")}
      {stat_card("Keeping up?", "Mostly", f"Closure/new ratio since 2024: Core {pct(core_closure_ratio)}, Gutenberg {pct(gut_closure_ratio)}.", "soft")}
    </div>
  </section>

  <section class="footer">
    <p>Generated {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} from local Core/Gutenberg exports and public sources.</p>
    <p>Sources: <a href="{W3TECHS_USAGE_URL}">W3Techs usage trend</a>, <a href="{W3TECHS_MARKET_SHARE_URL}">W3Techs CMS market-share trend</a>, <a href="{HTTP_ARCHIVE_CMS_URL}">HTTP Archive Web Almanac CMS 2025</a>, <a href="{HTTP_ARCHIVE_TECH_REPORT_URL}">HTTP Archive Technology Report API</a>, <a href="{STACK_EXCHANGE_DOCS_URL}">Stack Exchange API</a>, <a href="{WIKIMEDIA_PAGEVIEWS_DOCS_URL}">Wikimedia Pageviews API</a>, <a href="https://api.wordpress.org/">WordPress.org APIs</a>, <a href="{PLUGIN_DOWNLOADS_DOCS_URL}">WordPress.org plugin download stats</a>, <a href="{WORDPRESS_JOBS_URL}">WordPress Jobs board</a>, <a href="{WAYBACK_CDX_API}">Internet Archive CDX API</a>, <a href="https://central.wordcamp.org/wp-json/wp/v2/wordcamps">WordCamp Central API</a>, <a href="{EVENTS_WORDPRESS_URL}">WordPress Events</a>, <a href="{TRANSLATE_LOCALES_URL}">Translate WordPress</a>, <a href="{MAKE_CORE_API}">Make/Core posts API</a>, <a href="{MAKE_CORE_COMMENTS_API}">Make/Core comments API</a>, <a href="https://wordpress.org/support/view/all-topics/">WordPress.org support forums</a>, <a href="https://trends.builtwith.com/cms/WordPress">BuiltWith technology pages</a>, <a href="https://github.com/WordPress/gutenberg/issues">Gutenberg GitHub issues</a>, <a href="{FTTF_PLEDGES_URL}">Five for the Future pledges</a>, <a href="{RELEASE_ARCHIVE_URL}">WordPress release archive</a>, and <a href="{CREDITS_API}">Core credits API</a>.</p>
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
    fetched.update(build_derived_metrics(data))
    fetched["builtwith_tier_share_snapshot"] = derive_builtwith_tier_share_snapshot(data.get("builtwith_new_site_snapshot", []))
    fetched["market_share"] = []
    fetched["market_share"].extend(parse_w3techs_history(W3TECHS_USAGE_URL, "all_sites_usage", args.skip_network))
    fetched["market_share"].extend(parse_w3techs_history(W3TECHS_MARKET_SHARE_URL, "cms_market_share", args.skip_network))
    fetched["http_archive_adoption_monthly"] = fetch_http_archive_adoption_monthly(args.skip_network)
    fetched["http_archive_tracked_share_monthly"] = derive_http_archive_tracked_share_monthly(
        fetched["http_archive_adoption_monthly"]
    )
    fetched["http_archive_rank_adoption_snapshot"] = fetch_http_archive_rank_adoption_snapshot(args.skip_network)
    fetched["http_archive_cwv_monthly"] = fetch_http_archive_cwv_monthly(args.skip_network)
    fetched["wporg_ecosystem_stats_snapshot"] = fetch_wporg_ecosystem_stats_snapshot(args.skip_network)
    fetched["builtwith_technology_snapshots"], fetched["builtwith_technology_history"] = fetch_builtwith_technology_signals(
        args.skip_network
    )
    fetched["stack_overflow_tag_quarterly"] = fetch_stackoverflow_tag_quarterly(args.skip_network)
    fetched["wikimedia_pageviews_monthly"], fetched["wikimedia_pageviews_quarterly"] = fetch_wikimedia_pageviews(
        args.skip_network
    )
    fetched["hn_hiring_wordpress_quarterly"] = fetch_hn_hiring_wordpress_quarterly(args.skip_network)
    (
        fetched["wordpress_jobs_board_snapshots"],
        fetched["wordpress_jobs_board_category_snapshots"],
    ) = fetch_wordpress_jobs_board_snapshots(args.skip_network)
    fetched["enterprise_vip_case_studies"] = fetch_wordpress_vip_case_studies(args.skip_network)
    fetched["directory_snapshots"] = fetch_wordpress_directory_snapshots(args.skip_network)
    (
        fetched["directory_activity_snapshots"],
        fetched["plugin_directory_activity_sample"],
        fetched["theme_directory_activity_sample"],
    ) = fetch_directory_activity(args.skip_network)
    fetched["major_plugin_install_snapshot"] = fetch_major_plugin_install_snapshot(args.skip_network)
    fetched["major_plugin_install_history"] = fetch_major_plugin_install_history(
        fetched["major_plugin_install_snapshot"], args.skip_network
    )
    (
        fetched["major_plugin_download_daily"],
        fetched["major_plugin_download_quarterly"],
    ) = fetch_major_plugin_download_history(fetched["major_plugin_install_snapshot"], args.skip_network)
    fetched["wordcamps"] = fetch_wordcamps(args.skip_network)
    fetched["wordcamp_yearly"] = derive_wordcamp_yearly(fetched["wordcamps"])
    fetched["wp_event_snapshots"], fetched["wp_events"] = fetch_wordpress_events(args.skip_network)
    (
        fetched["translation_snapshots"],
        fetched["translation_locale_snapshot"],
        fetched["translation_core_dev_status"],
    ) = fetch_translation_snapshots(args.skip_network)
    fetched["make_core_posts"] = fetch_make_core_posts(args.skip_network)
    fetched["make_core_comments"] = fetch_make_core_comments(args.skip_network)
    fetched["make_core_comment_quarterly"] = derive_make_core_comment_quarterly(fetched["make_core_comments"])
    fetched["make_core_dev_note_tags"] = fetch_make_core_dev_note_tags(args.skip_network)
    (
        fetched["make_core_dev_notes"],
        fetched["make_core_dev_note_quarterly"],
        fetched["make_core_dev_note_releases"],
    ) = derive_make_core_dev_notes(fetched["make_core_posts"], fetched["make_core_dev_note_tags"])
    fetched["fttf_snapshots"], fetched["fttf_pledges"], fetched["fttf_contributors"] = fetch_five_for_the_future_pledges(
        args.skip_network
    )
    fetched["core_releases"], fetched["core_release_credits"] = fetch_core_release_credits(args.skip_network)
    fetched["core_release_committers"], fetched["core_release_committer_counts"] = fetch_core_release_committers(
        fetched["core_releases"], args.skip_network
    )
    if args.skip_network:
        apply_skip_network_db_fallback(fetched)
    fetched["new_site_choice_summary"] = derive_new_site_choice_summary(
        data.get("builtwith_new_site_snapshot", []),
        fetched.get("http_archive_tracked_share_monthly", []),
        fetched.get("builtwith_tier_share_snapshot", []),
    )
    (
        fetched["plugin_maintenance_summary"],
        fetched["plugin_stale_popular_sample"],
    ) = derive_plugin_maintenance_tables(fetched.get("plugin_directory_activity_sample", []))
    fetched["hn_hiring_demand_summary"] = derive_hn_hiring_demand_summary(
        fetched.get("hn_hiring_wordpress_quarterly", [])
    )
    fetched["attention_demand_summary"] = derive_attention_demand_summary(
        fetched.get("stack_overflow_tag_quarterly", []),
        fetched.get("wikimedia_pageviews_quarterly", []),
        fetched.get("hn_hiring_demand_summary", []),
        fetched.get("wordpress_jobs_board_snapshots", []),
    )

    build_database(data, fetched)
    build_report(data, fetched)
    eprint(f"wrote {DB_PATH}")
    eprint(f"wrote {OUT}")


if __name__ == "__main__":
    main()
