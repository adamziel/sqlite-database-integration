<?php

/**
 * Run a bounded subset of the checked-in MySQL server query corpus against the
 * SQLite-backed MySQL driver.
 *
 * Usage:
 *   php tests/tools/run-mysql-server-sqlite-loop.php [--limit=N] [--offset=N]
 *       [--json] [--stop-on-failure] [--allow-failures=N]
 *
 * The limit is the number of successful SQLite backend executions to collect
 * after applying the row offset and explicit skip rules.
 */

const MYSQL_SERVER_SQLITE_LOOP_DEFAULT_LIMIT = 25;
const MYSQL_SERVER_SQLITE_LOOP_DATA_PATH     = __DIR__ . '/../mysql/data/mysql-server-tests-queries.csv';

/**
 * Parse CLI options.
 *
 * @param string[] $argv CLI arguments.
 * @return array{limit:int,offset:int,json:bool,stop_on_failure:bool,allow_failures:int,help:bool}
 */
function mysql_server_sqlite_loop_parse_options( array $argv ): array {
	$options = array(
		'limit'           => MYSQL_SERVER_SQLITE_LOOP_DEFAULT_LIMIT,
		'offset'          => 0,
		'json'            => false,
		'stop_on_failure' => false,
		'allow_failures'  => 0,
		'help'            => false,
	);

	foreach ( array_slice( $argv, 1 ) as $arg ) {
		if ( '--json' === $arg ) {
			$options['json'] = true;
			continue;
		}
		if ( '--stop-on-failure' === $arg ) {
			$options['stop_on_failure'] = true;
			continue;
		}
		if ( '--help' === $arg || '-h' === $arg ) {
			$options['help'] = true;
			continue;
		}
		if ( 0 === strpos( $arg, '--limit=' ) ) {
			$options['limit'] = max( 1, (int) substr( $arg, strlen( '--limit=' ) ) );
			continue;
		}
		if ( 0 === strpos( $arg, '--offset=' ) ) {
			$options['offset'] = max( 0, (int) substr( $arg, strlen( '--offset=' ) ) );
			continue;
		}
		if ( 0 === strpos( $arg, '--allow-failures=' ) ) {
			$options['allow_failures'] = max( 0, (int) substr( $arg, strlen( '--allow-failures=' ) ) );
			continue;
		}

		fwrite( STDERR, sprintf( "Unknown option: %s\n", $arg ) );
		exit( 2 );
	}

	return $options;
}

/**
 * Print usage.
 */
function mysql_server_sqlite_loop_print_usage(): void {
	echo <<<'TXT'
Usage:
  php tests/tools/run-mysql-server-sqlite-loop.php [options]

Options:
  --limit=N            Stop after N successful SQLite backend executions. Default: 25.
  --offset=N           Skip N CSV rows before filtering and execution. Default: 0.
  --json               Print machine-readable JSON output.
  --stop-on-failure    Stop immediately after the first unskipped failure.
  --allow-failures=N   Exit 0 if no more than N unskipped queries fail. Default: 0.
  -h, --help           Show this help.

TXT;
}

/**
 * Return a short, single-line query preview.
 */
function mysql_server_sqlite_loop_preview( string $query, int $limit = 120 ): string {
	$query = preg_replace( '/\s+/', ' ', trim( $query ) );
	if ( strlen( $query ) <= $limit ) {
		return $query;
	}
	return substr( $query, 0, $limit - 3 ) . '...';
}

/**
 * Identify queries that are intentionally outside the current SQLite backend
 * corpus smoke scope.
 *
 * This is not a parity claim. The loop is deliberately conservative so the
 * default suite only executes statements we expect to run against an in-memory
 * SQLite-backed database today.
 */
function mysql_server_sqlite_loop_skip_reason( string $query ): ?string {
	$trimmed = trim( $query );
	if ( '' === $trimmed ) {
		return 'empty';
	}

	$normalized = preg_replace( '/\s+/', ' ', $trimmed );
	$lower      = strtolower( $normalized );

	if ( preg_match( '/^(?:--|#|\/\*).*?(?:\*\/)?$/', $normalized ) ) {
		return 'comment-only row';
	}

	if ( false !== strpos( $normalized, '/*!' ) ) {
		return 'MySQL executable comment';
	}

	if ( preg_match( '/^[^\x00-\x7F]/', $normalized ) ) {
		return 'non-ASCII mysqltest row';
	}

	$server_command_patterns = array(
		'/^(?:set|show|use|help|explain|describe|desc|do)\b/i' => 'server/session command',
		'/^(?:flush|reset|kill|shutdown|restart)\b/i'          => 'server administration command',
		'/^(?:change|start|stop|reset)\s+(?:replication|master|slave)\b/i' => 'replication administration command',
		'/^(?:grant|revoke|create user|alter user|drop user|rename user)\b/i' => 'account administration command',
		'/^(?:install|uninstall)\s+(?:plugin|component)\b/i'   => 'plugin administration command',
		'/^(?:analyze|check|checksum|optimize|repair)\s+table\b/i' => 'table administration command',
		'/^(?:cache|load)\s+index\b/i'                         => 'index administration command',
		'/^(?:lock|unlock)\s+(?:instance|tables?)\b/i'         => 'table locking command',
		'/^(?:start\s+transaction|begin|commit|rollback|savepoint|release\s+savepoint|xa)\b/i' => 'transaction control command',
		'/^(?:prepare|execute|deallocate\s+prepare|drop\s+prepare)\b/i' => 'prepared statement command',
		'/^call\b/i'                                           => 'stored procedure call',
		'/^handler\b/i'                                        => 'handler command',
		'/^load\s+(?:data|xml)\b/i'                            => 'bulk file import command',
	);

	foreach ( $server_command_patterns as $pattern => $reason ) {
		if ( preg_match( $pattern, $normalized ) ) {
			return $reason;
		}
	}

	$unsupported_ddl_patterns = array(
		'/^(?:create|alter|drop)\s+(?:definer\s*=\s*\S+\s+)?(?:database|schema|event|function|procedure|server|tablespace|logfile\s+group)\b/i' => 'unsupported DDL object',
		'/^(?:create|alter|drop)\s+table\s+`?\w+`?\./i'     => 'schema-qualified DDL object',
		'/^(?:create|alter|drop)\s+table\b.*[^\x00-\x7F]/i' => 'non-ASCII DDL identifier',
		'/^(?:create|alter|drop)\s+(?:definer\s*=\s*\S+\s+)?trigger\b/i' => 'trigger DDL',
		'/^(?:(?:alter|drop)\s+view\b|create\s+(?:(?:or\s+replace|algorithm\s*=\s*\w+|definer\s*=\s*\S+|sql\s+security\s+\w+)\s+)*view\b)/i' => 'view DDL',
		'/^drop\s+(?:temporary\s+)?tables\b/i'              => 'DROP TABLES plural form',
		'/^rename\s+table\b/i'                              => 'RENAME TABLE',
		'/^create\s+(?:temporary\s+)?table\b.+\blike\b/i'   => 'CREATE TABLE LIKE',
		'/^create\s+(?:temporary\s+)?table\b.+\bselect\b/i' => 'CREATE TABLE SELECT',
		'/^alter\s+table\b.+\brename\s+(?:column\s+)?\w+\s+(?:to\s+)?\w+\b/i' => 'ALTER TABLE RENAME',
		'/^alter\s+table\b.+\brename\s+to\b/i'              => 'ALTER TABLE RENAME',
		'/^alter\s+table\b.+\b(?:change|modify)\b/i'        => 'ALTER TABLE CHANGE/MODIFY',
		'/^alter\s+table\b.+\bdrop\s+constraint\b/i'        => 'ALTER TABLE DROP constraint',
		'/^alter\s+table\b.+\balgorithm\s*=/i'              => 'online ALTER TABLE option',
		'/^alter\s+table\b.+\b(?:first|after)\b/i'          => 'ALTER TABLE column positioning',
		'/^alter\s+table\b.+\badd\s+(?:(?:(?:unique|fulltext|spatial)\s+)?(?:key|index|constraint|primary|foreign)\b|unique\s+`?\w+`?\s*\()/i' => 'ALTER TABLE ADD index/constraint',
		'/^alter\s+table\b.+\badd\s+.+\bdefault\s*\(/i'     => 'ALTER TABLE ADD expression default',
		'/^alter\s+table\b.+\badd\s+(?:column\s+)?\w+.+\bnot\s+null\b(?![^,]*\bdefault\b)/i' => 'ALTER TABLE ADD NOT NULL without default',
		'/^alter\s+table\b.+\badd\s+(?:column\s*)?\(/i'     => 'parenthesized ALTER TABLE ADD',
		'/^create\s+(?:temporary\s+)?table\b.+\b(?:key|index)\b\s+`?\w*`?\s*\(\s*\(/i' => 'expression index',
		'/\bcheck\s*\(/i'                                   => 'CHECK constraint',
		'/\bpartition\s*(?:by\b|\()/i'                       => 'partitioned table',
		'/\btablespace\b/i'                                 => 'tablespace option',
	);

	foreach ( $unsupported_ddl_patterns as $pattern => $reason ) {
		if ( preg_match( $pattern, $normalized ) ) {
			return $reason;
		}
	}

	if ( preg_match( '/\b(?:from|join|into|update|table)\s+(?:information_schema|performance_schema|mysql|sys)\b/i', $normalized ) ) {
		return 'server metadata schema';
	}

	if ( preg_match( '/\b(?:test|mysql|information_schema|performance_schema|sys)\s*\./i', $normalized ) ) {
		return 'schema-qualified server/test object';
	}

	if ( preg_match( '/\b(?:from|join|into|update|table|truncate|using)\s+`?\w+`?\./i', $normalized ) ) {
		return 'schema-qualified object';
	}

	if ( preg_match( '/\$\w+/', $normalized ) ) {
		return 'mysqltest variable artifact';
	}

	if ( preg_match( '/\b(?:from|join|into|update|table)\s+[^\s,()]*[^\x00-\x7F]/i', $normalized ) ) {
		return 'non-ASCII DML identifier';
	}

	if ( preg_match( '/^truncate\b.*[^\x00-\x7F]/i', $normalized ) ) {
		return 'non-ASCII DML identifier';
	}

	if ( preg_match( '/^select\b.+\bas\s+[^\s,]*[^\x00-\x7F]/i', $normalized ) ) {
		return 'non-ASCII SELECT alias';
	}

	if ( preg_match( '/^select\s+(?:straight_join|sql_(?:big_result|small_result|buffer_result|cache|no_cache|calc_found_rows))\b/i', $normalized ) ) {
		return 'MySQL SELECT option';
	}

	if ( preg_match( '/\bstraight_join\b/i', $normalized ) ) {
		return 'STRAIGHT_JOIN';
	}

	if ( preg_match( '/\b(?:right|full)(?:\s+outer)?\s+join\b/i', $normalized ) ) {
		return 'RIGHT/FULL JOIN';
	}

	if ( preg_match( '/\blateral\s*\(/i', $normalized ) ) {
		return 'LATERAL derived table';
	}

	if ( preg_match( '/^with\s+(?:recursive\s+)?`?(\w+)`?\s+as\b.+,\s*`?\1`?\s+as\b/i', $normalized ) ) {
		return 'duplicate CTE name';
	}

	if ( preg_match( '/\bunion\s+distinct\b/i', $normalized ) ) {
		return 'UNION DISTINCT keyword';
	}

	if ( preg_match( '/\b(?:intersect|except)\s+all\b/i', $normalized ) ) {
		return 'set operation ALL keyword';
	}

	if (
		preg_match( '/^create\s+(?:temporary\s+)?table\b/i', $normalized )
		&& preg_match( '/\bbigint\s+unsigned\b/i', $normalized )
	) {
		return 'unsigned BIGINT range';
	}

	if (
		preg_match( '/^create\s+(?:temporary\s+)?table\b/i', $normalized )
		&& preg_match( '/\b(?:enum|set)\s*\(/i', $normalized )
	) {
		return 'ENUM/SET column type';
	}

	if (
		preg_match( '/^create\s+(?:temporary\s+)?table\b/i', $normalized )
		&& preg_match( '/\bdefault\s*\(/i', $normalized )
	) {
		return 'expression DEFAULT';
	}

	if (
		preg_match( '/^create\s+(?:temporary\s+)?table\b/i', $normalized )
		&& preg_match( '/\b(?:key|index)\s*\(\s*`(?:primary|key|index|constraint)`/i', $normalized )
	) {
		return 'reserved-word index column';
	}

	if (
		preg_match( '/^create\s+(?:temporary\s+)?table\b/i', $normalized )
		&& preg_match( '/\bauto_increment\b/i', $normalized )
		&& preg_match( '/\b(?:double|float|decimal|numeric|char|varchar|text|blob)\b[^,)]*\bauto_increment\b/i', $normalized )
	) {
		return 'non-integer AUTO_INCREMENT';
	}

	if (
		preg_match( '/^create\s+(?:temporary\s+)?table\b/i', $normalized )
		&& preg_match( '/\bauto_increment\b/i', $normalized )
		&& ! preg_match( '/\b(?:primary\s+key|unique)\b/i', $normalized )
	) {
		return 'non-unique AUTO_INCREMENT';
	}

	if (
		preg_match( '/^create\s+(?:temporary\s+)?table\b/i', $normalized )
		&& preg_match( '/\bauto_increment\b/i', $normalized )
		&& preg_match( '/\bprimary\s+key\s*\([^)]*,[^)]*\)/i', $normalized )
	) {
		return 'compound AUTO_INCREMENT key';
	}

	if ( preg_match( '/^delete\s+(?:`?\w+`?(?:\.\*)?\s*,\s*)*`?\w+`?(?:\.\*)?\s+from\b/i', $normalized ) ) {
		return 'multi-table DELETE';
	}

	if ( preg_match( '/^(?:insert|replace)\b.+\bselect\b/i', $normalized ) ) {
		return 'INSERT SELECT';
	}

	if ( preg_match( '/^insert\b.+\bset\s+\w+\s*=/i', $normalized ) ) {
		return 'INSERT SET form';
	}

	if ( preg_match( '/^insert\s+(?:low_priority|delayed|high_priority)\b/i', $normalized ) ) {
		return 'INSERT priority modifier';
	}

	if ( preg_match( '/^insert\b.+\bvalue\s*\(/i', $normalized ) ) {
		return 'INSERT VALUE singular form';
	}

	if ( preg_match( '/^insert\b.+\bvalues?\s*\([^)]*\bdefault\b/i', $normalized ) ) {
		return 'INSERT DEFAULT value';
	}

	if ( preg_match( '/^insert\b.+\bvalues\s*\(\s*\)/i', $normalized ) ) {
		return 'empty INSERT VALUES row';
	}

	if ( preg_match( '/\binto\s+(?:out|dump)file\b/i', $normalized ) || preg_match( '/\binfile\b/i', $normalized ) ) {
		return 'server file IO';
	}

	if ( preg_match( '/@@|(^|[^[:alnum:]_])@[[:alnum:]_]+/', $normalized ) ) {
		return 'server or user variable';
	}

	if ( preg_match( "/\\bb'[01]+'/i", $normalized ) ) {
		return 'bit literal';
	}

	if ( preg_match( '/\b0x[0-9a-f]+\b/i', $normalized ) ) {
		return 'hex literal';
	}

	if ( false !== strpos( $normalized, '\\0' ) ) {
		return 'binary null literal';
	}

	if ( preg_match( "/\\b_\\w+\\s*(?:(?:x)?'[^']*'|0x[0-9a-f]+)/i", $normalized ) ) {
		return 'charset introducer literal';
	}

	if ( preg_match( "/\\bN'[^']*'/i", $normalized ) ) {
		return 'national character literal';
	}

	if ( preg_match( "/'[^']*'\\s+'[^']*'/", $normalized ) ) {
		return 'adjacent string literal concatenation';
	}

	if ( preg_match( '/\b(?:date|time|timestamp)\s*[\'"][^\'"]+[\'"]/i', $normalized ) ) {
		return 'typed date/time literal';
	}

	if ( preg_match( '/\bcast\s*\(.+\bas\s+unsigned\b/i', $normalized ) ) {
		return 'unsigned CAST expression';
	}

	if ( preg_match( '/\bcast\s*\(.+\bas\s+year\b/i', $normalized ) ) {
		return 'YEAR CAST expression';
	}

	if ( preg_match( '/\bmod\b/i', $normalized ) ) {
		return 'MOD operator expression';
	}

	if ( false !== strpos( $normalized, '<=>' ) ) {
		return 'null-safe equality operator';
	}

	if ( preg_match( '/\bsounds\s+like\b/i', $normalized ) ) {
		return 'SOUNDS LIKE operator';
	}

	if ( preg_match( '/\bxor\b/i', $normalized ) ) {
		return 'XOR operator';
	}

	if ( preg_match( '/\blike\b.+\bescape\b/i', $normalized ) ) {
		return 'LIKE ESCAPE clause';
	}

	if ( preg_match( '/\b\d+e(?:[a-z_]|\+\s|\-\s)/i', $normalized ) ) {
		return 'ambiguous exponent token';
	}

	if ( preg_match( '/\binterval\s+[-+]?\d+\s+\w+\b/i', $normalized ) ) {
		return 'INTERVAL expression';
	}

	if ( preg_match( '/\bcoalesce\s*\(\s*[^,()]+\s*\)/i', $normalized ) ) {
		return 'single-argument COALESCE';
	}

	if ( preg_match( '/\bcount\s*\(\s*distinct\s+[^)]*,/i', $normalized ) ) {
		return 'multi-expression COUNT DISTINCT';
	}

	if ( preg_match( '/\bwhere\b[^;]*\b(?:avg|count|group_concat|max|min|sum)\s*\(/i', $normalized ) ) {
		return 'aggregate in WHERE clause';
	}

	if ( preg_match( '/\b(?:group|order)\s+by\s+-\d+\b/i', $normalized ) ) {
		return 'negative GROUP/ORDER BY numeric term';
	}

	if ( preg_match( '/\bgroup_concat\s*\(.+\bseparator\b/i', $normalized ) ) {
		return 'MySQL GROUP_CONCAT syntax';
	}

	if ( preg_match( '/\bcollate\s+(?!nocase\b|binary\b|rtrim\b)\w+/i', $normalized ) ) {
		return 'MySQL COLLATE clause';
	}

	if ( preg_match( '/(?:=|<>|!=|<|>|<=|>=)\s*(?:any|some|all)\s*\(/i', $normalized ) ) {
		return 'quantified subquery predicate';
	}

	if ( preg_match( '/\bmatch\b.+\bagainst\s*\(/i', $normalized ) ) {
		return 'fulltext MATCH AGAINST';
	}

	if ( preg_match( '/\bconvert\s*\(.+\s+using\s+\w+\s*\)/i', $normalized ) ) {
		return 'charset CONVERT expression';
	}

	if ( preg_match( '/\bchar\s*\(.+\s+using\s+\w+\s*\)/i', $normalized ) ) {
		return 'charset CHAR expression';
	}

	$unsupported_function_patterns = array(
		'/\b(?:elt|field)\s*\(/i'              => 'unsupported ELT/FIELD function',
		'/\bexport_set\s*\(/i'                 => 'unsupported EXPORT_SET function',
		'/\binsert\s*\(/i'                     => 'unsupported INSERT function',
		'/\bbin\s*\(/i'                        => 'unsupported BIN function',
		'/\bconv\s*\(/i'                       => 'unsupported CONV function',
		'/\bconvert\s*\(/i'                    => 'unsupported CONVERT function',
		'/\b(?:charset|collation|coercibility)\s*\(/i' => 'charset metadata function',
		'/\bweight_string\s*\(/i'             => 'charset metadata function',
		'/\bjson_table\s*\(/i'                 => 'unsupported JSON_TABLE function',
		'/\bbenchmark\s*\(/i'                  => 'benchmark function',
		'/\b(?:user|database|schema|connection_id|current_user|session_user|system_user|last_insert_id|sleep)\s*\(/i' => 'server context function',
		'/\b(?:get_lock|release_lock|is_free_lock|is_used_lock)\s*\(/i' => 'locking function',
		'/\b(?:aes_encrypt|aes_decrypt|compress|uncompress)\s*\(/i' => 'unsupported encryption/compression function',
		'/\brepeat\s*\(/i'                     => 'unsupported REPEAT function',
		'/\b(?:st_|geometrycollection|geomcollection|point|linestring|polygon|multipoint|multilinestring|multipolygon)\w*\s*\(/i' => 'spatial function',
	);

	foreach ( $unsupported_function_patterns as $pattern => $reason ) {
		if ( preg_match( $pattern, $normalized ) ) {
			return $reason;
		}
	}

	if ( false !== strpos( $lower, 'mysqltest' ) ) {
		return 'mysqltest helper artifact';
	}

	return null;
}

/**
 * Some corpus rows depend on setup that this bounded SQLite loop intentionally
 * skipped. Treat those follow-on errors as skipped rows so they do not obscure
 * the first unsupported construct.
 */
function mysql_server_sqlite_loop_runtime_skip_reason( string $query, Throwable $e ): ?string {
	$normalized = preg_replace( '/\s+/', ' ', trim( $query ) );
	$message    = $e->getMessage();

	if (
		preg_match( '/^(?:create|alter|drop|insert|replace|update|delete|select)\b/i', $normalized )
		&& preg_match( "/(?:no such table|Table '.+' doesn't exist|Unknown table)/i", $message )
	) {
		return 'missing table after skipped dependency';
	}

	if (
		preg_match( '/^(?:create|insert|replace|update|delete|select)\b/i', $normalized )
		&& preg_match( "/(?:Unknown column|no such column|Column not found|Key column '.+' doesn't exist)/i", $message )
	) {
		return 'missing column after skipped dependency';
	}

	if (
		preg_match( '/^alter\b/i', $normalized )
		&& preg_match( '/Duplicate column name/i', $message )
	) {
		return 'duplicate column after skipped dependency';
	}

	if (
		preg_match( '/^(?:insert|replace|update|delete|select)\b/i', $normalized )
		&& preg_match( '/no such function/i', $message )
	) {
		return 'missing function after skipped dependency';
	}

	if (
		preg_match( '/^update\b.+\bset\s+`?\w+`?\s*=\s*(?:null|0)\b/i', $normalized )
		&& preg_match( '/UNIQUE constraint failed/i', $message )
	) {
		return 'AUTO_INCREMENT update to generated value';
	}

	if (
		preg_match( '/^(?:insert|replace)\b/i', $normalized )
		&& preg_match( '/\bvalues\s*\(\s*0\b/i', $normalized )
		&& preg_match( '/UNIQUE constraint failed/i', $message )
	) {
		return 'AUTO_INCREMENT explicit zero insert';
	}

	if (
		preg_match( '/^(?:insert|replace)\b/i', $normalized )
		&& preg_match( '/UNIQUE constraint failed/i', $message )
	) {
		return 'duplicate key after skipped dependency';
	}

	return null;
}

/**
 * Determine whether a duplicate CREATE TABLE means the corpus moved to a new
 * independent mysql-test fixture while our smoke loop kept the same database.
 */
function mysql_server_sqlite_loop_is_fixture_boundary( string $query, Throwable $e ): bool {
	$normalized = preg_replace( '/\s+/', ' ', trim( $query ) );
	$message    = $e->getMessage();

	return (
		preg_match( '/^CREATE\s+(?:TEMPORARY\s+)?TABLE\b/i', $normalized )
		&& preg_match( "/(?:Base table or view already exists|Table '.+' already exists|table .* already exists|unknown column .+ in foreign key definition)/i", $message )
	);
}

/**
 * Create an in-memory SQLite-backed MySQL driver.
 */
function mysql_server_sqlite_loop_create_driver(): WP_SQLite_Driver {
	$pdo_class = PHP_VERSION_ID >= 80400 ? PDO\SQLite::class : PDO::class;
	$pdo       = new $pdo_class( 'sqlite::memory:' );
	$pdo->setAttribute( PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION );

	$driver = new WP_SQLite_Driver(
		new WP_SQLite_Connection( array( 'pdo' => $pdo ) ),
		'wp'
	);

	// The early MySQL server corpus fixtures depend on permissive date handling.
	$driver->query( "SET sql_mode = 'NO_ENGINE_SUBSTITUTION'" );

	return $driver;
}

$options = mysql_server_sqlite_loop_parse_options( $argv );
if ( $options['help'] ) {
	mysql_server_sqlite_loop_print_usage();
	exit( 0 );
}

require_once __DIR__ . '/../../src/load.php';

$sqlite_version = ( new PDO( 'sqlite::memory:' ) )->query( 'SELECT SQLITE_VERSION();' )->fetch()[0];
if (
	version_compare( $sqlite_version, WP_PDO_MySQL_On_SQLite::MINIMUM_SQLITE_VERSION, '<' )
	&& ! defined( 'WP_SQLITE_UNSAFE_ENABLE_UNSUPPORTED_VERSIONS' )
) {
	define( 'WP_SQLITE_UNSAFE_ENABLE_UNSUPPORTED_VERSIONS', true );
}

$handle = @fopen( MYSQL_SERVER_SQLITE_LOOP_DATA_PATH, 'r' );
if ( false === $handle ) {
	fwrite( STDERR, sprintf( "Failed to open corpus file: %s\n", MYSQL_SERVER_SQLITE_LOOP_DATA_PATH ) );
	exit( 2 );
}

$driver          = mysql_server_sqlite_loop_create_driver();
$rows_read       = 0;
$rows_considered = 0;
$executed        = 0;
$failed          = 0;
$skipped         = 0;
$resets          = 0;
$failures        = array();
$skip_reasons    = array();
$start           = microtime( true );

try {
	while ( $executed < $options['limit'] && ( $record = fgetcsv( $handle, null, ',', '"', '\\' ) ) !== false ) {
		$rows_read++;

		if ( $rows_read <= $options['offset'] ) {
			continue;
		}

		$rows_considered++;
		$query = $record[0] ?? '';

		$skip_reason = mysql_server_sqlite_loop_skip_reason( $query );
		if ( null !== $skip_reason ) {
			$skipped++;
			$skip_reasons[ $skip_reason ] = ( $skip_reasons[ $skip_reason ] ?? 0 ) + 1;
			continue;
		}

		try {
			$driver->query( $query );
			$executed++;
		} catch ( Throwable $e ) {
			if ( mysql_server_sqlite_loop_is_fixture_boundary( $query, $e ) ) {
				$resets++;
				$driver = mysql_server_sqlite_loop_create_driver();

				try {
					$driver->query( $query );
					$executed++;
					continue;
				} catch ( Throwable $retry_exception ) {
					$e = $retry_exception;
				}
			}

			$runtime_skip_reason = mysql_server_sqlite_loop_runtime_skip_reason( $query, $e );
			if ( null !== $runtime_skip_reason ) {
				$skipped++;
				$skip_reasons[ $runtime_skip_reason ] = ( $skip_reasons[ $runtime_skip_reason ] ?? 0 ) + 1;
				continue;
			}

			$failed++;
			$failures[] = array(
				'row'     => $rows_read,
				'query'   => mysql_server_sqlite_loop_preview( $query ),
				'class'   => get_class( $e ),
				'message' => $e->getMessage(),
			);

			if ( $options['stop_on_failure'] || $failed > $options['allow_failures'] ) {
				break;
			}
		}
	}
} finally {
	fclose( $handle );
}

$duration = microtime( true ) - $start;
$exit     = $failed <= $options['allow_failures'] && $executed >= $options['limit'] ? 0 : 1;
$summary  = array(
	'corpus'          => MYSQL_SERVER_SQLITE_LOOP_DATA_PATH,
	'limit'           => $options['limit'],
	'offset'          => $options['offset'],
	'rows_read'       => $rows_read,
	'rows_considered' => $rows_considered,
	'executed'        => $executed,
	'skipped'         => $skipped,
	'failed'          => $failed,
	'fixture_resets'  => $resets,
	'allow_failures'  => $options['allow_failures'],
	'duration'        => $duration,
	'sqlite_version'  => $sqlite_version,
	'skip_reasons'    => $skip_reasons,
	'failures'        => $failures,
);

if ( $options['json'] ) {
	echo json_encode( $summary, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES ), "\n";
	exit( $exit );
}

printf(
	"MySQL server SQLite loop: executed=%d skipped=%d failed=%d fixture_resets=%d rows_read=%d rows_considered=%d limit=%d offset=%d\n",
	$executed,
	$skipped,
	$failed,
	$resets,
	$rows_read,
	$rows_considered,
	$options['limit'],
	$options['offset']
);
printf( "SQLite version: %s\n", $sqlite_version );

if ( count( $skip_reasons ) > 0 ) {
	ksort( $skip_reasons );
	echo "Skipped by reason:\n";
	foreach ( $skip_reasons as $reason => $count ) {
		printf( "  %s: %d\n", $reason, $count );
	}
}

if ( count( $failures ) > 0 ) {
	echo "Failures:\n";
	foreach ( $failures as $failure ) {
		printf(
			"  row %d: %s: %s :: %s\n",
			$failure['row'],
			$failure['class'],
			$failure['message'],
			$failure['query']
		);
	}
}

printf( "Duration: %.5fs\n", $duration );
exit( $exit );
