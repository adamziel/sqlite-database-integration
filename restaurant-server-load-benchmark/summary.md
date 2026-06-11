# Local Production-Methodology Small Restaurant Benchmark

Scope: macOS system-under-test using local nginx, PHP-FPM, WordPress, and MariaDB/SQLite. This is a small-site diagnostic matching the previous WooCommerce methodology as closely as practical.

Fixture profile: `restaurant-small` {'pages': 10, 'posts': 6, 'comments': 36, 'users': 4, 'reservation_seed_rows': 8}. Warm-up: `5.0s`; measured duration: `20.0s`; repetitions: `3`; concurrency: `[4, 16, 32, 64]`.
Resource sampling interval: `1.0s`; CPU is process-group `%CPU` sampled from macOS `ps`, normalized to approximate core-seconds per 1k successful flows. Disk activity is sampled from macOS `iostat`; RSS is process-group resident memory.

WordPress `7.0`, PHP 8.5.7 (cli) (built: Jun  2 2026 20:59:56) (NTS), PHP 8.5.7 (fpm-fcgi) (built: Jun  2 2026 20:59:56) (NTS), nginx version: nginx/1.31.1, mysql from 12.3.2-MariaDB, client 15.2 for osx10.21 (arm64) using  EditLine wrapper.

| Variant | Workload | Concurrent requests | Reps | Median flows/s | Median avg request ms | Median p95 ms | Median write/s | Failed flows | Verify failures | SQLite lock errors | Max WAL bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mariadb-innodb-baseline | balanced | 4 | 3 | 69.38 | 36.24 | 146.98 | 13.88 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | balanced | 16 | 3 | 102.17 | 99.12 | 574.74 | 20.64 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | balanced | 32 | 3 | 106.17 | 181.06 | 1,223.10 | 21.41 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | balanced | 64 | 3 | 108.04 | 367.26 | 2,135.08 | 23.02 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 4 | 3 | 116.18 | 21.23 | 75.77 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 16 | 3 | 108.78 | 86.81 | 346.34 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 32 | 3 | 113.48 | 174.87 | 696.08 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 64 | 3 | 110.72 | 349.17 | 1,398.85 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 4 | 3 | 65.18 | 43.52 | 145.51 | 19.06 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 16 | 3 | 94.01 | 120.10 | 561.32 | 27.64 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 32 | 3 | 103.53 | 221.12 | 1,091.01 | 32.24 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 64 | 3 | 111.82 | 427.42 | 2,009.65 | 33.96 | 0 | 0 | 0 | 0 |
| sqlite-driver-3.0.0-rc.3 | balanced | 4 | 3 | 96.39 | 26.82 | 100.28 | 19.70 | 0 | 0 | 0 | 4173592 |
| sqlite-driver-3.0.0-rc.3 | balanced | 16 | 3 | 94.87 | 106.72 | 441.60 | 19.23 | 0 | 0 | 0 | 4276592 |
| sqlite-driver-3.0.0-rc.3 | balanced | 32 | 3 | 89.65 | 211.63 | 903.08 | 17.87 | 0 | 0 | 0 | 4911072 |
| sqlite-driver-3.0.0-rc.3 | balanced | 64 | 3 | 91.97 | 434.24 | 1,850.41 | 19.50 | 0 | 0 | 0 | 6233592 |
| sqlite-driver-3.0.0-rc.3 | read-heavy | 4 | 3 | 93.45 | 26.90 | 95.23 | 0.00 | 0 | 0 | 0 | 49472 |
| sqlite-driver-3.0.0-rc.3 | read-heavy | 16 | 3 | 89.43 | 105.38 | 401.88 | 0.00 | 0 | 0 | 0 | 70072 |
| sqlite-driver-3.0.0-rc.3 | read-heavy | 32 | 3 | 92.39 | 214.97 | 777.71 | 0.00 | 0 | 0 | 0 | 82432 |
| sqlite-driver-3.0.0-rc.3 | read-heavy | 64 | 3 | 91.29 | 422.20 | 1,615.65 | 0.00 | 0 | 0 | 0 | 82432 |
| sqlite-driver-3.0.0-rc.3 | write-heavy | 4 | 3 | 96.43 | 29.13 | 106.22 | 28.81 | 0 | 0 | 0 | 4321912 |
| sqlite-driver-3.0.0-rc.3 | write-heavy | 16 | 3 | 95.71 | 118.70 | 490.25 | 27.96 | 0 | 0 | 0 | 5265392 |
| sqlite-driver-3.0.0-rc.3 | write-heavy | 32 | 3 | 99.18 | 233.18 | 915.19 | 30.65 | 0 | 0 | 0 | 6657952 |
| sqlite-driver-3.0.0-rc.3 | write-heavy | 64 | 3 | 94.18 | 488.38 | 1,950.32 | 28.76 | 0 | 0 | 0 | 26883032 |

## Server Load Summary

| Variant | Workload | Concurrent requests | CPU core-s / 1k flows | Peak process CPU % | Peak total RSS | Peak PHP-FPM RSS | Peak DB RSS | Peak disk MB/sample | Median loopback bytes/s |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mariadb-innodb-baseline | balanced | 4 | 31.002 | 318.60 | 817.84 MiB | 646.42 MiB | 149.36 MiB | 11.79 | 30,056,971 |
| mariadb-innodb-baseline | balanced | 16 | 31.099 | 355.00 | 1.10 GiB | 957.14 MiB | 149.47 MiB | 13.66 | 43,255,229 |
| mariadb-innodb-baseline | balanced | 32 | 29.021 | 359.40 | 1.71 GiB | 1.57 GiB | 149.48 MiB | 13.66 | 45,956,276 |
| mariadb-innodb-baseline | balanced | 64 | 29.063 | 357.40 | 2.83 GiB | 2.66 GiB | 150.05 MiB | 23.35 | 44,569,750 |
| mariadb-innodb-baseline | read-heavy | 4 | 29.964 | 366.20 | 812.64 MiB | 643.31 MiB | 149.08 MiB | 13.23 | 44,394,482 |
| mariadb-innodb-baseline | read-heavy | 16 | 32.717 | 372.30 | 1.09 GiB | 942.06 MiB | 149.16 MiB | 29.55 | 42,533,677 |
| mariadb-innodb-baseline | read-heavy | 32 | 30.688 | 367.90 | 1.65 GiB | 1.49 GiB | 149.20 MiB | 18.53 | 42,825,885 |
| mariadb-innodb-baseline | read-heavy | 64 | 31.138 | 362.70 | 2.81 GiB | 2.64 GiB | 149.28 MiB | 12.71 | 44,043,554 |
| mariadb-innodb-baseline | write-heavy | 4 | 28.023 | 294.60 | 827.30 MiB | 656.75 MiB | 150.19 MiB | 27.46 | 29,993,659 |
| mariadb-innodb-baseline | write-heavy | 16 | 26.634 | 332.30 | 1.11 GiB | 970.59 MiB | 150.25 MiB | 14.54 | 45,381,451 |
| mariadb-innodb-baseline | write-heavy | 32 | 26.515 | 334.40 | 1.71 GiB | 1.55 GiB | 150.34 MiB | 15.86 | 49,755,587 |
| mariadb-innodb-baseline | write-heavy | 64 | 26.383 | 348.60 | 2.86 GiB | 2.69 GiB | 150.77 MiB | 13.91 | 54,389,510 |
| sqlite-driver-3.0.0-rc.3 | balanced | 4 | 38.264 | 383.60 | 935.70 MiB | 765.00 MiB | 149.25 MiB | 12.72 | 42,401,805 |
| sqlite-driver-3.0.0-rc.3 | balanced | 16 | 38.551 | 379.90 | 1.43 GiB | 1.26 GiB | 149.48 MiB | 16.58 | 39,290,670 |
| sqlite-driver-3.0.0-rc.3 | balanced | 32 | 40.904 | 378.00 | 2.11 GiB | 1.93 GiB | 149.48 MiB | 15.75 | 38,921,843 |
| sqlite-driver-3.0.0-rc.3 | balanced | 64 | 39.627 | 379.90 | 3.54 GiB | 3.37 GiB | 149.48 MiB | 15.04 | 38,863,298 |
| sqlite-driver-3.0.0-rc.3 | read-heavy | 4 | 39.054 | 382.70 | 893.31 MiB | 728.17 MiB | 149.09 MiB | 10.54 | 35,631,861 |
| sqlite-driver-3.0.0-rc.3 | read-heavy | 16 | 40.147 | 380.50 | 1.38 GiB | 1.24 GiB | 149.08 MiB | 8.44 | 35,397,575 |
| sqlite-driver-3.0.0-rc.3 | read-heavy | 32 | 39.330 | 379.30 | 1.99 GiB | 1.86 GiB | 149.16 MiB | 11.64 | 35,166,153 |
| sqlite-driver-3.0.0-rc.3 | read-heavy | 64 | 42.453 | 377.60 | 3.33 GiB | 3.16 GiB | 149.28 MiB | 12.38 | 34,928,798 |
| sqlite-driver-3.0.0-rc.3 | write-heavy | 4 | 38.295 | 379.80 | 956.23 MiB | 783.06 MiB | 150.19 MiB | 20.75 | 46,157,451 |
| sqlite-driver-3.0.0-rc.3 | write-heavy | 16 | 37.847 | 376.70 | 1.43 GiB | 1.28 GiB | 150.12 MiB | 17.50 | 47,284,389 |
| sqlite-driver-3.0.0-rc.3 | write-heavy | 32 | 36.882 | 381.90 | 2.16 GiB | 2.00 GiB | 150.34 MiB | 16.22 | 47,681,427 |
| sqlite-driver-3.0.0-rc.3 | write-heavy | 64 | 39.233 | 377.30 | 3.73 GiB | 3.56 GiB | 150.77 MiB | 19.65 | 45,246,338 |
