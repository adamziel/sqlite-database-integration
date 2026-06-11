# Local Production-Methodology Small Restaurant Benchmark

Scope: macOS system-under-test using local nginx, PHP-FPM, WordPress, and MariaDB/SQLite. This is a small-site diagnostic matching the previous WooCommerce methodology as closely as practical.

Fixture profile: `restaurant-small` {'pages': 10, 'posts': 6, 'comments': 36, 'users': 4, 'reservation_seed_rows': 8}. Warm-up: `5.0s`; measured duration: `20.0s`; repetitions: `3`; concurrency: `[4, 16, 32, 64]`.
Resource sampling interval: `1.0s`; CPU is process-group `%CPU` sampled from macOS `ps`, normalized to approximate core-seconds per 1k successful flows. Disk activity is sampled from macOS `iostat`; RSS is process-group resident memory.

WordPress `7.0`, PHP 8.5.7 (cli) (built: Jun  2 2026 20:59:56) (NTS), PHP 8.5.7 (fpm-fcgi) (built: Jun  2 2026 20:59:56) (NTS), nginx version: nginx/1.31.1, mysql from 12.3.2-MariaDB, client 15.2 for osx10.21 (arm64) using  EditLine wrapper.

| Variant | Workload | Concurrent requests | Reps | Median flows/s | Median avg request ms | Median p95 ms | Median write/s | Failed flows | Verify failures | SQLite lock errors | Max WAL bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mariadb-innodb-baseline | balanced | 4 | 3 | 76.18 | 33.34 | 130.91 | 15.55 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | balanced | 16 | 3 | 103.94 | 97.56 | 548.67 | 21.01 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | balanced | 32 | 3 | 105.26 | 182.88 | 1,162.15 | 20.98 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | balanced | 64 | 3 | 109.55 | 363.14 | 2,170.55 | 23.63 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 4 | 3 | 120.50 | 20.22 | 72.14 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 16 | 3 | 119.87 | 79.24 | 322.34 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 32 | 3 | 119.55 | 165.86 | 668.02 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 64 | 3 | 106.94 | 361.76 | 1,424.22 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 4 | 3 | 64.55 | 44.09 | 143.51 | 18.94 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 16 | 3 | 94.30 | 120.51 | 567.17 | 28.06 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 32 | 3 | 106.12 | 216.75 | 1,065.14 | 33.02 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 64 | 3 | 118.70 | 402.84 | 1,880.78 | 36.52 | 0 | 0 | 0 | 0 |
| sqlite-wal-pr405 | balanced | 4 | 3 | 98.26 | 26.48 | 98.53 | 19.89 | 0 | 0 | 0 | 4148872 |
| sqlite-wal-pr405 | balanced | 16 | 3 | 98.98 | 102.12 | 412.42 | 19.93 | 0 | 0 | 0 | 4466112 |
| sqlite-wal-pr405 | balanced | 32 | 3 | 93.32 | 205.51 | 814.48 | 18.63 | 0 | 0 | 0 | 5224192 |
| sqlite-wal-pr405 | balanced | 64 | 3 | 99.37 | 400.18 | 1,582.94 | 21.13 | 0 | 0 | 0 | 6052312 |
| sqlite-wal-pr405 | read-heavy | 4 | 3 | 100.09 | 24.93 | 89.13 | 0.00 | 0 | 0 | 0 | 82432 |
| sqlite-wal-pr405 | read-heavy | 16 | 3 | 95.81 | 97.82 | 375.21 | 0.00 | 0 | 0 | 0 | 74192 |
| sqlite-wal-pr405 | read-heavy | 32 | 3 | 96.96 | 202.52 | 731.04 | 0.00 | 0 | 0 | 0 | 78312 |
| sqlite-wal-pr405 | read-heavy | 64 | 3 | 94.83 | 404.23 | 1,482.05 | 0.00 | 0 | 0 | 0 | 86552 |
| sqlite-wal-pr405 | write-heavy | 4 | 3 | 102.92 | 27.45 | 98.75 | 30.31 | 0 | 0 | 0 | 4264232 |
| sqlite-wal-pr405 | write-heavy | 16 | 3 | 102.77 | 110.76 | 441.66 | 29.84 | 0 | 0 | 0 | 4997592 |
| sqlite-wal-pr405 | write-heavy | 32 | 3 | 101.52 | 228.32 | 847.75 | 31.36 | 0 | 0 | 0 | 6373672 |
| sqlite-wal-pr405 | write-heavy | 64 | 3 | 104.63 | 443.85 | 1,650.42 | 31.31 | 0 | 0 | 0 | 18581232 |

## Server Load Summary

| Variant | Workload | Concurrent requests | CPU core-s / 1k flows | Peak process CPU % | Peak total RSS | Peak PHP-FPM RSS | Peak DB RSS | Peak disk MB/sample | Median loopback bytes/s |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mariadb-innodb-baseline | balanced | 4 | 27.332 | 262.00 | 813.78 MiB | 646.05 MiB | 151.41 MiB | 15.39 | 33,241,155 |
| mariadb-innodb-baseline | balanced | 16 | 28.578 | 359.60 | 1.10 GiB | 956.00 MiB | 151.45 MiB | 16.00 | 43,840,853 |
| mariadb-innodb-baseline | balanced | 32 | 27.536 | 366.90 | 1.70 GiB | 1.52 GiB | 151.53 MiB | 25.75 | 46,327,317 |
| mariadb-innodb-baseline | balanced | 64 | 28.058 | 365.30 | 2.85 GiB | 2.68 GiB | 151.89 MiB | 19.75 | 45,249,653 |
| mariadb-innodb-baseline | read-heavy | 4 | 28.524 | 364.90 | 816.08 MiB | 644.03 MiB | 151.19 MiB | 14.14 | 46,259,785 |
| mariadb-innodb-baseline | read-heavy | 16 | 31.027 | 384.60 | 1.09 GiB | 941.28 MiB | 151.19 MiB | 9.52 | 46,477,300 |
| mariadb-innodb-baseline | read-heavy | 32 | 30.152 | 376.90 | 1.67 GiB | 1.50 GiB | 151.20 MiB | 12.81 | 46,046,509 |
| mariadb-innodb-baseline | read-heavy | 64 | 30.663 | 369.60 | 2.80 GiB | 2.64 GiB | 151.23 MiB | 47.39 | 42,109,055 |
| mariadb-innodb-baseline | write-heavy | 4 | 26.158 | 257.80 | 821.17 MiB | 653.36 MiB | 151.91 MiB | 22.88 | 30,240,681 |
| mariadb-innodb-baseline | write-heavy | 16 | 26.482 | 306.90 | 1.11 GiB | 963.28 MiB | 151.92 MiB | 26.21 | 45,215,136 |
| mariadb-innodb-baseline | write-heavy | 32 | 25.784 | 331.10 | 1.71 GiB | 1.54 GiB | 152.03 MiB | 16.77 | 50,794,282 |
| mariadb-innodb-baseline | write-heavy | 64 | 24.220 | 349.00 | 2.89 GiB | 2.72 GiB | 152.41 MiB | 13.08 | 58,434,187 |
| sqlite-wal-pr405 | balanced | 4 | 39.241 | 389.20 | 941.06 MiB | 769.33 MiB | 148.08 MiB | 10.93 | 43,439,658 |
| sqlite-wal-pr405 | balanced | 16 | 37.739 | 390.10 | 1.40 GiB | 1.24 GiB | 148.08 MiB | 14.95 | 41,386,072 |
| sqlite-wal-pr405 | balanced | 32 | 39.443 | 387.70 | 2.15 GiB | 1.99 GiB | 148.08 MiB | 9.58 | 40,387,574 |
| sqlite-wal-pr405 | balanced | 64 | 38.111 | 391.10 | 3.53 GiB | 3.37 GiB | 148.08 MiB | 11.44 | 41,763,330 |
| sqlite-wal-pr405 | read-heavy | 4 | 37.451 | 391.20 | 907.52 MiB | 732.12 MiB | 152.47 MiB | 9.70 | 38,119,946 |
| sqlite-wal-pr405 | read-heavy | 16 | 38.735 | 390.70 | 1.34 GiB | 1.16 GiB | 152.38 MiB | 10.04 | 37,323,731 |
| sqlite-wal-pr405 | read-heavy | 32 | 39.032 | 389.20 | 1.99 GiB | 1.82 GiB | 152.25 MiB | 7.64 | 37,278,994 |
| sqlite-wal-pr405 | read-heavy | 64 | 41.593 | 386.00 | 3.35 GiB | 3.19 GiB | 152.25 MiB | 8.76 | 36,723,666 |
| sqlite-wal-pr405 | write-heavy | 4 | 36.722 | 389.30 | 960.81 MiB | 790.14 MiB | 147.81 MiB | 16.41 | 48,588,740 |
| sqlite-wal-pr405 | write-heavy | 16 | 37.415 | 391.40 | 1.44 GiB | 1.28 GiB | 147.81 MiB | 18.30 | 50,602,318 |
| sqlite-wal-pr405 | write-heavy | 32 | 36.565 | 391.70 | 2.21 GiB | 2.05 GiB | 142.17 MiB | 26.00 | 49,025,602 |
| sqlite-wal-pr405 | write-heavy | 64 | 37.245 | 385.60 | 3.73 GiB | 3.56 GiB | 142.17 MiB | 14.11 | 51,308,519 |
