<?php

declare(strict_types=1);

namespace App\Core;

use PDO;

/**
 * PDO-Verbindung (MariaDB, utf8mb4) mit Query-Hilfsmethoden.
 * Ausschließlich Prepared Statements verwenden.
 */
final class Database
{
    private static ?PDO $pdo = null;

    public static function get(): PDO
    {
        if (self::$pdo === null) {
            $dsn = sprintf(
                'mysql:host=%s;port=%s;dbname=%s;charset=utf8mb4',
                Config::get('db.host'),
                Config::get('db.port'),
                Config::get('db.name')
            );
            self::$pdo = new PDO($dsn, Config::get('db.user'), Config::get('db.password'), [
                PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                PDO::ATTR_EMULATE_PREPARES   => false,
            ]);
        }
        return self::$pdo;
    }

    public static function fetch(string $sql, array $params = []): ?array
    {
        $stmt = self::get()->prepare($sql);
        $stmt->execute($params);
        $row = $stmt->fetch();
        return $row === false ? null : $row;
    }

    public static function fetchAll(string $sql, array $params = []): array
    {
        $stmt = self::get()->prepare($sql);
        $stmt->execute($params);
        return $stmt->fetchAll();
    }

    public static function execute(string $sql, array $params = []): int
    {
        $stmt = self::get()->prepare($sql);
        $stmt->execute($params);
        return $stmt->rowCount();
    }

    public static function insert(string $table, array $data): int
    {
        $cols = array_keys($data);
        $sql = sprintf(
            'INSERT INTO `%s` (`%s`) VALUES (%s)',
            $table,
            implode('`,`', $cols),
            implode(',', array_fill(0, count($cols), '?'))
        );
        self::execute($sql, array_values($data));
        return (int) self::get()->lastInsertId();
    }

    public static function update(string $table, array $data, string $where, array $whereParams): int
    {
        $set = implode(',', array_map(fn($c) => "`$c` = ?", array_keys($data)));
        return self::execute("UPDATE `$table` SET $set WHERE $where", [...array_values($data), ...$whereParams]);
    }
}
