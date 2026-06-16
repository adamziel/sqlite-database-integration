# MySQL-on-SQLite Test Tools

## MySQL Server SQLite Loop

Run a bounded smoke subset of the checked-in MySQL server query corpus against
the in-memory SQLite backend:

```sh
php packages/mysql-on-sqlite/tests/tools/run-mysql-server-sqlite-loop.php
```

Useful options:

```sh
php packages/mysql-on-sqlite/tests/tools/run-mysql-server-sqlite-loop.php --limit=50
php packages/mysql-on-sqlite/tests/tools/run-mysql-server-sqlite-loop.php --limit=5000
php packages/mysql-on-sqlite/tests/tools/run-mysql-server-sqlite-loop.php --limit=25 --json
php packages/mysql-on-sqlite/tests/tools/run-mysql-server-sqlite-loop.php --offset=100 --limit=10 --allow-failures=1
```

The loop intentionally skips server administration, metadata, and known
unsupported MySQL-only constructs. It is a SQLite backend execution smoke test,
not a full MySQL server-suite parity run.

`--limit` counts successful SQLite backend executions, not raw CSV rows. Larger
limits can read far more rows than the requested limit because unsupported
statements are skipped. The runner also resets the in-memory database when the
corpus appears to cross an independent mysql-test fixture boundary, then retries
the same statement against the fresh database.
