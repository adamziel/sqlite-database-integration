# Restaurant WAL + LALR Source Benchmark

Local production-methodology small restaurant benchmark comparing MySQL 8.4 InnoDB with SQLite Database Integration source that combines:

- WAL PR #405: https://github.com/WordPress/sqlite-database-integration/pull/405
- LALR parser PR #429: https://github.com/WordPress/sqlite-database-integration/pull/429

Source refs:

- WAL PR #405 SHA: `02a14006d0c584742371d4e9dc5f532bbeb06da5`
- LALR PR #429 SHA: `2beadb5605bd5a2d4843398f1f3f0e31f6689cb8`
- Combined benchmark branch SHA: `67935c0b6b0f2e8a7ce24eb25f73303dfbde6708`

Important caveats:

- The requested baseline was MariaDB, but local MariaDB 12.3.2 repeatedly crashed during the full matrix with `InnoDB: fsync() returned 5`, so the published complete matrix uses isolated MySQL 8.4.9 InnoDB on port 3307. Do not read this as a MariaDB result.
- PR #429's standalone LALR parser package was present in the combined source branch, but the active WordPress SQLite driver path still appeared to load the existing driver parser entrypoint. Treat this as a benchmark of the combined source branch, not proof that request-time SQL parsing used the standalone LALR package.

Validation summary:

- 72 raw result rows
- 24 aggregate rows
- 134,835 successful measured flows
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
