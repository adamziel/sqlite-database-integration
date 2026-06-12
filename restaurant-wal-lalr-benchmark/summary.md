# Local Production-Methodology Small Restaurant Benchmark

Scope: macOS system-under-test using local nginx, PHP-FPM, WordPress, and MySQL 8.4 InnoDB/SQLite. This is a small-site diagnostic matching the previous WooCommerce methodology as closely as practical.

Fixture profile: `restaurant-small` {'pages': 10, 'posts': 6, 'comments': 36, 'users': 4, 'reservation_seed_rows': 8}. Warm-up: `5.0s`; measured duration: `20.0s`; repetitions: `3`; concurrency: `[4, 16, 32, 64]`.
Resource sampling interval: `1.0s`; CPU is process-group `%CPU` sampled from macOS `ps`, normalized to approximate core-seconds per 1k successful flows. Disk activity is sampled from macOS `iostat`; RSS is process-group resident memory.

WordPress `7.0`, PHP 8.5.7 (cli) (built: Jun  2 2026 20:59:56) (NTS), PHP 8.5.7 (fpm-fcgi) (built: Jun  2 2026 20:59:56) (NTS), nginx version: nginx/1.31.1, /opt/homebrew/opt/mysql@8.4/bin/mysql  Ver 8.4.9 for macos26.4 on arm64 (Homebrew).

| Variant | Workload | Concurrent requests | Reps | Median flows/s | Median avg request ms | Median p95 ms | Median write/s | Failed flows | Verify failures | SQLite lock errors | Max WAL bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mariadb-innodb-baseline | balanced | 4 | 3 | 97.10 | 26.77 | 99.90 | 19.68 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | balanced | 16 | 3 | 94.14 | 106.99 | 521.30 | 19.28 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | balanced | 32 | 3 | 89.61 | 212.92 | 1,113.06 | 18.22 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | balanced | 64 | 3 | 92.94 | 424.92 | 1,872.67 | 19.32 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 4 | 3 | 99.59 | 25.03 | 92.56 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 16 | 3 | 95.78 | 98.05 | 499.56 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 32 | 3 | 94.98 | 208.56 | 1,002.28 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | read-heavy | 64 | 3 | 96.41 | 396.59 | 1,885.23 | 0.00 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 4 | 3 | 99.90 | 28.32 | 102.76 | 29.51 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 16 | 3 | 101.23 | 112.79 | 526.78 | 29.14 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 32 | 3 | 102.54 | 226.39 | 1,016.87 | 32.06 | 0 | 0 | 0 | 0 |
| mariadb-innodb-baseline | write-heavy | 64 | 3 | 103.24 | 452.38 | 1,640.31 | 31.33 | 0 | 0 | 0 | 0 |
| sqlite-wal-pr405-lalr-pr429 | balanced | 4 | 3 | 91.71 | 28.41 | 107.89 | 19.16 | 0 | 0 | 0 | 4350752 |
| sqlite-wal-pr405-lalr-pr429 | balanced | 16 | 3 | 86.49 | 115.53 | 472.27 | 17.62 | 0 | 0 | 0 | 4527912 |
| sqlite-wal-pr405-lalr-pr429 | balanced | 32 | 3 | 85.45 | 223.63 | 915.89 | 17.54 | 0 | 0 | 0 | 4606192 |
| sqlite-wal-pr405-lalr-pr429 | balanced | 64 | 3 | 86.90 | 460.23 | 1,894.80 | 18.13 | 0 | 0 | 0 | 5491992 |
| sqlite-wal-pr405-lalr-pr429 | read-heavy | 4 | 3 | 89.52 | 27.96 | 102.03 | 0.00 | 0 | 0 | 0 | 74192 |
| sqlite-wal-pr405-lalr-pr429 | read-heavy | 16 | 3 | 84.37 | 112.32 | 426.52 | 0.00 | 0 | 0 | 0 | 78312 |
| sqlite-wal-pr405-lalr-pr429 | read-heavy | 32 | 3 | 87.35 | 226.04 | 821.91 | 0.00 | 0 | 0 | 0 | 78312 |
| sqlite-wal-pr405-lalr-pr429 | read-heavy | 64 | 3 | 84.17 | 454.30 | 1,738.22 | 0.00 | 0 | 0 | 0 | 78312 |
| sqlite-wal-pr405-lalr-pr429 | write-heavy | 4 | 3 | 92.77 | 30.24 | 110.70 | 27.33 | 0 | 0 | 0 | 4255992 |
| sqlite-wal-pr405-lalr-pr429 | write-heavy | 16 | 3 | 91.82 | 123.79 | 491.84 | 26.96 | 0 | 0 | 0 | 5409592 |
| sqlite-wal-pr405-lalr-pr429 | write-heavy | 32 | 3 | 94.08 | 242.59 | 900.41 | 28.78 | 0 | 0 | 0 | 6612632 |
| sqlite-wal-pr405-lalr-pr429 | write-heavy | 64 | 3 | 92.97 | 500.70 | 1,853.09 | 28.22 | 0 | 0 | 0 | 18342272 |

## Server Load Summary

| Variant | Workload | Concurrent requests | CPU core-s / 1k flows | Peak process CPU % | Peak total RSS | Peak PHP-FPM RSS | Peak DB RSS | Peak disk MB/sample | Median loopback bytes/s |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mariadb-innodb-baseline | balanced | 4 | 34.406 | 361.10 | 1.01 GiB | 657.95 MiB | 355.03 MiB | 29.68 | 90,645,297 |
| mariadb-innodb-baseline | balanced | 16 | 36.440 | 350.90 | 1.44 GiB | 1.08 GiB | 358.94 MiB | 16.27 | 82,497,497 |
| mariadb-innodb-baseline | balanced | 32 | 36.921 | 348.00 | 2.14 GiB | 1.76 GiB | 363.78 MiB | 7.97 | 80,278,694 |
| mariadb-innodb-baseline | balanced | 64 | 36.300 | 349.00 | 3.54 GiB | 3.15 GiB | 369.00 MiB | 18.10 | 80,506,751 |
| mariadb-innodb-baseline | read-heavy | 4 | 33.475 | 359.40 | 1.03 GiB | 645.83 MiB | 386.05 MiB | 12.32 | 73,959,929 |
| mariadb-innodb-baseline | read-heavy | 16 | 36.213 | 355.50 | 1.44 GiB | 1.03 GiB | 397.25 MiB | 5.70 | 73,235,300 |
| mariadb-innodb-baseline | read-heavy | 32 | 33.783 | 355.70 | 2.09 GiB | 1.68 GiB | 405.58 MiB | 14.38 | 70,474,874 |
| mariadb-innodb-baseline | read-heavy | 64 | 35.361 | 348.50 | 3.62 GiB | 3.30 GiB | 412.59 MiB | 50.42 | 70,612,883 |
| mariadb-innodb-baseline | write-heavy | 4 | 33.263 | 352.30 | 1.02 GiB | 667.97 MiB | 367.52 MiB | 26.50 | 115,657,042 |
| mariadb-innodb-baseline | write-heavy | 16 | 33.708 | 356.50 | 1.43 GiB | 1.04 GiB | 374.72 MiB | 22.80 | 131,496,327 |
| mariadb-innodb-baseline | write-heavy | 32 | 32.506 | 353.30 | 2.13 GiB | 1.74 GiB | 381.39 MiB | 21.76 | 121,382,305 |
| mariadb-innodb-baseline | write-heavy | 64 | 32.679 | 351.30 | 3.51 GiB | 3.14 GiB | 387.41 MiB | 20.90 | 125,582,884 |
| sqlite-wal-pr405-lalr-pr429 | balanced | 4 | 39.043 | 374.20 | 1.13 GiB | 769.64 MiB | 370.98 MiB | 47.19 | 40,380,735 |
| sqlite-wal-pr405-lalr-pr429 | balanced | 16 | 39.090 | 369.30 | 1.62 GiB | 1.26 GiB | 370.98 MiB | 14.83 | 35,887,107 |
| sqlite-wal-pr405-lalr-pr429 | balanced | 32 | 40.517 | 370.70 | 2.29 GiB | 1.94 GiB | 370.98 MiB | 6.82 | 36,615,890 |
| sqlite-wal-pr405-lalr-pr429 | balanced | 64 | 41.555 | 364.10 | 3.69 GiB | 3.33 GiB | 370.98 MiB | 13.60 | 35,736,565 |
| sqlite-wal-pr405-lalr-pr429 | read-heavy | 4 | 40.554 | 369.30 | 1.10 GiB | 725.97 MiB | 381.47 MiB | 13.32 | 34,713,260 |
| sqlite-wal-pr405-lalr-pr429 | read-heavy | 16 | 41.816 | 365.40 | 1.56 GiB | 1.20 GiB | 381.47 MiB | 12.71 | 33,480,249 |
| sqlite-wal-pr405-lalr-pr429 | read-heavy | 32 | 39.859 | 369.90 | 2.26 GiB | 1.90 GiB | 381.47 MiB | 12.85 | 33,336,164 |
| sqlite-wal-pr405-lalr-pr429 | read-heavy | 64 | 41.265 | 370.10 | 3.43 GiB | 3.07 GiB | 381.47 MiB | 25.66 | 32,077,421 |
| sqlite-wal-pr405-lalr-pr429 | write-heavy | 4 | 38.043 | 366.10 | 1.15 GiB | 788.80 MiB | 370.98 MiB | 12.81 | 44,270,281 |
| sqlite-wal-pr405-lalr-pr429 | write-heavy | 16 | 39.110 | 369.60 | 1.66 GiB | 1.27 GiB | 370.98 MiB | 11.21 | 44,716,660 |
| sqlite-wal-pr405-lalr-pr429 | write-heavy | 32 | 37.051 | 372.00 | 2.38 GiB | 1.99 GiB | 370.98 MiB | 12.02 | 45,219,948 |
| sqlite-wal-pr405-lalr-pr429 | write-heavy | 64 | 38.847 | 368.50 | 3.97 GiB | 3.61 GiB | 370.98 MiB | 15.90 | 44,780,208 |
