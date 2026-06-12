# Restaurant WAL + Wired LALR Benchmark

Local production-methodology small restaurant benchmark comparing MySQL 8.4 InnoDB with SQLite Database Integration source that combines:

- WAL PR #405: https://github.com/WordPress/sqlite-database-integration/pull/405
- LALR parser PR #429: https://github.com/WordPress/sqlite-database-integration/pull/429

Source refs:

- WAL PR #405 SHA: `02a14006d0c584742371d4e9dc5f532bbeb06da5`
- LALR PR #429 SHA: `2beadb5605bd5a2d4843398f1f3f0e31f6689cb8`
- Combined benchmark branch SHA: `94b33a7cc426ce81ad573e561dedbf67d33a3def`
- Local wiring commits:
  - `f2c088a1bf51746d499305e82214d8c8e2db511a` wires the LALR parser adapter into the SQLite driver.
  - `94b33a7cc426ce81ad573e561dedbf67d33a3def` fixes LALR system-variable parsing for WordPress bootstrap queries such as `SELECT @@SESSION.sql_mode`.

Important caveats:

- The requested baseline was MariaDB, but local MariaDB 12.3.2 repeatedly crashed during the full matrix with `InnoDB: fsync() returned 5`, so the published complete matrix uses isolated MySQL 8.4.9 InnoDB on port 3307. Do not read this as a MariaDB result.
- This rerun did wire the LALR parser into the request-time SQLite driver path. The measured SQLite PHP-FPM pools include `env[WP_SQLITE_USE_LALR_PARSER] = 1`.
- WAL mode was verified during setup with `PRAGMA journal_mode=WAL`, which returned `wal`; measured SQLite cells also checkpointed successfully.

Main result:

- With LALR actually wired, SQLite WAL+LALR was slower than MySQL 8.4 InnoDB in every workload/concurrent-request cell.
- SQLite had 0 failed flows, 0 write verification failures, and 0 SQLite busy/locked log events, so the regression is throughput/latency rather than visible request errors.
- The lowest-concurrency write-heavy cell was the worst relative result: SQLite median throughput was 5.86 flows/s vs MySQL 106.20 flows/s, with p95 latency 1.98s vs 98ms.

Validation summary:

- 72 raw result rows
- 24 aggregate rows
- 106,755 successful measured flows
- 0 failed flows
- 0 HTTP failures
- 0 write verification failures
- 0 SQLite busy/locked log events
- 0 fatal or warning PHP log events

Primary report:

- `comparison-visual.html`

Raw artifacts:

- `aggregate.csv`
- `aggregate.json`
- `results.csv`
- `results.json`
- `manifest.json`
- `summary.md`
