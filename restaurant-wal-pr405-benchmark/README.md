# Restaurant Site SQLite WAL PR #405 Benchmark

This directory contains the small restaurant-site request-load benchmark for MariaDB/InnoDB vs SQLite Database Integration PR #405.

- SQLite source: `WordPress/sqlite-database-integration` PR #405, commit `02a14006d0c584742371d4e9dc5f532bbeb06da5`.
- Fixture: 10 pages, 6 posts, 36 comments, 4 users, 8 seed reservation requests.
- Workloads: read-heavy, balanced, write-heavy.
- Concurrent requests: 4, 16, 32, 64.
- Repetitions: 3 per matrix cell.
- Measured duration: 20 seconds per cell after a 5 second warm-up.

Primary report: `comparison-visual.html`.

