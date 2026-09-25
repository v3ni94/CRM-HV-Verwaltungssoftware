<?php

declare(strict_types=1);

namespace App\Services\Storage;

/**
 * Abstraktion des Dateispeichers. Große Dateien liegen nie in MariaDB,
 * sondern lokal oder auf SFTP; die DB hält nur Metadaten und Pfade.
 */
interface StorageInterface
{
    /** Legt Inhalt unter dem relativen Pfad ab (Verzeichnisse werden angelegt). */
    public function put(string $relativePath, string $content): void;

    public function get(string $relativePath): string;

    public function delete(string $relativePath): void;

    public function exists(string $relativePath): bool;
}
