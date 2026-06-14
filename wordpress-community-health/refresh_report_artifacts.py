#!/usr/bin/env python3
import argparse
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path("/Users/admin/wordpress_community_health")
DB_PATH = ROOT / "community_health.sqlite"


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

    if not ns.skip_main_report:
        report_cmd = [sys.executable, "make_community_health_report.py"]
        if not ns.with_network:
            report_cmd.append("--skip-network")
        run_step(report_cmd)

    run_step([sys.executable, "make_goal_audit.py"])
    run_step([sys.executable, "make_data_inventory.py"])

    after = integrity_check()
    print(f"sqlite integrity after: {after}", flush=True)
    return 0 if after == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
