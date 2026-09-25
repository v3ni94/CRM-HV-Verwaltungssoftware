<?php

declare(strict_types=1);

namespace App\Core;

/**
 * Statische Konfiguration aus .env, ergänzt um DB-gestützte Einstellungen
 * (Tabelle settings), die administrativ gepflegt werden.
 */
final class Config
{
    private static array $config = [];
    private static ?array $dbSettings = null;

    public static function init(): void
    {
        self::$config = [
            'app.name'     => 'U-Protokoll',
            'app.url'      => Env::get('APP_URL', 'https://u-protokoll.muellerhv.de'),
            'app.debug'    => Env::get('APP_DEBUG', '0') === '1',
            'app.timezone' => Env::get('APP_TIMEZONE', 'Europe/Berlin'),

            'db.host'     => Env::get('DB_HOST', 'localhost'),
            'db.port'     => Env::get('DB_PORT', '3306'),
            'db.name'     => Env::get('DB_NAME', 'u_protokoll'),
            'db.user'     => Env::get('DB_USER', ''),
            'db.password' => Env::get('DB_PASSWORD', ''),

            'smtp.host'       => Env::get('SMTP_HOST', ''),
            'smtp.port'       => (int) Env::get('SMTP_PORT', '587'),
            'smtp.encryption' => Env::get('SMTP_ENCRYPTION', 'tls'),
            'smtp.user'       => Env::get('SMTP_USER', ''),
            'smtp.password'   => Env::get('SMTP_PASSWORD', ''),
            'smtp.from'       => Env::get('SMTP_FROM', 'u-protokoll@muellerhv.de'),
            'smtp.from_name'  => Env::get('SMTP_FROM_NAME', 'Hausverwaltung Müller GmbH'),
            'smtp.reply_to'   => Env::get('SMTP_REPLY_TO', ''),

            'storage.driver'    => Env::get('STORAGE_DRIVER', 'local'), // local | sftp
            'storage.base_path' => Env::get('STORAGE_BASE_PATH', BASE_PATH . '/storage/uploads'),
            'sftp.host'      => Env::get('SFTP_HOST', ''),
            'sftp.port'      => (int) Env::get('SFTP_PORT', '22'),
            'sftp.user'      => Env::get('SFTP_USER', ''),
            'sftp.password'  => Env::get('SFTP_PASSWORD', ''),
            'sftp.key_file'  => Env::get('SFTP_KEY_FILE', ''),
            'sftp.base_path' => Env::get('SFTP_BASE_PATH', '/u-protokoll'),
        ];
    }

    public static function get(string $key, mixed $default = null): mixed
    {
        return self::$config[$key] ?? $default;
    }

    /** Einstellung aus der Datenbank (Tabelle settings), lazy geladen. */
    public static function setting(string $key, ?string $default = null): ?string
    {
        if (self::$dbSettings === null) {
            try {
                self::$dbSettings = [];
                foreach (Database::get()->query('SELECT setting_key, setting_value FROM settings') as $row) {
                    self::$dbSettings[$row['setting_key']] = $row['setting_value'];
                }
            } catch (\Throwable) {
                self::$dbSettings = [];
            }
        }
        $value = self::$dbSettings[$key] ?? null;
        return ($value === null || $value === '') ? $default : $value;
    }
}
