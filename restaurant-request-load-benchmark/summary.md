# Local Production-Methodology Small Restaurant Benchmark

Scope: macOS system-under-test using local nginx, PHP-FPM, WordPress, and MariaDB/SQLite. This is a small-site diagnostic matching the previous WooCommerce methodology as closely as practical.

Fixture profile: `restaurant-small` {'pages': 10, 'posts': 6, 'comments': 36, 'users': 4, 'reservation_seed_rows': 8}. Warm-up: `5.0s`; measured duration: `20.0s`; repetitions: `3`; concurrency: `[4, 16, 32, 64]`.

WordPress `7.0`, PHP 8.5.7 (cli) (built: Jun  2 2026 20:59:56) (NTS), PHP 8.5.7 (fpm-fcgi) (built: Jun  2 2026 20:59:56) (NTS), nginx version: nginx/1.31.1, mysql from 12.3.2-MariaDB, client 15.2 for osx10.21 (arm64) using  EditLine wrapper.

| Variant | Workload | Concurrent requests | Reps | Median flows/s | Median avg request ms | Median p95 ms | Median write/s | Failed flows | Verify failures | SQLite lock errors | Max WAL bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mariadb-innodb-baseline | balanced | 4 | 3 | 73.28 | 34.63 | 137.91 | 14.66 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | balanced | 16 | 3 | 100.49 | 100.41 | 599.34 | 20.45 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | balanced | 32 | 3 | 104.00 | 186.56 | 1,231.08 | 20.89 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | balanced | 64 | 3 | 109.91 | 364.40 | 2,195.95 | 23.58 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 4 | 3 | 115.85 | 21.31 | 75.12 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 16 | 3 | 115.40 | 81.63 | 328.01 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 32 | 3 | 115.61 | 171.25 | 677.95 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 64 | 3 | 113.64 | 341.45 | 1,353.10 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 4 | 3 | 67.23 | 42.38 | 145.08 | 19.90 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 16 | 3 | 92.08 | 123.06 | 566.76 | 27.01 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 32 | 3 | 103.48 | 223.07 | 1,110.99 | 31.82 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 64 | 3 | 113.74 | 417.18 | 2,010.77 | 34.49 | 0 | 0 | 0 | 0 |
| sqlite-driver-3.0.0-rc.3 | balanced | 4 | 3 | 95.17 | 27.22 | 100.94 | 19.57 | 0 | 0 | 0 | 4177712 |
| sqlite-driver-3.0.0-rc.3 | balanced | 16 | 3 | 91.83 | 109.87 | 455.35 | 18.53 | 0 | 0 | 0 | 4288952 |
| sqlite-driver-3.0.0-rc.3 | balanced | 32 | 3 | 86.47 | 219.64 | 927.32 | 17.38 | 0 | 0 | 0 | 5442552 |
| sqlite-driver-3.0.0-rc.3 | balanced | 64 | 3 | 93.03 | 426.24 | 1,791.86 | 19.87 | 0 | 0 | 0 | 5805112 |
| sqlite-driver-3.0.0-rc.3 | read-heavy | 4 | 3 | 93.53 | 26.79 | 96.37 | 0.00 | 0 | 0 | 0 | 82432 |
| sqlite-driver-3.0.0-rc.3 | read-heavy | 16 | 3 | 88.98 | 105.52 | 405.85 | 0.00 | 0 | 0 | 0 | 74192 |
| sqlite-driver-3.0.0-rc.3 | read-heavy | 32 | 3 | 92.68 | 213.22 | 769.08 | 0.00 | 0 | 0 | 0 | 78312 |
| sqlite-driver-3.0.0-rc.3 | read-heavy | 64 | 3 | 93.04 | 414.14 | 1,574.93 | 0.00 | 0 | 0 | 0 | 78312 |
| sqlite-driver-3.0.0-rc.3 | write-heavy | 4 | 3 | 95.32 | 29.45 | 104.73 | 28.15 | 0 | 0 | 0 | 4210672 |
| sqlite-driver-3.0.0-rc.3 | write-heavy | 16 | 3 | 90.31 | 124.66 | 510.47 | 26.63 | 0 | 0 | 0 | 4779232 |
| sqlite-driver-3.0.0-rc.3 | write-heavy | 32 | 3 | 95.27 | 240.67 | 965.54 | 29.20 | 0 | 0 | 0 | 9714992 |
| sqlite-driver-3.0.0-rc.3 | write-heavy | 64 | 3 | 97.30 | 476.23 | 1,900.20 | 29.33 | 0 | 0 | 0 | 14778472 |
