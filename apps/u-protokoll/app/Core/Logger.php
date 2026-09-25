<?php

declare(strict_types=1);

namespace App\Core;

/**
 * Datei-Logger (storage/logs/app-YYYY-MM-DD.log).
 * Technische Details gehören ins Log, nie in die Ausgabe.
 */
final class Logger
{
    public static function log(string $level, string $message, array $context = []): void
    {
        $line = sprintf(
            "[%s] %s: %s %s\n",
            date('Y-m-d H:i:s'),
            strtoupper($level),
            $message,
            $context ? json_encode($context, JSON_UNESCAPED_UNICODE) : ''
        );
        @file_put_contents(BASE_PATH . '/storage/logs/app-' . date('Y-m-d') . '.log', $line, FILE_APPEND | LOCK_EX);
    }

    public static function info(string $message, array $context = []): void
    {
        self::log('info', $message, $context);
    }

    public static function error(string $message, array $context = []): void
    {
        self::log('error', $message, $context);
    }
}
