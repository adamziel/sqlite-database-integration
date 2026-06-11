# Restaurant Site Concurrent Request Load Benchmark

This directory contains the small restaurant-site request-load benchmark for MariaDB/InnoDB vs SQLite Database Integration `v3.0.0-rc.3`.

- Fixture: 10 pages, 6 posts, 36 comments, 4 users, 8 seed reservation requests.
- Workloads: read-heavy, balanced, write-heavy.
- Concurrent requests: 4, 16, 32, 64.
- Repetitions: 3 per matrix cell.
- Measured duration: 20 seconds per cell after a 5 second warm-up.

Primary report: `comparison-visual.html`.

