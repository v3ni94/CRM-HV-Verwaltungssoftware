<?php
/**
 * Datenbank-Migrationen ausführen:
 *   php bin/migrate.php            – ausstehende Migrationen anwenden
 *   php bin/migrate.php --seed     – zusätzlich Beispieldaten einspielen
 */

declare(strict_types=1);

define('BASE_PATH', dirname(__DIR__));
require BASE_PATH . '/app/Core/helpers.php';
require BASE_PATH . '/app/Core/Env.php';
require BASE_PATH . '/app/Core/Config.php';
require BASE_PATH . '/app/Core/Database.php';

\App\Core\Env::load(BASE_PATH . '/.env');
\App\Core\Config::init();

$pdo = \App\Core\Database::get();
$pdo->exec('CREATE TABLE IF NOT EXISTS migrations (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    filename VARCHAR(255) NOT NULL,
    applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id), UNIQUE KEY uq_migrations_filename (filename)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');

$applied = [];
foreach ($pdo->query('SELECT filename FROM migrations') as $row) {
    $applied[$row['filename']] = true;
}

$files = glob(BASE_PATH . '/database/migrations/*.sql') ?: [];
sort($files);
foreach ($files as $file) {
    $name = basename($file);
    if (isset($applied[$name])) {
        echo "Übersprungen (bereits angewendet): $name\n";
        continue;
    }
    echo "Wende an: $name … ";
    run_sql_file($pdo, $file);
    $stmt = $pdo->prepare('INSERT INTO migrations (filename) VALUES (?)');
    $stmt->execute([$name]);
    echo "OK\n";
}

if (in_array('--seed', $argv, true)) {
    foreach (glob(BASE_PATH . '/database/seeds/*.sql') ?: [] as $seed) {
        echo 'Seed: ' . basename($seed) . " … ";
        run_sql_file($pdo, $seed);
        echo "OK\n";
    }
}

echo "Fertig.\n";

/**
 * Führt eine SQL-Datei Statement für Statement aus, damit Fehler
 * einzelner Statements nicht verschluckt werden. Statements enden
 * mit ";" am Zeilenende; Semikolons in Stringliteralen der
 * mitgelieferten Dateien kommen so nicht vor.
 */
function run_sql_file(PDO $pdo, string $file): void
{
    $sql = (string) file_get_contents($file);
    foreach (preg_split('/;\s*\n/', $sql) as $statement) {
        $statement = trim($statement);
        // Reine Kommentar-/Leerblöcke überspringen
        $withoutComments = trim((string) preg_replace('/^--.*$/m', '', $statement));
        if ($withoutComments === '') {
            continue;
        }
        $pdo->exec($statement);
    }
}
