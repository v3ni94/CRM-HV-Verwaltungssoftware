<?php

declare(strict_types=1);

namespace App\Core;

/**
 * Anmeldung, Rollen und Login-Rate-Limiting.
 */
final class Auth
{
    private const MAX_ATTEMPTS_PER_IP = 10;   // pro 15 Minuten
    private const LOCK_AFTER_FAILURES = 6;    // Kontosperre
    private const LOCK_MINUTES = 15;

    public static function check(): bool
    {
        return isset($_SESSION['user_id']);
    }

    public static function user(): ?array
    {
        if (!self::check()) {
            return null;
        }
        static $user = null;
        if ($user === null) {
            $user = Database::fetch('SELECT * FROM users WHERE id = ? AND is_active = 1', [$_SESSION['user_id']]);
            if ($user === null) {
                self::logout();
            }
        }
        return $user;
    }

    public static function id(): ?int
    {
        return isset($_SESSION['user_id']) ? (int) $_SESSION['user_id'] : null;
    }

    public static function isAdmin(): bool
    {
        return (self::user()['role'] ?? '') === 'admin';
    }

    /** Gehilfe (Mieter, Eigentümer, Beauftragter): Zugriff nur auf zugewiesene Protokolle. */
    public static function isHelper(): bool
    {
        return (self::user()['role'] ?? '') === 'helper';
    }

    /**
     * Interne Rollen der Hausverwaltung (alles außer Gehilfen). Fail-closed:
     * ein gesperrter oder gelöschter Benutzer mit noch laufender Sitzung ist
     * kein Mitarbeiter.
     */
    public static function isStaff(): bool
    {
        $user = self::user();
        return $user !== null && $user['role'] !== 'helper';
    }

    public static function canWrite(): bool
    {
        return in_array(self::user()['role'] ?? '', ['admin', 'employee', 'caretaker', 'helper'], true);
    }

    public static function requireAdmin(): void
    {
        if (!self::isAdmin()) {
            self::deny();
        }
    }

    /** Aktionen, die Gehilfen nie ausführen dürfen (Anlage, Versionen, Versand, Export). */
    public static function requireStaff(): void
    {
        if (!self::isStaff() || !self::canWrite()) {
            self::deny();
        }
    }

    /** IDs der Protokolle, die einem Gehilfen zugewiesen sind. */
    public static function assignedProtocolIds(): array
    {
        $id = self::id();
        if ($id === null) {
            return [];
        }
        $rows = Database::fetchAll('SELECT protocol_id FROM protocol_access WHERE user_id = ?', [$id]);
        return array_map(static fn(array $r): int => (int) $r['protocol_id'], $rows);
    }

    public static function canAccessProtocol(int $protocolId): bool
    {
        $user = self::user();
        if ($user === null) {
            return false; // gesperrt oder gelöscht: fail-closed, auch bei laufender Sitzung
        }
        if ($user['role'] !== 'helper') {
            return true;
        }
        return Database::fetch(
            'SELECT id FROM protocol_access WHERE user_id = ? AND protocol_id = ?
             AND (valid_until IS NULL OR valid_until > NOW())',
            [(int) $user['id'], $protocolId]
        ) !== null;
    }

    /**
     * Zentrale Zugriffsprüfung für ein einzelnes Protokoll. Wird vom
     * Repository bei jedem Laden aufgerufen, damit kein Controller sie
     * versehentlich auslassen kann.
     */
    public static function requireProtocolAccess(int $protocolId): void
    {
        if (!self::canAccessProtocol($protocolId)) {
            self::deny();
        }
    }

    /** Einheitliche Ablehnung: JSON für Fetch-Aufrufe, sonst Fehlerseite im Layout. */
    public static function deny(string $message = 'Für diese Aktion oder dieses Protokoll besteht keine Berechtigung.'): never
    {
        if (Request::wantsJson()) {
            Response::json(['ok' => false, 'error' => 'Keine Berechtigung.'], 403);
        }
        $content = View::render('layout/error', [
            'heading' => 'Kein Zugriff',
            'message' => $message,
            'backUrl' => self::isHelper() ? url('/meine-uebergabe') : url('/'),
        ]);
        Response::html(View::render('layout/main', ['title' => 'Kein Zugriff', 'content' => $content]), 403);
    }

    public static function requireWrite(): void
    {
        if (!self::canWrite()) {
            if (Request::wantsJson()) {
                Response::json(['ok' => false, 'error' => 'Keine Schreibberechtigung.'], 403);
            }
            self::deny('Ihr Konto hat nur Leserechte. Änderungen sind nicht möglich.');
        }
    }

    public static function attempt(string $username, #[\SensitiveParameter] string $password): bool|string
    {
        $ip = Request::ip();
        $recent = Database::fetch(
            'SELECT COUNT(*) AS c FROM login_attempts WHERE ip_address = ? AND success = 0 AND created_at > (NOW() - INTERVAL 15 MINUTE)',
            [$ip]
        );
        if ((int) ($recent['c'] ?? 0) >= self::MAX_ATTEMPTS_PER_IP) {
            return 'Zu viele Fehlversuche. Bitte warten Sie einige Minuten.';
        }

        $user = Database::fetch('SELECT * FROM users WHERE (username = ? OR email = ?) AND is_active = 1', [$username, $username]);

        if ($user && $user['locked_until'] !== null && strtotime($user['locked_until']) > time()) {
            return 'Konto vorübergehend gesperrt. Bitte später erneut versuchen.';
        }

        $ok = $user && password_verify($password, $user['password_hash']);
        Database::insert('login_attempts', ['ip_address' => $ip, 'username' => mb_substr($username, 0, 80), 'success' => $ok ? 1 : 0]);

        if (!$ok) {
            if ($user) {
                $failures = (int) $user['failed_logins'] + 1;
                $locked = $failures >= self::LOCK_AFTER_FAILURES
                    ? date('Y-m-d H:i:s', time() + self::LOCK_MINUTES * 60)
                    : null;
                Database::update('users', ['failed_logins' => $failures, 'locked_until' => $locked], 'id = ?', [$user['id']]);
            }
            return false;
        }

        if (password_needs_rehash($user['password_hash'], PASSWORD_DEFAULT)) {
            Database::update('users', ['password_hash' => password_hash($password, PASSWORD_DEFAULT)], 'id = ?', [$user['id']]);
        }
        Database::update('users', ['failed_logins' => 0, 'locked_until' => null, 'last_login_at' => date('Y-m-d H:i:s')], 'id = ?', [$user['id']]);

        session_regenerate_id(true);
        $_SESSION['user_id'] = (int) $user['id'];
        Audit::log('login', 'user', (int) $user['id']);
        return true;
    }

    public static function logout(): void
    {
        $_SESSION = [];
        if (ini_get('session.use_cookies')) {
            $p = session_get_cookie_params();
            setcookie(session_name(), '', time() - 42000, $p['path'], $p['domain'], $p['secure'], $p['httponly']);
        }
        session_destroy();
    }
}
