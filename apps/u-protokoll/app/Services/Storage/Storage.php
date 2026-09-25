<?php

declare(strict_types=1);

namespace App\Services\Storage;

use App\Core\Config;

final class Storage
{
    private static ?StorageInterface $instance = null;

    public static function driver(): StorageInterface
    {
        if (self::$instance === null) {
            self::$instance = Config::get('storage.driver') === 'sftp'
                ? new SftpStorage((string) Config::get('sftp.base_path'))
                : new LocalStorage((string) Config::get('storage.base_path'));
        }
        return self::$instance;
    }

    /**
     * Relatives Zielverzeichnis eines Protokolls, z. B. 2026/000001/photos
     * (Protokoll-ID mit führenden Nullen).
     */
    public static function protocolDir(int $protocolId, string $subDir, ?string $createdAt = null): string
    {
        $year = $createdAt ? date('Y', strtotime($createdAt)) : date('Y');
        return sprintf('%s/%06d/%s', $year, $protocolId, trim($subDir, '/'));
    }
}
