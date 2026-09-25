<?php

declare(strict_types=1);

namespace App\Services\Storage;

use App\Core\Config;
use App\Core\Logger;

/**
 * SFTP-Speicher auf Basis von phpseclib (composer: phpseclib/phpseclib).
 * Zugangsdaten kommen ausschließlich aus der .env.
 */
final class SftpStorage implements StorageInterface
{
    private ?object $sftp = null;

    public function __construct(private readonly string $basePath)
    {
    }

    private function connection(): object
    {
        if ($this->sftp !== null) {
            return $this->sftp;
        }
        if (!class_exists(\phpseclib3\Net\SFTP::class)) {
            throw new \RuntimeException('phpseclib ist nicht installiert (composer install ausführen).');
        }
        $sftp = new \phpseclib3\Net\SFTP(Config::get('sftp.host'), Config::get('sftp.port'));
        $keyFile = (string) Config::get('sftp.key_file');
        if ($keyFile !== '' && is_file($keyFile)) {
            $key = \phpseclib3\Crypt\PublicKeyLoader::load(file_get_contents($keyFile), (string) Config::get('sftp.password'));
            $ok = $sftp->login(Config::get('sftp.user'), $key);
        } else {
            $ok = $sftp->login(Config::get('sftp.user'), Config::get('sftp.password'));
        }
        if (!$ok) {
            Logger::error('SFTP-Login fehlgeschlagen', ['host' => Config::get('sftp.host')]);
            throw new \RuntimeException('SFTP-Verbindung fehlgeschlagen.');
        }
        return $this->sftp = $sftp;
    }

    private function fullPath(string $relativePath): string
    {
        if (str_contains($relativePath, '..')) {
            throw new \InvalidArgumentException('Ungültiger Pfad.');
        }
        return rtrim($this->basePath, '/') . '/' . ltrim($relativePath, '/');
    }

    public function put(string $relativePath, string $content): void
    {
        $sftp = $this->connection();
        $full = $this->fullPath($relativePath);
        $sftp->mkdir(dirname($full), 0750, true);
        if (!$sftp->put($full, $content)) {
            throw new \RuntimeException('SFTP-Upload fehlgeschlagen.');
        }
    }

    public function get(string $relativePath): string
    {
        $content = $this->connection()->get($this->fullPath($relativePath));
        if (!is_string($content)) {
            throw new \RuntimeException('SFTP-Datei nicht lesbar: ' . $relativePath);
        }
        return $content;
    }

    public function delete(string $relativePath): void
    {
        $this->connection()->delete($this->fullPath($relativePath), false);
    }

    public function exists(string $relativePath): bool
    {
        return (bool) $this->connection()->file_exists($this->fullPath($relativePath));
    }
}
