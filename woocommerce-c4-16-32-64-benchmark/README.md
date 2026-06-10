# WooCommerce 5GB SQLite Benchmark: MariaDB vs SQLite rc3 vs stable control

Merged report combining the supplemental 4-concurrent-request run with the existing 16/32/64 matrix.

## Files

- `comparison-readable.html`: explanatory report with tables.
- `comparison-visual.html`: visual report; SVG chart files are included in this gist.
- `aggregate.csv`: median aggregate metrics by variant/workload/concurrency.
- `results.csv`: per-repetition measured results.
- `manifest.json`: benchmark manifest and source metadata.

## Matrix

- Variants: `mariadb-innodb-baseline, sqlite-driver-3.0.0-rc.3, sqlite-plugin-2.2.23-control`
- Workloads: `read-heavy, balanced, write-heavy`
- Concurrent requests: `4, 16, 32, 64`
- Repetitions per cell: `3`
- Fixture: `woocommerce-5gb`

## Integrity Totals

| Variant | Failed flows | SQLite lock/busy events |
| --- | ---: | ---: |
| `mariadb-innodb-baseline` | 0 | 0 |
| `sqlite-driver-3.0.0-rc.3` | 0 | 0 |
| `sqlite-plugin-2.2.23-control` | 361 | 3438 |

Generated from local benchmark artifacts on 2026-06-10.
