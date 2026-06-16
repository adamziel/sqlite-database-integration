#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/homebrew/bin:${PATH}"

if ! command -v php >/dev/null 2>&1; then
	echo "php was not found. Install PHP or add it to PATH." >&2
	exit 1
fi

if ! php -r 'new PDO("sqlite::memory:");' >/dev/null 2>&1; then
	echo "php is available, but the pdo_sqlite extension is not loaded." >&2
	exit 1
fi

if ! command -v sqlancer >/dev/null 2>&1; then
	if [[ "${SQLANCER_BOOTSTRAP_INSTALL:-0}" == "1" ]] && command -v brew >/dev/null 2>&1; then
		brew install sqlancer
	else
		echo "sqlancer was not found." >&2
		echo "Install it with Homebrew, or rerun with SQLANCER_BOOTSTRAP_INSTALL=1 if brew is available:" >&2
		echo "  brew install sqlancer" >&2
		exit 1
	fi
fi

sqlancer_help="$(sqlancer --help 2>&1 || true)"
if [[ "${sqlancer_help}" != *"Usage: SQLancer"* ]]; then
	echo "sqlancer is installed but did not run successfully." >&2
	exit 1
fi

echo "SQLancer prerequisites are available."
echo "php: $(command -v php)"
echo "sqlancer: $(command -v sqlancer)"
