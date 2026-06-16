# SQLancer SQLite Replay

This directory contains the SQLite-only SQLancer workflow for the
`mysql-on-sqlite` package. SQLancer's SQLite provider speaks directly to SQLite
through JDBC; the smoke loop therefore uses SQLancer as the generator, then
replays a conservative, MySQL-on-SQLite-compatible slice through
`WP_SQLite_Driver`.

## Prerequisites

The scripts prefer the Homebrew SQLancer install:

```sh
export PATH="/opt/homebrew/bin:$PATH"
packages/mysql-on-sqlite/tests/tools/sqlancer-bootstrap.sh
```

If SQLancer is missing and Homebrew is available:

```sh
SQLANCER_BOOTSTRAP_INSTALL=1 packages/mysql-on-sqlite/tests/tools/sqlancer-bootstrap.sh
```

The bootstrap check also requires PHP with `pdo_sqlite`.

## Smoke Loop

Run the bounded SQLite-backend loop from the repository root:

```sh
export PATH="/opt/homebrew/bin:$PATH"
packages/mysql-on-sqlite/tests/tools/sqlancer-run-sqlite-smoke.sh
```

Useful knobs:

```sh
SQLANCER_SECONDS=5 SQLANCER_SEED=123 SQLANCER_REPLAY_LIMIT=100 \
	 packages/mysql-on-sqlite/tests/tools/sqlancer-run-sqlite-smoke.sh
```

The runner writes transient SQLancer output under `tests/sqlancer/.work/`,
parses `logs/sqlite3/*-cur.log`, filters unsupported SQLite-only constructs,
and replays accepted statements through `WP_SQLite_Driver`.

## Regression Capture

If replaying an accepted generated statement fails unexpectedly, the replay
tool exits non-zero and writes a minimized `.sql` fixture plus `.json` metadata
under:

```text
packages/mysql-on-sqlite/tests/sqlancer/fixtures/generated/
```

Review those files and commit them when the failure should become a regression
test.

Replay committed fixtures:

```sh
export PATH="/opt/homebrew/bin:$PATH"
php packages/mysql-on-sqlite/tests/tools/sqlancer-replay-sqlite.php --fixtures
```

Replay a specific SQLancer log or log directory:

```sh
php packages/mysql-on-sqlite/tests/tools/sqlancer-replay-sqlite.php \
	--input packages/mysql-on-sqlite/tests/sqlancer/.work/<run>/logs/sqlite3 \
	--capture-dir packages/mysql-on-sqlite/tests/sqlancer/fixtures/generated
```
