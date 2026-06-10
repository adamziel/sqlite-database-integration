# WooCommerce 5GB SQLite Benchmark: PR #378 assessment

Merged PR assessment adding SQLite PR #378 to the existing MariaDB, rc3, and stable-control matrix.

## Files

- `comparison-readable.html`: explanatory report with tables.
- `comparison-visual.html`: visual report; SVG chart files are included in this gist.
- `aggregate.csv`: median aggregate metrics by variant/workload/concurrency.
- `results.csv`: per-repetition measured results.
- `manifest.json`: benchmark manifest and source metadata.

## Matrix

- Variants: `mariadb-innodb-baseline, sqlite-driver-3.0.0-rc.3, sqlite-driver-pr-378-performance, sqlite-plugin-2.2.23-control`
- Workloads: `read-heavy, balanced, write-heavy`
- Concurrent requests: `4, 16, 32, 64`
- Repetitions per cell: `3`
- Fixture: `woocommerce-5gb`

## Integrity Totals

| Variant | Failed flows | SQLite lock/busy events |
| --- | ---: | ---: |
| `mariadb-innodb-baseline` | 0 | 0 |
| `sqlite-driver-3.0.0-rc.3` | 0 | 0 |
| `sqlite-driver-pr-378-performance` | 0 | 0 |
| `sqlite-plugin-2.2.23-control` | 361 | 3438 |

Generated from local benchmark artifacts on 2026-06-10.
