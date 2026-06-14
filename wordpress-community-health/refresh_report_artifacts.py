#!/usr/bin/env python3
import argparse
import re
import shutil
import sqlite3
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"

HTML_ARTIFACTS = {
    "final_report.html": [
        "Decision Questions",
        "Goal Coverage Map",
        "Source Coverage",
        "Decision Readout",
    ],
    "goal_audit.html": [
        "Requirement Coverage",
        "Partial Signals Stored In SQLite",
    ],
    "data_inventory.html": [
        "WordPress report data inventory",
        "Goal audit",
        "Partial-source gaps stored in SQLite",
    ],
    "source_gap_plan.html": [
        "WordPress report source gap plan",
        "Collection order",
        "new_site_cohort_quarterly",
    ],
    "contributor_depth.html": [
        "WordPress contributor depth",
        "Depth ladders since 2024",
        "Core Trac reporters",
    ],
    "ecosystem_activity.html": [
        "WordPress ecosystem activity",
        "Activity lanes",
        "Make/Core discussion",
    ],
    "market_position.html": [
        "WordPress market position",
        "Decision lanes",
        "Current new-site proxy",
    ],
    "new_site_choice.html": [
        "WordPress new-site choice",
        "Recurring tracked share over time",
        "BuiltWith 90-day newly found sites",
    ],
    "developer_interest.html": [
        "WordPress developer interest",
        "Developer-help questions",
        "Package ecosystem activity",
        "GitHub code-review activity",
    ],
    "job_demand.html": [
        "WordPress job demand",
        "HN hiring mention rates",
        "WordPress Jobs board snapshots",
    ],
    "search_interest.html": [
        "WordPress search interest",
        "Public attention proxy",
        "Latest Wikimedia peer comparison",
    ],
    "support_load.html": [
        "WordPress support load",
        "Support queue by last activity month",
        "Major-plugin support load",
    ],
    "project_load.html": [
        "WordPress project load",
        "Open backlog age",
        "Open backlog by category",
    ],
    "decision_brief.html": [
        "Decision Questions",
        "WordPress is still the default CMS",
    ],
    "progress_summary.html": [
        "WordPress relevance report progress",
        "Goal audit",
    ],
    "refresh_runbook.html": [
        "Refresh runbook",
        "python3 refresh_report_artifacts.py",
    ],
}

LOCAL_PAGE_ALIASES = {
    "index.html": "final_report.html",
}


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)
        if "id" in attr_map:
            self.ids.add(attr_map["id"])
        if tag == "a" and "href" in attr_map:
            self.hrefs.append(attr_map["href"])


def free_mb(path):
    usage = shutil.disk_usage(path)
    return usage.free / 1024 / 1024


def integrity_check():
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()


def run_step(args):
    printable = " ".join(args)
    print(f"running: {printable}", flush=True)
    subprocess.run(args, cwd=ROOT, check=True)


def validate_html_artifact(path, required_strings):
    if not path.exists():
        print(f"missing HTML artifact: {path}", file=sys.stderr)
        return False
    text = path.read_text(encoding="utf-8")
    parser = LinkParser()
    parser.feed(text)
    missing = [needle for needle in required_strings if needle not in text]
    if missing:
        print(f"{path.name} missing required text: {', '.join(missing)}", file=sys.stderr)
        return False
    if "file://" in text:
        print(f"{path.name} contains a local file:// link", file=sys.stderr)
        return False
    if re.search(r"\brisk\b", text, flags=re.I):
        print(f"{path.name} contains avoided wording: risk", file=sys.stderr)
        return False
    if not validate_local_links(path, parser.hrefs):
        return False
    return True


def resolve_local_target(current_path, href):
    parsed = urlparse(href)
    if parsed.scheme or parsed.netloc:
        return None, parsed.fragment
    if href.startswith("#"):
        return current_path, unquote(parsed.fragment)
    target = unquote(parsed.path)
    if not target:
        return current_path, unquote(parsed.fragment)
    target = LOCAL_PAGE_ALIASES.get(target, target)
    return ROOT / target, unquote(parsed.fragment)


def html_ids(path):
    parser = LinkParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.ids


def validate_local_links(path, hrefs):
    ok = True
    id_cache = {}
    for href in hrefs:
        target, fragment = resolve_local_target(path, href)
        if target is None:
            continue
        if not target.exists():
            print(f"{path.name} links to missing local target: {href}", file=sys.stderr)
            ok = False
            continue
        if fragment and target.suffix == ".html":
            if target not in id_cache:
                id_cache[target] = html_ids(target)
            if fragment not in id_cache[target]:
                print(f"{path.name} links to missing fragment {href}", file=sys.stderr)
                ok = False
    return ok


def validate_artifacts():
    ok = True
    for name, required in HTML_ARTIFACTS.items():
        ok = validate_html_artifact(ROOT / name, required) and ok
    print(f"artifact validation: {'ok' if ok else 'failed'}", flush=True)
    return ok


def main():
    parser = argparse.ArgumentParser(description="Rebuild WordPress report HTML artifacts in dependency order.")
    parser.add_argument(
        "--with-network",
        action="store_true",
        help="Allow make_community_health_report.py to refresh public network sources. Default uses --skip-network.",
    )
    parser.add_argument(
        "--skip-main-report",
        action="store_true",
        help="Only rebuild companion generated artifacts from the existing SQLite database.",
    )
    parser.add_argument(
        "--min-free-mb",
        type=int,
        default=500,
        help="Minimum free disk space required before running. Default: 500.",
    )
    parser.add_argument(
        "--allow-low-disk",
        action="store_true",
        help="Run even when free disk is below --min-free-mb.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the existing SQLite database and HTML artifacts without rebuilding them.",
    )
    ns = parser.parse_args()

    current_free = free_mb(ROOT)
    print(f"free disk: {current_free:.0f} MB", flush=True)
    if current_free < ns.min_free_mb and not ns.allow_low_disk:
        print(
            f"free disk is below {ns.min_free_mb} MB; free space or rerun with --allow-low-disk for an HTML-only validation pass",
            file=sys.stderr,
        )
        return 2

    if not DB_PATH.exists():
        print(f"missing database: {DB_PATH}", file=sys.stderr)
        return 2

    before = integrity_check()
    print(f"sqlite integrity before: {before}", flush=True)
    if before != "ok":
        return 2

    if not ns.validate_only and not ns.skip_main_report:
        report_cmd = [sys.executable, "make_community_health_report.py"]
        if not ns.with_network:
            report_cmd.append("--skip-network")
        run_step(report_cmd)

    if not ns.validate_only:
        run_step([sys.executable, "make_goal_audit.py"])
        run_step([sys.executable, "make_project_load_report.py"])
        run_step([sys.executable, "make_contributor_depth_report.py"])
        run_step([sys.executable, "make_ecosystem_activity_report.py"])
        run_step([sys.executable, "make_market_position_report.py"])
        run_step([sys.executable, "make_new_site_choice_report.py"])
        run_step([sys.executable, "make_developer_interest_report.py"])
        run_step([sys.executable, "make_job_demand_report.py"])
        run_step([sys.executable, "make_search_interest_report.py"])
        run_step([sys.executable, "make_support_load_report.py"])
        run_step([sys.executable, "make_source_gap_plan.py"])
        run_step([sys.executable, "make_data_inventory.py"])

    after = integrity_check()
    print(f"sqlite integrity after: {after}", flush=True)
    if after != "ok":
        return 2
    return 0 if validate_artifacts() else 2


if __name__ == "__main__":
    raise SystemExit(main())
