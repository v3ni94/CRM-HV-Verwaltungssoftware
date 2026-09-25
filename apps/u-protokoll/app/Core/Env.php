<?php

declare(strict_types=1);

namespace App\Core;

/**
 * Minimaler .env-Loader. Die .env liegt außerhalb des Webroots und
 * enthält sämtliche Zugangsdaten (DB, SMTP, SFTP).
 */
final class Env
{
    private static array $vars = [];

    public static function load(string $file): void
    {
        if (!is_file($file)) {
            return;
        }
        foreach (file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
            $line = trim($line);
            if ($line === '' || str_starts_with($line, '#') || !str_contains($line, '=')) {
                continue;
            }
            [$key, $value] = explode('=', $line, 2);
            $key = trim($key);
            $value = trim($value);
            if (strlen($value) >= 2 && ($value[0] === '"' || $value[0] === "'") && str_ends_with($value, $value[0])) {
                $value = substr($value, 1, -1);
            }
            self::$vars[$key] = $value;
        }
    }

    public static function get(string $key, ?string $default = null): ?string
    {
        $fromServer = getenv($key);
        if ($fromServer !== false && $fromServer !== '') {
            return $fromServer;
        }
        return self::$vars[$key] ?? $default;
    }
}
