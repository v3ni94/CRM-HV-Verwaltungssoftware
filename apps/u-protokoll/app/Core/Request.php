<?php

declare(strict_types=1);

namespace App\Core;

final class Request
{
    public static function wantsJson(): bool
    {
        $accept = $_SERVER['HTTP_ACCEPT'] ?? '';
        $xrw = $_SERVER['HTTP_X_REQUESTED_WITH'] ?? '';
        return str_contains($accept, 'application/json') || $xrw === 'XMLHttpRequest';
    }

    public static function post(string $key, ?string $default = null): ?string
    {
        $value = $_POST[$key] ?? $default;
        return is_string($value) ? trim($value) : $default;
    }

    public static function get(string $key, ?string $default = null): ?string
    {
        $value = $_GET[$key] ?? $default;
        return is_string($value) ? trim($value) : $default;
    }

    /** JSON-Body (für Autosave-Requests). */
    public static function jsonBody(): array
    {
        $raw = file_get_contents('php://input');
        $data = json_decode($raw ?: '', true);
        return is_array($data) ? $data : [];
    }

    public static function ip(): string
    {
        return $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
    }
}
