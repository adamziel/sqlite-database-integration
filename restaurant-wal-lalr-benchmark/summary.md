# Local Production-Methodology Small Restaurant Benchmark

Scope: macOS system-under-test using local nginx, PHP-FPM, WordPress, and MySQL 8.4 InnoDB/SQLite. This is a small-site diagnostic matching the previous WooCommerce methodology as closely as practical.

Fixture profile: `restaurant-small` {'pages': 10, 'posts': 6, 'comments': 36, 'users': 4, 'reservation_seed_rows': 8}. Warm-up: `5.0s`; measured duration: `20.0s`; repetitions: `3`; concurrency: `[4, 16, 32, 64]`.
Resource sampling interval: `1.0s`; CPU is process-group `%CPU` sampled from macOS `ps`, normalized to approximate core-seconds per 1k successful flows. Disk activity is sampled from macOS `iostat`; RSS is process-group resident memory.

WordPress `7.0`, PHP 8.5.7 (cli) (built: Jun  2 2026 20:59:56) (NTS), PHP 8.5.7 (fpm-fcgi) (built: Jun  2 2026 20:59:56) (NTS), nginx version: nginx/1.31.1, /opt/homebrew/opt/mysql@8.4/bin/mysql  Ver 8.4.9 for macos26.4 on arm64 (Homebrew).

| Variant | Workload | Concurrent requests | Reps | Median flows/s | Median avg request ms | Median p95 ms | Median write/s | Failed flows | Verify failures | SQLite lock errors | Max WAL bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mariadb-innodb-baseline | balanced | 4 | 3 | 102.55 | 25.36 | 96.61 | 20.91 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | balanced | 16 | 3 | 95.57 | 105.44 | 523.35 | 19.37 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | balanced | 32 | 3 | 95.26 | 202.06 | 1,061.68 | 19.04 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | balanced | 64 | 3 | 100.03 | 396.50 | 1,737.06 | 21.37 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 4 | 3 | 97.42 | 25.62 | 94.02 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 16 | 3 | 90.62 | 104.50 | 515.84 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 32 | 3 | 98.09 | 204.50 | 919.75 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 64 | 3 | 93.76 | 407.79 | 1,932.67 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 4 | 3 | 106.20 | 26.60 | 98.02 | 31.61 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 16 | 3 | 101.01 | 113.85 | 501.18 | 29.61 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 32 | 3 | 101.73 | 225.97 | 997.57 | 30.90 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 64 | 3 | 98.61 | 475.23 | 1,784.23 | 29.86 | 0 | 0 | 0 | 0 |
| sqlite-wal-pr405-lalr-wired | balanced | 4 | 3 | 11.00 | 221.86 | 1,959.16 | 2.70 | 0 | 0 | 0 | 4152992 |
| sqlite-wal-pr405-lalr-wired | balanced | 16 | 3 | 35.68 | 258.89 | 1,978.11 | 7.95 | 0 | 0 | 0 | 4148872 |
| sqlite-wal-pr405-lalr-wired | balanced | 32 | 3 | 59.47 | 309.32 | 2,044.88 | 12.32 | 0 | 0 | 0 | 4255992 |
| sqlite-wal-pr405-lalr-wired | balanced | 64 | 3 | 66.71 | 549.25 | 2,591.44 | 13.78 | 0 | 0 | 0 | 4602072 |
| sqlite-wal-pr405-lalr-wired | read-heavy | 4 | 3 | 16.32 | 144.24 | 1,926.05 | 0.00 | 0 | 0 | 0 | 123632 |
| sqlite-wal-pr405-lalr-wired | read-heavy | 16 | 3 | 60.99 | 148.06 | 1,937.09 | 0.00 | 0 | 0 | 0 | 70072 |
| sqlite-wal-pr405-lalr-wired | read-heavy | 32 | 3 | 70.94 | 268.16 | 1,998.89 | 0.00 | 0 | 0 | 0 | 74192 |
| sqlite-wal-pr405-lalr-wired | read-heavy | 64 | 3 | 70.60 | 519.27 | 2,397.54 | 0.00 | 0 | 0 | 0 | 65952 |
| sqlite-wal-pr405-lalr-wired | write-heavy | 4 | 3 | 5.86 | 473.63 | 1,984.35 | 1.63 | 0 | 0 | 0 | 2426712 |
| sqlite-wal-pr405-lalr-wired | write-heavy | 16 | 3 | 25.47 | 432.35 | 2,006.26 | 7.27 | 0 | 0 | 0 | 4173592 |
| sqlite-wal-pr405-lalr-wired | write-heavy | 32 | 3 | 50.63 | 421.55 | 2,041.41 | 15.67 | 0 | 0 | 0 | 4293072 |
| sqlite-wal-pr405-lalr-wired | write-heavy | 64 | 3 | 58.30 | 680.43 | 2,651.25 | 17.45 | 0 | 0 | 0 | 4523792 |

## Server Load Summary

| Variant | Workload | Concurrent requests | CPU core-s / 1k flows | Peak process CPU % | Peak total RSS | Peak PHP-FPM RSS | Peak DB RSS | Peak disk MB/sample | Median loopback bytes/s |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mariadb-innodb-baseline | balanced | 4 | 33.658 | 360.50 | 1.04 GiB | 657.97 MiB | 393.56 MiB | 26.52 | 97,984,831 |
| mariadb-innodb-baseline | balanced | 16 | 35.023 | 355.90 | 1.45 GiB | 1.05 GiB | 397.89 MiB | 18.99 | 85,427,764 |
| mariadb-innodb-baseline | balanced | 32 | 34.650 | 351.00 | 2.13 GiB | 1.71 GiB | 400.53 MiB | 14.59 | 85,828,003 |
| mariadb-innodb-baseline | balanced | 64 | 34.698 | 348.30 | 3.65 GiB | 3.26 GiB | 403.17 MiB | 14.47 | 84,026,391 |
| mariadb-innodb-baseline | read-heavy | 4 | 35.194 | 365.60 | 1.03 GiB | 643.89 MiB | 383.00 MiB | 24.73 | 71,917,310 |
| mariadb-innodb-baseline | read-heavy | 16 | 36.397 | 359.10 | 1.40 GiB | 1.02 GiB | 383.69 MiB | 16.00 | 70,036,363 |
| mariadb-innodb-baseline | read-heavy | 32 | 33.862 | 353.20 | 2.05 GiB | 1.65 GiB | 386.48 MiB | 10.59 | 72,551,516 |
| mariadb-innodb-baseline | read-heavy | 64 | 35.922 | 345.50 | 3.60 GiB | 3.25 GiB | 390.62 MiB | 16.88 | 71,414,811 |
| mariadb-innodb-baseline | write-heavy | 4 | 32.389 | 352.60 | 1.05 GiB | 668.55 MiB | 386.09 MiB | 31.57 | 128,713,028 |
| mariadb-innodb-baseline | write-heavy | 16 | 34.351 | 355.20 | 1.43 GiB | 1.07 GiB | 391.81 MiB | 79.29 | 130,130,807 |
| mariadb-innodb-baseline | write-heavy | 32 | 33.478 | 350.10 | 2.18 GiB | 1.80 GiB | 397.44 MiB | 24.43 | 122,279,682 |
| mariadb-innodb-baseline | write-heavy | 64 | 32.595 | 341.00 | 3.42 GiB | 3.04 GiB | 401.27 MiB | 19.92 | 115,128,677 |
| sqlite-wal-pr405-lalr-wired | balanced | 4 | 21.618 | 89.10 | 1.12 GiB | 879.38 MiB | 260.30 MiB | 23.94 | 3,514,871 |
| sqlite-wal-pr405-lalr-wired | balanced | 16 | 33.200 | 254.00 | 1.64 GiB | 1.37 GiB | 260.30 MiB | 40.73 | 15,056,047 |
| sqlite-wal-pr405-lalr-wired | balanced | 32 | 45.095 | 353.20 | 2.55 GiB | 2.32 GiB | 260.30 MiB | 17.44 | 25,894,663 |
| sqlite-wal-pr405-lalr-wired | balanced | 64 | 44.202 | 358.50 | 4.38 GiB | 4.10 GiB | 260.30 MiB | 15.85 | 27,532,828 |
| sqlite-wal-pr405-lalr-wired | read-heavy | 4 | 40.390 | 214.60 | 1.25 GiB | 878.00 MiB | 376.75 MiB | 53.53 | 5,927,281 |
| sqlite-wal-pr405-lalr-wired | read-heavy | 16 | 44.241 | 362.70 | 1.72 GiB | 1.40 GiB | 376.75 MiB | 19.96 | 23,611,763 |
| sqlite-wal-pr405-lalr-wired | read-heavy | 32 | 42.921 | 358.10 | 2.54 GiB | 2.31 GiB | 368.78 MiB | 20.94 | 26,970,959 |
| sqlite-wal-pr405-lalr-wired | read-heavy | 64 | 45.169 | 361.00 | 4.09 GiB | 3.91 GiB | 368.17 MiB | 23.56 | 27,610,606 |
| sqlite-wal-pr405-lalr-wired | write-heavy | 4 | 84.164 | 194.80 | 1.13 GiB | 882.05 MiB | 260.30 MiB | 13.18 | 2,754,673 |
| sqlite-wal-pr405-lalr-wired | write-heavy | 16 | 46.036 | 256.40 | 1.60 GiB | 1.33 GiB | 260.30 MiB | 17.20 | 13,508,188 |
| sqlite-wal-pr405-lalr-wired | write-heavy | 32 | 43.771 | 347.40 | 2.60 GiB | 2.32 GiB | 260.30 MiB | 19.07 | 23,249,769 |
| sqlite-wal-pr405-lalr-wired | write-heavy | 64 | 45.597 | 359.00 | 4.35 GiB | 4.10 GiB | 260.30 MiB | 32.25 | 29,211,669 |
