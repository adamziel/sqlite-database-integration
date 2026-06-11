# Restaurant Site: Real Chrome Browser Benchmark

Low-load Google Chrome rendering and XHR comparison for a small restaurant WordPress fixture:

- MariaDB/InnoDB baseline
- SQLite Database Integration `v3.0.0-rc.3`

The run used 20 repetitions per flow for:

- Restaurant homepage render
- Restaurant menu page render
- Restaurant blog post render
- Restaurant frontend XHR burst
- Restaurant reservation submit
- `wp-admin` post editor open
- `wp-admin` Site Editor open
- `wp-admin` pages search

Primary report:

- [Chrome visual report](comparison-chrome-20-repetitions.html)

Supporting artifacts:

- [Aggregate JSON](aggregate.json)
- [Manifest JSON](manifest.json)
