# SQLite rc3 vs MariaDB: Decision Summary

Decision: SQLite Database Integration v3.0.0-rc.3 looks viable for small or low-concurrency sites after environment-specific validation, but the current measurements do not support making it the default replacement for MariaDB on write-heavy or high-concurrency WooCommerce production sites.

## Simple Dimensions

| Dimension | Impact of SQLite rc3 vs MariaDB | Decision meaning |
| --- | --- | --- |
| Browser-visible page readiness | Mostly tied; median ready delta was +0.2% on restaurant flows and +0.4% on WooCommerce flows. | Most users probably would not notice on ordinary page/editor flows. |
| Server request capacity | Slower under load; SQLite throughput was lower in 20 of 24 request-load cells. | Capacity headroom is the main reason not to make it the default everywhere. |
| Tail latency | Mixed; p95 improved in 15 of 24 request-load cells, but WooCommerce write-heavy c32/c64 regressed +33.9%/+40.0%. | p95 alone is not enough; pair it with throughput. |
| Writes and correctness | rc3 had 0 flow failures, 0 write verification failures, and 0 SQLite busy/locked errors in these local runs. | rc3 is much healthier than the old stable control, but write-heavy capacity still needs caution. |
| Operational fit | SQLite removes the MariaDB service but uses WAL files and has different concurrency behavior. | Simpler stack, but not automatically faster at scale. |

## Recommendation

- Use rc3 as a serious candidate for small sites, development, demos, local-first deployments, and low-write sites.
- Do not treat rc3 as a blanket MariaDB replacement for WooCommerce or high-write production traffic based on these measurements.
- If adopting, gate it by workload: browser journeys, checkout/admin writes, request throughput at expected concurrency, write verification, and lock/busy logs.
