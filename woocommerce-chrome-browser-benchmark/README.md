# WooCommerce 5GB Real Chrome Browser Benchmark

Real Google Chrome rendering and XHR benchmark for a 5GB WooCommerce fixture. This version repeats each measured flow 20 times for both MySQL/MariaDB and SQLite.

- `comparison-chrome-20-repetitions.html`: visual report with medians, deltas, distribution plots, box/dot plots, and scatter plots.
- `comparison-chrome.html`: same report at the stable path; GitHub Pages may cache this path for several minutes after updates.
- `aggregate.json`: summarized metrics used by the report.
- `manifest.json`: run environment, versions, fixture metadata, and benchmark scope.

This is a low-load browser-visible diagnostic run on local macOS. It complements the concurrent request benchmark reports in the sibling directories.
