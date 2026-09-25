<?php

declare(strict_types=1);

namespace App\Services\Storage;

final class LocalStorage implements StorageInterface
{
    public function __construct(private readonly string $basePath)
    {
    }

    private function fullPath(string $relativePath): string
    {
        $relative = str_replace('\\', '/', $relativePath);
        // Path-Traversal ausschließen
        if (str_contains($relative, '..')) {
            throw new \InvalidArgumentException('Ungültiger Pfad.');
        }
        return rtrim($this->basePath, '/') . '/' . ltrim($relative, '/');
    }

    public function put(string $relativePath, string $content): void
    {
        $full = $this->fullPath($relativePath);
        $dir = dirname($full);
        if (!is_dir($dir) && !mkdir($dir, 0750, true) && !is_dir($dir)) {
            throw new \RuntimeException('Verzeichnis konnte nicht angelegt werden.');
        }
        if (file_put_contents($full, $content, LOCK_EX) === false) {
            throw new \RuntimeException('Datei konnte nicht gespeichert werden.');
        }
    }

    public function get(string $relativePath): string
    {
        $content = @file_get_contents($this->fullPath($relativePath));
        if ($content === false) {
            throw new \RuntimeException('Datei nicht lesbar: ' . $relativePath);
        }
        return $content;
    }

    public function delete(string $relativePath): void
    {
        $full = $this->fullPath($relativePath);
        if (is_file($full)) {
            @unlink($full);
        }
    }

    public function exists(string $relativePath): bool
    {
        return is_file($this->fullPath($relativePath));
    }
}
