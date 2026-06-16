#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SQLANCER_DIR="${PACKAGE_DIR}/tests/sqlancer"
WORK_BASE="${SQLANCER_DIR}/.work"

export PATH="/opt/homebrew/bin:${PATH}"

"${SCRIPT_DIR}/sqlancer-bootstrap.sh" >/dev/null

SQLANCER_BIN="${SQLANCER_BIN:-sqlancer}"
SQLANCER_SECONDS="${SQLANCER_SECONDS:-3}"
SQLANCER_SEED="${SQLANCER_SEED:-7}"
SQLANCER_NUM_QUERIES="${SQLANCER_NUM_QUERIES:-20}"
SQLANCER_MAX_INSERTS="${SQLANCER_MAX_INSERTS:-5}"
SQLANCER_ORACLE="${SQLANCER_ORACLE:-FUZZER}"
SQLANCER_REPLAY_LIMIT="${SQLANCER_REPLAY_LIMIT:-75}"

RUN_DIR="${WORK_BASE}/run-$(date -u +%Y%m%dT%H%M%SZ)-seed-${SQLANCER_SEED}"
mkdir -p "${RUN_DIR}"

echo "Running SQLancer SQLite generator for ${SQLANCER_SECONDS}s..."
(
	cd "${RUN_DIR}"
	"${SQLANCER_BIN}" \
		--num-threads 1 \
		--random-seed "${SQLANCER_SEED}" \
		--num-queries "${SQLANCER_NUM_QUERIES}" \
		--max-num-inserts "${SQLANCER_MAX_INSERTS}" \
		--random-string-generation NUMERIC \
		--print-progress-information false \
		--print-progress-summary false \
		sqlite3 \
		--oracle "${SQLANCER_ORACLE}" \
		--test-fts false \
		--test-rtree false \
		--test-functions false \
		--test-foreign-keys false \
		--test-generated-columns false \
		--test-temp-tables false \
		--test-without-rowids false \
		--test-dbstats false \
		--test-match false \
		> sqlancer.out 2>&1 &
	pid=$!
	sleep "${SQLANCER_SECONDS}"
	if kill -0 "${pid}" >/dev/null 2>&1; then
		kill -TERM "${pid}" >/dev/null 2>&1 || true
		for _ in {1..20}; do
			if ! kill -0 "${pid}" >/dev/null 2>&1; then
				break
			fi
			sleep 0.1
		done
		if kill -0 "${pid}" >/dev/null 2>&1; then
			kill -KILL "${pid}" >/dev/null 2>&1 || true
		fi
	fi
	wait "${pid}" >/dev/null 2>&1 || true
)

if ! find "${RUN_DIR}/logs/sqlite3" -type f -name '*-cur.log' -print -quit >/dev/null 2>&1; then
	echo "SQLancer did not produce a SQLite log. Output follows:" >&2
	sed -n '1,160p' "${RUN_DIR}/sqlancer.out" >&2 || true
	exit 1
fi

echo "Replaying bounded SQLancer corpus through WP_SQLite_Driver..."
php "${SCRIPT_DIR}/sqlancer-replay-sqlite.php" \
	--input "${RUN_DIR}/logs/sqlite3" \
	--limit "${SQLANCER_REPLAY_LIMIT}" \
	--capture-dir "${SQLANCER_DIR}/fixtures/generated" \
	--require-min-replayed 2

echo "SQLancer work directory: ${RUN_DIR}"
