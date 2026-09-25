<?php

declare(strict_types=1);

namespace App\Controllers;

use App\Core\Audit;
use App\Core\Auth;
use App\Core\Database;
use App\Core\Request;
use App\Core\Response;
use App\Core\View;

/**
 * Administrationsbereich: Einstellungen, Benutzerverwaltung, Audit-Log.
 * SMTP-/SFTP-Zugangsdaten werden bewusst NICHT hier gepflegt, sondern
 * ausschließlich über die .env außerhalb des Webroots.
 */
final class AdminController
{
    private const EDITABLE_SETTINGS = [
        'company.name', 'company.brand_footer', 'company.street', 'company.phone',
        'company.email', 'company.website', 'company.register', 'company.ceo',
        'pdf.show_brand_footer', 'pdf.signature_consent',
        'email.default_subject', 'email.default_body',
        'email.helper_subject', 'email.helper_intro', 'email.helper_privacy',
        'email.completion_subject', 'email.completion_body',
        'helper.access_days', 'legal.privacy_url', 'legal.imprint_url',
        'upload.max_image_side', 'upload.jpeg_quality', 'retention.archive_years',
    ];

    public function index(): void
    {
        Auth::requireAdmin();
        $settings = [];
        foreach (Database::fetchAll('SELECT setting_key, setting_value FROM settings') as $row) {
            $settings[$row['setting_key']] = $row['setting_value'];
        }
        View::page('admin/settings', ['title' => 'Einstellungen', 'settings' => $settings]);
    }

    public function saveSettings(): void
    {
        Auth::requireAdmin();
        foreach (self::EDITABLE_SETTINGS as $key) {
            $field = str_replace('.', '_', $key);
            if (!isset($_POST[$field])) {
                continue;
            }
            Database::execute(
                'INSERT INTO settings (setting_key, setting_value, updated_by) VALUES (?, ?, ?)
                 ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value), updated_by = VALUES(updated_by)',
                [$key, trim((string) $_POST[$field]), Auth::id()]
            );
        }
        Audit::log('settings_changed', 'settings');
        $_SESSION['flash_success'] = 'Einstellungen gespeichert.';
        Response::redirect('/admin');
    }

    public function users(): void
    {
        Auth::requireAdmin();
        $editId = (int) (Request::get('edit', '0'));
        View::page('admin/users', [
            'title'       => 'Benutzerverwaltung',
            'users'       => Database::fetchAll("SELECT u.*, b.name AS branch FROM users u LEFT JOIN branches b ON b.id = u.branch_id WHERE u.role <> 'helper' ORDER BY u.username"),
            'branches'    => Database::fetchAll('SELECT * FROM branches WHERE is_active = 1 ORDER BY name'),
            'editUser'    => $editId ? Database::fetch('SELECT * FROM users WHERE id = ?', [$editId]) : null,
            'invitations' => Database::fetchAll('SELECT i.*, b.name AS branch FROM user_invitations i LEFT JOIN branches b ON b.id = i.branch_id WHERE i.accepted_at IS NULL ORDER BY i.created_at DESC'),
            'helpers'     => Database::fetchAll(
                "SELECT u.*, (SELECT GROUP_CONCAT(p.protocol_number ORDER BY p.id SEPARATOR ', ')
                    FROM protocol_access a JOIN protocols p ON p.id = a.protocol_id WHERE a.user_id = u.id) AS protocols
                 FROM users u WHERE u.role = 'helper' ORDER BY u.created_at DESC"
            ),
        ]);
    }

    /** Mitarbeiter per E-Mail einladen: Einladung anlegen und Link versenden. */
    public function inviteUser(): void
    {
        Auth::requireAdmin();
        $email = (string) Request::post('email', '');
        if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
            $_SESSION['flash_error'] = 'Bitte eine gültige E-Mail-Adresse angeben.';
            Response::redirect('/admin/users');
        }
        if (Database::fetch('SELECT id FROM users WHERE email = ?', [$email])) {
            $_SESSION['flash_error'] = 'Für diese E-Mail-Adresse existiert bereits ein Benutzer.';
            Response::redirect('/admin/users');
        }
        // Offene Einladungen an dieselbe Adresse ersetzen
        Database::execute('DELETE FROM user_invitations WHERE email = ? AND accepted_at IS NULL', [$email]);

        $token = bin2hex(random_bytes(32));
        Database::insert('user_invitations', [
            'email'      => $email,
            'first_name' => Request::post('first_name') ?: null,
            'last_name'  => Request::post('last_name') ?: null,
            'role'       => in_array(Request::post('role'), ['admin', 'employee', 'caretaker', 'readonly'], true) ? Request::post('role') : 'employee',
            'branch_id'  => Request::post('branch_id') !== '' ? (int) Request::post('branch_id') : null,
            'token_hash' => hash('sha256', $token),
            'expires_at' => date('Y-m-d H:i:s', time() + 7 * 86400),
            'created_by' => Auth::id(),
        ]);
        Audit::log('user_invited', 'user_invitations', null, null, null, $email);

        $link = rtrim((string) \App\Core\Config::get('app.url'), '/') . url('/invite/' . $token);
        $body = "Guten Tag" . (Request::post('first_name') ? ' ' . Request::post('first_name') . ' ' . Request::post('last_name') : '') . ",\n\n"
            . "Sie wurden zu U-Protokoll, dem digitalen Übergabeprotokoll der Hausverwaltung Müller GmbH, eingeladen.\n\n"
            . "Bitte richten Sie Ihren Zugang über folgenden Link ein (gültig für 7 Tage):\n\n"
            . $link . "\n\n"
            . "Mit freundlichen Grüßen\n\nHausverwaltung Müller GmbH";
        $result = \App\Services\MailService::sendRaw($email, 'Ihre Einladung zu U-Protokoll', $body);

        if ($result['ok']) {
            $_SESSION['flash_success'] = 'Einladung wurde an ' . $email . ' versendet.';
        } else {
            // SMTP nicht erreichbar: Link anzeigen, damit er manuell weitergegeben werden kann
            $_SESSION['flash_error'] = 'E-Mail-Versand fehlgeschlagen. Einladungslink zum manuellen Weitergeben: ' . $link;
        }
        Response::redirect('/admin/users');
    }

    /** Einladung erneut versenden: neuer Token, neue 7-Tage-Frist. */
    public function resendInvitation(): void
    {
        Auth::requireAdmin();
        $id = (int) Request::post('invitation_id', '0');
        $invitation = Database::fetch('SELECT * FROM user_invitations WHERE id = ? AND accepted_at IS NULL', [$id]);
        if ($invitation === null) {
            $_SESSION['flash_error'] = 'Einladung nicht gefunden oder bereits angenommen.';
            Response::redirect('/admin/users');
        }

        $token = bin2hex(random_bytes(32));
        Database::update('user_invitations', [
            'token_hash' => hash('sha256', $token),
            'expires_at' => date('Y-m-d H:i:s', time() + 7 * 86400),
        ], 'id = ?', [$id]);
        Audit::log('invitation_resent', 'user_invitations', $id, null, null, $invitation['email']);

        $link = rtrim((string) \App\Core\Config::get('app.url'), '/') . url('/invite/' . $token);
        $body = "Guten Tag" . ($invitation['first_name'] ? ' ' . $invitation['first_name'] . ' ' . $invitation['last_name'] : '') . ",\n\n"
            . "hier ist Ihr neuer Einladungslink zu U-Protokoll, dem digitalen Übergabeprotokoll der Hausverwaltung Müller GmbH.\n\n"
            . "Bitte richten Sie Ihren Zugang über folgenden Link ein (gültig für 7 Tage):\n\n"
            . $link . "\n\n"
            . "Ein früher versendeter Einladungslink ist damit ungültig.\n\n"
            . "Mit freundlichen Grüßen\n\nHausverwaltung Müller GmbH";
        $result = \App\Services\MailService::sendRaw($invitation['email'], 'Ihre Einladung zu U-Protokoll', $body);

        if ($result['ok']) {
            $_SESSION['flash_success'] = 'Einladung wurde erneut an ' . $invitation['email'] . ' versendet (7 Tage gültig).';
        } else {
            $_SESSION['flash_error'] = 'E-Mail-Versand fehlgeschlagen. Einladungslink zum manuellen Weitergeben: ' . $link;
        }
        Response::redirect('/admin/users');
    }

    public function deleteInvitation(): void
    {
        Auth::requireAdmin();
        $id = (int) Request::post('invitation_id', '0');
        Database::execute('DELETE FROM user_invitations WHERE id = ?', [$id]);
        Audit::log('invitation_deleted', 'user_invitations', $id);
        $_SESSION['flash_success'] = 'Einladung wurde zurückgezogen.';
        Response::redirect('/admin/users');
    }

    public function saveUser(): void
    {
        Auth::requireAdmin();
        $userId = (int) (Request::post('user_id', '0'));
        $old = $userId > 0 ? Database::fetch('SELECT * FROM users WHERE id = ?', [$userId]) : null;
        if ($userId > 0 && $old === null) {
            $_SESSION['flash_error'] = 'Benutzer nicht gefunden.';
            Response::redirect('/admin/users');
        }
        $role = (string) Request::post('role', 'employee');
        if (!array_key_exists($role, user_roles())) {
            $role = 'employee';
        }
        // Gehilfen entstehen nur über die Gehilfenanlage und behalten ihre Rolle;
        // interne Konten werden nicht zu Gehilfen und umgekehrt
        if ($old !== null && $old['role'] === 'helper') {
            $role = 'helper';
        } elseif ($role === 'helper') {
            $_SESSION['flash_error'] = 'Gehilfenzugänge werden über das Formular "Gehilfenzugang anlegen" erstellt.';
            Response::redirect('/admin/users');
        }
        $data = [
            'username'   => trim((string) Request::post('username', '')),
            'email'      => trim((string) Request::post('email', '')),
            'first_name' => Request::post('first_name') ?: null,
            'last_name'  => Request::post('last_name') ?: null,
            'role'       => $role,
            'branch_id'  => Request::post('branch_id') !== '' && Request::post('branch_id') !== null ? (int) Request::post('branch_id') : null,
            'is_active'  => Request::post('is_active') === '1' ? 1 : 0,
        ];
        if ($data['username'] === '' || !filter_var($data['email'], FILTER_VALIDATE_EMAIL)) {
            $_SESSION['flash_error'] = 'Benutzername und eine gültige E-Mail-Adresse sind erforderlich.';
            Response::redirect('/admin/users');
        }
        $conflict = Database::fetch(
            'SELECT id FROM users WHERE (username = ? OR email = ?) AND id <> ?',
            [$data['username'], $data['email'], $userId]
        );
        if ($conflict !== null) {
            $_SESSION['flash_error'] = 'Benutzername oder E-Mail-Adresse ist bereits vergeben.';
            Response::redirect($userId > 0 ? '/admin/users?edit=' . $userId . '#user-form' : '/admin/users#user-form');
        }
        $password = (string) ($_POST['password'] ?? '');
        if ($password !== '') {
            if (mb_strlen($password) < 10) {
                $_SESSION['flash_error'] = 'Das Passwort muss mindestens 10 Zeichen haben.';
                Response::redirect('/admin/users');
            }
            $data['password_hash'] = password_hash($password, PASSWORD_DEFAULT);
        }

        if ($userId > 0) {
            Database::update('users', $data, 'id = ?', [$userId]);
            // Nachvollziehbarkeit: Rollen-, Sperr- und Stammdatenänderungen mit Alt- und Neuwert (nie Passwörter)
            $track = ['username', 'email', 'role', 'branch_id', 'is_active'];
            $oldValues = array_intersect_key($old, array_flip($track));
            $newValues = array_intersect_key($data, array_flip($track));
            $changed = array_keys(array_filter($newValues, static fn($v, $k) => (string) ($oldValues[$k] ?? '') !== (string) ($v ?? ''), ARRAY_FILTER_USE_BOTH));
            Audit::log(
                'user_updated',
                'users',
                $userId,
                null,
                $changed !== [] ? json_encode(array_intersect_key($oldValues, array_flip($changed)), JSON_UNESCAPED_UNICODE) : null,
                $changed !== [] ? json_encode(array_intersect_key($newValues, array_flip($changed)), JSON_UNESCAPED_UNICODE) . (isset($data['password_hash']) ? ' (Passwort neu gesetzt)' : '') : (isset($data['password_hash']) ? 'Passwort neu gesetzt' : null)
            );
        } else {
            if (!isset($data['password_hash'])) {
                $_SESSION['flash_error'] = 'Für neue Benutzer ist ein Passwort erforderlich.';
                Response::redirect('/admin/users');
            }
            $userId = Database::insert('users', $data);
            Audit::log('user_created', 'users', $userId);
        }
        $_SESSION['flash_success'] = 'Benutzer gespeichert.';
        Response::redirect('/admin/users');
    }

    public function audit(): void
    {
        Auth::requireAdmin();
        $page = max(1, (int) Request::get('page', '1'));
        $perPage = 50;
        $protocolId = Request::get('protocol_id');
        $where = '';
        $params = [];
        if ($protocolId) {
            $where = 'WHERE protocol_id = ?';
            $params[] = (int) $protocolId;
        }
        $rows = Database::fetchAll(
            "SELECT * FROM audit_log $where ORDER BY id DESC LIMIT $perPage OFFSET " . (($page - 1) * $perPage),
            $params
        );
        View::page('admin/audit', ['title' => 'Audit-Log', 'rows' => $rows, 'page' => $page]);
    }
}
