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

	$server_command_patterns = array(
		'/^(?:set|show|use|help)\b/i'                         => 'server/session command',
		'/^(?:flush|reset|kill|shutdown|restart)\b/i'          => 'server administration command',
		'/^(?:grant|revoke|create user|alter user|drop user)\b/i' => 'account administration command',
		'/^(?:install|uninstall)\s+plugin\b/i'                 => 'plugin administration command',
		'/^(?:analyze|check|checksum|optimize|repair)\s+table\b/i' => 'table administration command',
		'/^(?:cache|load)\s+index\b/i'                         => 'index administration command',
		'/^(?:lock|unlock)\s+tables\b/i'                       => 'table locking command',
		'/^(?:start\s+transaction|begin|commit|rollback|savepoint|release\s+savepoint)\b/i' => 'transaction control command',
		'/^(?:prepare|execute|deallocate\s+prepare)\b/i'       => 'prepared statement command',
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
		'/^(?:create|alter|drop)\s+(?:database|schema|event|function|procedure|server|tablespace|logfile\s+group)\b/i' => 'unsupported DDL object',
		'/^(?:create|alter|drop)\s+trigger\b/i'             => 'trigger DDL',
		'/^(?:create|alter|drop)\s+view\b/i'                => 'view DDL',
		'/^create\s+(?:temporary\s+)?table\b.+\bselect\b/i' => 'CREATE TABLE SELECT',
		'/\bpartition\s+by\b/i'                             => 'partitioned table',
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

	if ( preg_match( '/\binto\s+(?:out|dump)file\b/i', $normalized ) || preg_match( '/\binfile\b/i', $normalized ) ) {
		return 'server file IO';
	}

	if ( preg_match( '/@@|(^|[^[:alnum:]_])@[[:alnum:]_]+/', $normalized ) ) {
		return 'server or user variable';
	}

	$unsupported_function_patterns = array(
		'/\b(?:elt|field)\s*\(/i'              => 'unsupported ELT/FIELD function',
		'/\bbenchmark\s*\(/i'                  => 'benchmark function',
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
		preg_match( '/^(?:drop|insert|replace|update|delete|select)\b/i', $normalized )
		&& preg_match( "/(?:no such table|Table '.+' doesn't exist|Unknown table)/i", $message )
	) {
		return 'missing table after skipped dependency';
	}

	return null;
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
	"MySQL server SQLite loop: executed=%d skipped=%d failed=%d rows_read=%d rows_considered=%d limit=%d offset=%d\n",
	$executed,
	$skipped,
	$failed,
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
