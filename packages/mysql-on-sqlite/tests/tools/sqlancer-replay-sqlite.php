<?php
/**
 * Replays a conservative SQLancer SQLite corpus through WP_SQLite_Driver.
 *
 * SQLancer targets SQLite directly, while WP_SQLite_Driver accepts the
 * project's MySQL-on-SQLite surface. This harness keeps statements that are
 * already compatible or can be safely normalized across that boundary, records
 * skipped SQLite-only statements, and captures any unexpected driver failure as
 * a replayable fixture.
 */

require_once __DIR__ . '/../bootstrap.php';

$options = parse_cli_options( $argv );

if ( isset( $options['help'] ) || ( ! isset( $options['input'] ) && ! isset( $options['fixtures'] ) ) ) {
	fwrite(
		STDOUT,
		"Usage:\n" .
		"  php tests/tools/sqlancer-replay-sqlite.php --input <log-file-or-dir> [--limit 75] [--capture-dir tests/sqlancer/fixtures/generated]\n" .
		"  php tests/tools/sqlancer-replay-sqlite.php --fixtures [--input tests/sqlancer/fixtures]\n"
	);
	exit( isset( $options['help'] ) ? 0 : 1 );
}

$limit                = isset( $options['limit'] ) ? max( 0, (int) $options['limit'] ) : 0;
$require_min_replayed = isset( $options['require-min-replayed'] ) ? (int) $options['require-min-replayed'] : 0;
$capture_dir          = isset( $options['capture-dir'] ) ? $options['capture-dir'] : null;

if ( isset( $options['fixtures'] ) ) {
	$input = isset( $options['input'] ) ? $options['input'] : __DIR__ . '/../sqlancer/fixtures';
	$files = collect_files( $input, '/\.sql$/i' );
	$summary = array(
		'fixture_files' => count( $files ),
		'replayed'      => 0,
		'failures'      => 0,
	);

	foreach ( $files as $file ) {
		$statements = split_sql_statements( file_get_contents( $file ) );
		$result     = replay_statements( $statements );
		$summary['replayed'] += count( $statements );

		if ( null !== $result['failure'] ) {
			++$summary['failures'];
			fwrite( STDERR, "Fixture failed: {$file}\n" );
			fwrite( STDERR, format_failure( $result['failure'] ) . "\n" );
		}
	}

	print_summary( $summary );
	exit( 0 === $summary['failures'] ? 0 : 1 );
}

$input_files = collect_files( $options['input'], '/-cur\.log$|\.log$/i' );
if ( empty( $input_files ) ) {
	fwrite( STDERR, "No SQLancer log files found under {$options['input']}.\n" );
	exit( 1 );
}

$accepted        = array();
$source_records  = array();
$skip_reasons    = array();
$total_generated = 0;
$normalized      = 0;

foreach ( $input_files as $file ) {
	foreach ( extract_sqlancer_statements( file_get_contents( $file ) ) as $statement ) {
		++$total_generated;
		$reason = '';
		$sql    = normalize_statement_for_driver( $statement, $reason );

		if ( null === $sql ) {
			$skip_reasons[ $reason ] = isset( $skip_reasons[ $reason ] ) ? $skip_reasons[ $reason ] + 1 : 1;
			continue;
		}

		if ( trim_sql( $statement ) !== trim_sql( $sql ) ) {
			++$normalized;
		}

		$accepted[]       = $sql;
		$source_records[] = array(
			'file'       => $file,
			'original'   => $statement,
			'normalized' => $sql,
		);

		if ( $limit > 0 && count( $accepted ) >= $limit ) {
			break 2;
		}
	}
}

$result = replay_statements( $accepted );
$summary = array(
	'log_files'            => count( $input_files ),
	'generated_statements' => $total_generated,
	'replayed'             => count( $accepted ),
	'normalized'           => $normalized,
	'skipped'              => array_sum( $skip_reasons ),
	'skip_reasons'         => $skip_reasons,
	'failures'             => null === $result['failure'] ? 0 : 1,
);

if ( null !== $result['failure'] ) {
	fwrite( STDERR, format_failure( $result['failure'] ) . "\n" );

	if ( null !== $capture_dir ) {
		$fixture = capture_failure_fixture( $capture_dir, $accepted, $source_records, $result['failure'] );
		fwrite( STDERR, "Captured regression fixture: {$fixture['sql']}\n" );
		fwrite( STDERR, "Captured fixture metadata: {$fixture['json']}\n" );
	}
}

print_summary( $summary );

if ( count( $accepted ) < $require_min_replayed ) {
	fwrite( STDERR, "Expected at least {$require_min_replayed} replayed statement(s), got " . count( $accepted ) . ".\n" );
	exit( 1 );
}

exit( 0 === $summary['failures'] ? 0 : 1 );

function parse_cli_options( $argv ) {
	$options = array();
	for ( $i = 1; $i < count( $argv ); ++$i ) {
		$arg = $argv[ $i ];
		if ( 0 !== strpos( $arg, '--' ) ) {
			continue;
		}

		$key = substr( $arg, 2 );
		if ( false !== strpos( $key, '=' ) ) {
			list( $key, $value ) = explode( '=', $key, 2 );
			$options[ $key ]    = $value;
			continue;
		}

		if ( isset( $argv[ $i + 1 ] ) && 0 !== strpos( $argv[ $i + 1 ], '--' ) ) {
			$options[ $key ] = $argv[ ++$i ];
		} else {
			$options[ $key ] = true;
		}
	}
	return $options;
}

function collect_files( $path, $pattern ) {
	if ( is_file( $path ) ) {
		return preg_match( $pattern, $path ) ? array( $path ) : array();
	}

	if ( ! is_dir( $path ) ) {
		return array();
	}

	$files    = array();
	$iterator = new RecursiveIteratorIterator(
		new RecursiveDirectoryIterator( $path, FilesystemIterator::SKIP_DOTS )
	);

	foreach ( $iterator as $file ) {
		$pathname = $file->getPathname();
		if ( $file->isFile() && preg_match( $pattern, $pathname ) ) {
			$files[] = $pathname;
		}
	}

	sort( $files );
	return $files;
}

function extract_sqlancer_statements( $contents ) {
	$statements = array();
	if ( preg_match_all( '/^(.+?);\s+--\s+\d+ms;$/ms', $contents, $matches ) ) {
		foreach ( $matches[1] as $sql ) {
			$statements[] = trim( $sql ) . ';';
		}
	}
	return $statements;
}

function normalize_statement_for_driver( $statement, &$reason ) {
	$sql = trim_sql( $statement );

	if ( '' === $sql ) {
		$reason = 'empty';
		return null;
	}

	if ( preg_match( '/[^\x09\x0A\x0D\x20-\x7E]/', $sql ) ) {
		$reason = 'non-ascii generated literal';
		return null;
	}

	if ( preg_match( '/\bsqlite_(?:stat\d*|master|schema|sequence)\b/i', $sql ) ) {
		$reason = 'sqlite internal table';
		return null;
	}

	if ( preg_match( '/\b(?:PRAGMA|BEGIN|COMMIT|ROLLBACK|END|REINDEX|ANALYZE|VACUUM)\b/i', $sql ) ) {
		$reason = 'sqlite control statement';
		return null;
	}

	if ( preg_match( '/\b(?:CREATE\s+VIRTUAL\s+TABLE|CREATE\s+(?:UNIQUE\s+)?INDEX)\b/i', $sql ) ) {
		$reason = 'sqlite-only schema statement';
		return null;
	}

	if ( ! preg_match( '/^\s*(?:CREATE\s+TABLE|INSERT|UPDATE|DELETE|SELECT)\b/i', $sql ) ) {
		$reason = 'outside replayed statement classes';
		return null;
	}

	if ( preg_match( '/\b(?:GLOB|MATCH|NULLS\s+(?:FIRST|LAST)|ISNULL|NOTNULL)\b/i', $sql ) ) {
		$reason = 'sqlite-only expression syntax';
		return null;
	}

	if ( preg_match( '/(?:\bx\s*\'|0x[0-9a-f]+)/i', $sql ) ) {
		$reason = 'sqlite hex literal';
		return null;
	}

	if ( preg_match( '/\b(?:CAST|COLLATE|RAISE|LIKELY|UNLIKELY|LIKELIHOOD)\b/i', $sql ) ) {
		$reason = 'unsupported expression feature';
		return null;
	}

	$normalized = preg_replace( '/\bUPDATE\s+OR\s+(?:ABORT|FAIL|IGNORE|REPLACE|ROLLBACK)\s+/i', 'UPDATE ', $sql );
	$normalized = preg_replace( '/\bINSERT\s+OR\s+(?:ABORT|FAIL|IGNORE|REPLACE|ROLLBACK)\s+INTO\b/i', 'INSERT INTO', $normalized );

	if ( preg_match( '/\bSET\s*\(/i', $normalized ) ) {
		$reason = 'sqlite tuple assignment';
		return null;
	}

	return rtrim( $normalized, ';' ) . ';';
}

function trim_sql( $sql ) {
	return trim( rtrim( trim( $sql ), ';' ) );
}

function split_sql_statements( $sql ) {
	$statements = array();
	$current    = '';
	$in_string  = false;
	$length     = strlen( $sql );

	for ( $i = 0; $i < $length; ++$i ) {
		$char     = $sql[ $i ];
		$current .= $char;

		if ( "'" === $char ) {
			if ( $in_string && isset( $sql[ $i + 1 ] ) && "'" === $sql[ $i + 1 ] ) {
				$current .= $sql[ ++$i ];
				continue;
			}
			$in_string = ! $in_string;
			continue;
		}

		if ( ';' === $char && ! $in_string ) {
			$statement = trim( $current );
			if ( '' !== $statement ) {
				$statements[] = $statement;
			}
			$current = '';
		}
	}

	$tail = trim( $current );
	if ( '' !== $tail ) {
		$statements[] = rtrim( $tail, ';' ) . ';';
	}

	return $statements;
}

function replay_statements( $statements ) {
	$pdo_class = PHP_VERSION_ID >= 80400 ? PDO\SQLite::class : PDO::class;
	$pdo       = new $pdo_class( 'sqlite::memory:' );
	$driver    = new WP_SQLite_Driver(
		new WP_SQLite_Connection( array( 'pdo' => $pdo ) ),
		'wp'
	);

	$executed = array();
	foreach ( $statements as $index => $statement ) {
		try {
			$driver->query( $statement );
			$executed[] = $statement;
		} catch ( Throwable $e ) {
			return array(
				'executed' => $executed,
				'failure'  => array(
					'index'     => $index,
					'statement' => $statement,
					'class'     => get_class( $e ),
					'message'   => $e->getMessage(),
				),
			);
		}
	}

	return array(
		'executed' => $executed,
		'failure'  => null,
	);
}

function capture_failure_fixture( $capture_dir, $statements, $source_records, $failure ) {
	if ( ! is_dir( $capture_dir ) ) {
		mkdir( $capture_dir, 0777, true );
	}

	$prefix     = array_slice( $statements, 0, $failure['index'] );
	$schema     = array_values(
		array_filter(
			$prefix,
			function ( $statement ) {
				return preg_match( '/^\s*CREATE\s+TABLE\b/i', $statement );
			}
		)
	);
	$minimal    = array_merge( $schema, array( $failure['statement'] ) );
	$min_result = replay_statements( $minimal );

	if ( null === $min_result['failure'] ) {
		$minimal = array_merge( $prefix, array( $failure['statement'] ) );
	}

	$hash      = substr( sha1( implode( "\n", $minimal ) ), 0, 12 );
	$basename  = gmdate( 'Ymd\THis\Z' ) . "-{$hash}";
	$sql_file  = rtrim( $capture_dir, DIRECTORY_SEPARATOR ) . DIRECTORY_SEPARATOR . "{$basename}.sql";
	$json_file = rtrim( $capture_dir, DIRECTORY_SEPARATOR ) . DIRECTORY_SEPARATOR . "{$basename}.json";

	file_put_contents(
		$sql_file,
		"-- SQLancer WP_SQLite_Driver regression fixture\n" .
		"-- Failure: {$failure['class']}: " . str_replace( "\n", ' ', $failure['message'] ) . "\n\n" .
		implode( "\n", $minimal ) . "\n"
	);

	$record = isset( $source_records[ $failure['index'] ] ) ? $source_records[ $failure['index'] ] : null;
	file_put_contents(
		$json_file,
		json_encode(
			array(
				'failure' => $failure,
				'source'  => $record,
			),
			JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES
		) . "\n"
	);

	return array(
		'sql'  => $sql_file,
		'json' => $json_file,
	);
}

function format_failure( $failure ) {
	return "Unexpected replay failure at statement {$failure['index']}:\n" .
		"{$failure['class']}: {$failure['message']}\n" .
		"SQL: {$failure['statement']}";
}

function print_summary( $summary ) {
	echo "SQLancer SQLite replay summary\n";
	foreach ( $summary as $key => $value ) {
		if ( is_array( $value ) ) {
			if ( empty( $value ) ) {
				echo "  {$key}: none\n";
				continue;
			}
			echo "  {$key}:\n";
			arsort( $value );
			foreach ( $value as $reason => $count ) {
				echo "    {$reason}: {$count}\n";
			}
			continue;
		}
		echo "  {$key}: {$value}\n";
	}
}
