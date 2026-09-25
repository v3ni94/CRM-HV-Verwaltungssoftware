<?php

declare(strict_types=1);

namespace App\Core;

final class Response
{
    public static function redirect(string $path): never
    {
        header('Location: ' . url($path));
        exit;
    }

    public static function json(array $data, int $status = 200): never
    {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode($data, JSON_UNESCAPED_UNICODE);
        exit;
    }

    public static function html(string $html, int $status = 200): never
    {
        http_response_code($status);
        header('Content-Type: text/html; charset=utf-8');
        echo $html;
        exit;
    }

    public static function download(string $content, string $filename, string $mime, bool $inline = false): never
    {
        header('Content-Type: ' . $mime);
        header('Content-Length: ' . strlen($content));
        header('X-Content-Type-Options: nosniff');
        $disposition = $inline ? 'inline' : 'attachment';
        header("Content-Disposition: $disposition; filename=\"" . rawurlencode($filename) . '"');
        echo $content;
        exit;
    }
}
