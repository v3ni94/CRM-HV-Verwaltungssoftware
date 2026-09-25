<?php

declare(strict_types=1);

namespace App\Services;

use App\Core\Audit;
use App\Core\Auth;
use App\Core\Config;
use App\Core\Database;
use App\Core\Logger;
use App\Services\Storage\Storage;

/**
 * Gehilfenzugänge: externe Personen (Mieter, Eigentümer, Beauftragte), die
 * genau die ihnen zugewiesenen Protokolle ausfüllen, unterschreiben und
 * abschließen dürfen. Anlage erzeugt Benutzer, Passwort, Protokollzuweisung
 * und versendet die Zugangsdaten per E-Mail.
 */
final class HelperService
{
    /** Zeichen ohne Verwechslungsgefahr (kein O/0, I/l/1). */
    private const PASSWORD_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789';

    public static function generatePassword(int $length = 12): string
    {
        $max = strlen(self::PASSWORD_CHARS) - 1;
        $out = '';
        for ($i = 0; $i < $length; $i++) {
            $out .= self::PASSWORD_CHARS[random_int(0, $max)];
        }
        return $out . '!';
    }

    /** Freien Benutzernamen aus Vor- und Nachname ableiten. */
    public static function buildUsername(string $firstName, string $lastName, string $email): string
    {
        $slug = static function (string $value): string {
            $value = strtr(mb_strtolower(trim($value)), ['ä' => 'ae', 'ö' => 'oe', 'ü' => 'ue', 'ß' => 'ss']);
            return preg_replace('/[^a-z0-9]/', '', $value) ?? '';
        };
        $first = $slug($firstName);
        $last = $slug($lastName);
        $base = $first !== '' && $last !== ''
            ? mb_substr($first, 0, 1) . '.' . $last
            : ($last !== '' ? $last : $slug((string) strstr($email, '@', true)));
        $base = $base !== '' ? mb_substr($base, 0, 60) : 'gehilfe';

        $candidate = $base;
        for ($i = 2; Database::fetch('SELECT id FROM users WHERE username = ?', [$candidate]) !== null; $i++) {
            $candidate = $base . $i;
        }
        return $candidate;
    }

    /**
     * Legt einen Gehilfenbenutzer an (ohne Protokollzuweisung).
     *
     * @return array{user:array, password:string}
     */
    public static function createUser(string $email, string $firstName, string $lastName, string $helperType): array
    {
        $type = in_array($helperType, ['helper', 'tenant', 'owner'], true) ? $helperType : 'helper';
        $password = self::generatePassword();
        $username = self::buildUsername($firstName, $lastName, $email);

        $userId = Database::insert('users', [
            'username'      => $username,
            'email'         => $email,
            'password_hash' => password_hash($password, PASSWORD_DEFAULT),
            'first_name'    => $firstName !== '' ? $firstName : null,
            'last_name'     => $lastName !== '' ? $lastName : null,
            'role'          => 'helper',
            'helper_type'   => $type,
            'is_active'     => 1,
        ]);
        Audit::log('helper_created', 'users', $userId, null, null, $email);

        return ['user' => Database::fetch('SELECT * FROM users WHERE id = ?', [$userId]), 'password' => $password];
    }

    /** Weist einem Gehilfen ein Protokoll zu (idempotent, hebt ein früheres Gültigkeitsende auf). */
    public static function grantAccess(int $protocolId, int $userId): void
    {
        Database::execute(
            'INSERT INTO protocol_access (protocol_id, user_id, granted_by, valid_until) VALUES (?, ?, ?, NULL)
             ON DUPLICATE KEY UPDATE granted_by = VALUES(granted_by), valid_until = NULL',
            [$protocolId, $userId, Auth::id()]
        );
        Audit::log('helper_access_granted', 'protocol_access', $userId, $protocolId);
    }

    public static function revokeAccess(int $protocolId, int $userId): void
    {
        Database::execute('DELETE FROM protocol_access WHERE protocol_id = ? AND user_id = ?', [$protocolId, $userId]);
        Audit::log('helper_access_revoked', 'protocol_access', $userId, $protocolId);
    }

    public static function hasAccess(int $protocolId, int $userId): bool
    {
        return Database::fetch('SELECT id FROM protocol_access WHERE protocol_id = ? AND user_id = ?', [$protocolId, $userId]) !== null;
    }

    /**
     * Nach dem Abschluss endet der Zugriff der Gehilfen automatisch nach der
     * eingestellten Frist (helper.access_days, 0 = sofort, leer = unbegrenzt).
     */
    public static function limitAccessAfterCompletion(int $protocolId): ?string
    {
        // Rohwert lesen: ein gespeicherter Leerstring bedeutet "unbegrenzt", kein Eintrag bedeutet Standard 30 Tage
        $row = Database::fetch("SELECT setting_value FROM settings WHERE setting_key = 'helper.access_days'");
        $daysSetting = $row === null ? '30' : trim((string) ($row['setting_value'] ?? ''));
        if ($daysSetting === '' || !ctype_digit($daysSetting)) {
            return null;
        }
        $until = date('Y-m-d H:i:s', time() + ((int) $daysSetting) * 86400);
        Database::execute(
            'UPDATE protocol_access SET valid_until = ? WHERE protocol_id = ? AND valid_until IS NULL',
            [$until, $protocolId]
        );
        Audit::log('helper_access_expiry', 'protocol_access', null, $protocolId, null, $until);
        return $until;
    }

    /** Setzt ein neues Passwort und liefert es im Klartext zurück. */
    public static function resetPassword(int $userId): string
    {
        $password = self::generatePassword();
        Database::update('users', [
            'password_hash' => password_hash($password, PASSWORD_DEFAULT),
            'failed_logins' => 0,
            'locked_until'  => null,
        ], 'id = ?', [$userId]);
        Audit::log('helper_password_reset', 'users', $userId);
        return $password;
    }

    /** @return array<int, array> Gehilfen mit Zugriff auf ein Protokoll */
    public static function forProtocol(int $protocolId): array
    {
        return Database::fetchAll(
            'SELECT u.*, a.created_at AS granted_at, a.valid_until, a.granted_by FROM protocol_access a
             JOIN users u ON u.id = a.user_id
             WHERE a.protocol_id = ? ORDER BY a.id',
            [$protocolId]
        );
    }

    /** @return array<int, array> Protokolle, die einem Gehilfen zugewiesen sind */
    public static function protocolsOf(int $userId): array
    {
        return Database::fetchAll(
            'SELECT p.*, a.valid_until FROM protocol_access a JOIN protocols p ON p.id = a.protocol_id
             WHERE a.user_id = ? ORDER BY p.handover_date IS NULL, p.handover_date, p.id',
            [$userId]
        );
    }

    /** Kopfzeile aller E-Mails an Gehilfen. */
    private static function salutation(array $user): string
    {
        $name = trim(($user['first_name'] ?? '') . ' ' . ($user['last_name'] ?? ''));
        return 'Guten Tag' . ($name !== '' ? ' ' . $name : '') . ",\n\n";
    }

    /** Fußzeile mit Kontakt und Datenschutzhinweis. */
    private static function footer(): string
    {
        $contact = company_contact_line();
        $privacy = trim(mail_text('email.helper_privacy', true));
        return ($contact !== '' ? "Bei Fragen erreichen Sie uns unter: " . $contact . "\n\n" : '')
            . "Mit freundlichen Grüßen\n\nHausverwaltung Müller GmbH"
            . ($privacy !== '' ? "\n\n" . $privacy : '');
    }

    /**
     * Versendet die Zugangsdaten mit kurzer Anleitung.
     *
     * @return array{ok:bool, error:?string}
     */
    public static function sendCredentials(array $user, #[\SensitiveParameter] string $password, ?array $protocol): array
    {
        $loginUrl = rtrim((string) Config::get('app.url'), '/') . url('/login');
        if ($protocol !== null) {
            $intro = MailService::renderTemplate(mail_text('email.helper_intro'), $protocol);
            $subject = MailService::renderTemplate(mail_text('email.helper_subject'), $protocol);
        } else {
            // Ohne eindeutiges Protokoll keine Platzhalter verwenden
            $intro = 'Über den folgenden Zugang können Sie Ihr Übergabeprotokoll digital ausfüllen, unterschreiben und abschließen.';
            $subject = 'Ihr Zugang zu U-Protokoll';
        }

        $body = self::salutation($user)
            . $intro . "\n\n"
            . "So gehen Sie vor:\n"
            . "1. Öffnen Sie diesen Link: " . $loginUrl . "\n"
            . "2. Geben Sie Benutzername und Passwort ein.\n"
            . "3. Füllen Sie das Protokoll aus, erfassen Sie die Unterschriften und schließen Sie es am Ende ab.\n\n"
            . 'Benutzername: ' . $user['username'] . "\n"
            . 'Passwort: ' . $password . "\n\n"
            . "Bitte bewahren Sie die Zugangsdaten sorgfältig auf und geben Sie sie nicht weiter. Nach der Anmeldung können Sie das Passwort über den Menüpunkt Passwort ändern.\n\n"
            . "Nach dem Abschluss erhalten Sie das fertige Protokoll automatisch als PDF per E-Mail. Ein Abschluss ist endgültig, danach sind keine Änderungen mehr möglich.\n\n"
            . self::footer();

        $result = MailService::sendRaw((string) $user['email'], $subject, $body);
        if (!$result['ok']) {
            Logger::error('Versand der Gehilfen-Zugangsdaten fehlgeschlagen: ' . (string) $result['error'], ['user' => $user['id']]);
        }
        return $result;
    }

    /**
     * Information eines bestehenden Gehilfen über ein weiteres freigeschaltetes
     * Protokoll, ohne das Passwort zu ändern.
     *
     * @return array{ok:bool, error:?string}
     */
    public static function sendAccessNotice(array $user, array $protocol): array
    {
        $loginUrl = rtrim((string) Config::get('app.url'), '/') . url('/login');
        $subject = MailService::renderTemplate(mail_text('email.helper_subject'), $protocol);
        $body = self::salutation($user)
            . 'Ihr bestehender Zugang zu U-Protokoll wurde für ein weiteres Übergabeprotokoll freigeschaltet'
            . (protocol_address($protocol) !== '' ? ' (Objekt ' . protocol_address($protocol) . ')' : '') . ".\n\n"
            . "Ihre Zugangsdaten bleiben unverändert. Anmeldung: " . $loginUrl . "\n"
            . 'Benutzername: ' . $user['username'] . "\n\n"
            . "Falls Sie Ihr Passwort nicht mehr kennen, wenden Sie sich bitte an die Hausverwaltung, wir senden Ihnen neue Zugangsdaten.\n\n"
            . self::footer();
        $result = MailService::sendRaw((string) $user['email'], $subject, $body);
        Audit::log('helper_access_notice', 'users', (int) $user['id'], (int) $protocol['id'], null, (string) $user['email']);
        return $result;
    }

    /**
     * Versendet das abgeschlossene Protokoll automatisch an alle Beteiligten
     * mit hinterlegter E-Mail-Adresse sowie an die aktiven zugewiesenen
     * Gehilfen. Jeder Empfänger erhält eine eigene E-Mail. Fehlversuche werden
     * in der Versandhistorie protokolliert, damit die Verwaltung sie sieht.
     *
     * @param array $full Ergebnis von ProtocolRepository::loadUnfiltered()
     * @return array{sent:string[], failed:string[], skipped:string[], error:bool}
     */
    public static function sendCompletionCopies(array $full): array
    {
        $protocol = $full['protocol'];
        $protocolId = (int) $protocol['id'];
        $recipients = [];
        $skipped = [];
        foreach ($full['participants'] as $participant) {
            $email = trim((string) ($participant['email'] ?? ''));
            if ($email === '') {
                continue;
            }
            if (filter_var($email, FILTER_VALIDATE_EMAIL)) {
                $recipients[mb_strtolower($email)] = $email;
            } else {
                $skipped[] = $email;
            }
        }
        foreach (self::forProtocol($protocolId) as $helper) {
            if ((int) ($helper['is_active'] ?? 0) !== 1) {
                continue; // gesperrte Zugänge erhalten keine Durchschrift
            }
            $email = trim((string) ($helper['email'] ?? ''));
            if ($email !== '' && filter_var($email, FILTER_VALIDATE_EMAIL)) {
                $recipients[mb_strtolower($email)] = $email;
            }
        }

        $subject = MailService::renderTemplate(mail_text('email.completion_subject'), $protocol);
        $body = MailService::renderTemplate(mail_text('email.completion_body'), $protocol);

        // Formal ungültige Adressen sichtbar in der Versandhistorie festhalten
        foreach ($skipped as $email) {
            self::logFailedDispatch($protocolId, $email, $subject, $body, 'Formal ungültige E-Mail-Adresse, kein Versand', null);
        }
        if ($recipients === []) {
            return ['sent' => [], 'failed' => [], 'skipped' => $skipped, 'error' => false];
        }

        // Gespeicherte Version anhängen, sonst frisch erzeugen
        $version = Database::fetch(
            'SELECT v.id, f.storage_path, f.original_filename FROM protocol_versions v
             JOIN protocol_files f ON f.id = v.pdf_file_id
             WHERE v.protocol_id = ? ORDER BY v.id DESC LIMIT 1',
            [$protocolId]
        );
        $versionId = $version !== null ? (int) $version['id'] : null;
        try {
            if ($version !== null) {
                $pdf = Storage::driver()->get($version['storage_path']);
                $pdfName = $version['original_filename'];
            } else {
                $pdf = PdfService::htmlToPdf(\App\Core\View::render('pdf/protocol', $full + ['forPdf' => true]));
                $pdfName = PdfService::filename($protocol);
            }
        } catch (\Throwable $e) {
            Logger::error('PDF für automatischen Versand nicht verfügbar: ' . $e->getMessage(), ['protocol' => $protocolId]);
            foreach ($recipients as $email) {
                self::logFailedDispatch($protocolId, $email, $subject, $body, 'PDF für den Versand nicht verfügbar', $versionId);
            }
            return ['sent' => [], 'failed' => array_values($recipients), 'skipped' => $skipped, 'error' => true];
        }
        $attachments = [['content' => $pdf, 'filename' => $pdfName, 'mime' => 'application/pdf']];

        $sent = [];
        $failed = [];
        $connectionDown = false;
        foreach ($recipients as $email) {
            if ($connectionDown) {
                // Server nicht erreichbar: restliche Empfänger ohne erneuten Verbindungsversuch protokollieren
                self::logFailedDispatch($protocolId, $email, $subject, $body, 'SMTP-Server nicht erreichbar', $versionId);
                $failed[] = $email;
                continue;
            }
            $result = MailService::send($protocol, [$email], [], [], $subject, $body, $attachments, $versionId);
            if ($result['ok']) {
                $sent[] = $email;
            } else {
                $failed[] = $email;
                $error = (string) ($result['error'] ?? '');
                if (stripos($error, 'SMTP connect') !== false || stripos($error, 'Could not connect') !== false) {
                    $connectionDown = true;
                }
            }
        }
        if ($sent !== []) {
            Database::execute("UPDATE protocols SET status = 'sent' WHERE id = ? AND status = 'completed'", [$protocolId]);
        }
        return ['sent' => $sent, 'failed' => $failed, 'skipped' => $skipped, 'error' => false];
    }

    /**
     * Interne Benachrichtigung der Hausverwaltung nach einem Abschluss durch
     * einen Gehilfen: an den anlegenden Mitarbeiter, sonst an den Ersteller
     * des Protokolls, sonst an die zentrale Adresse aus den Einstellungen.
     *
     * @param array{sent:string[], failed:string[], skipped:string[], error:bool} $dispatch
     */
    public static function notifyStaffOfCompletion(array $protocol, array $dispatch): void
    {
        $protocolId = (int) $protocol['id'];
        $address = null;
        $grant = Database::fetch(
            "SELECT u.email FROM protocol_access a JOIN users u ON u.id = a.granted_by
             WHERE a.protocol_id = ? AND u.is_active = 1 AND u.email <> '' ORDER BY a.id DESC LIMIT 1",
            [$protocolId]
        );
        if ($grant !== null) {
            $address = $grant['email'];
        } elseif (!empty($protocol['created_by'])) {
            $creator = Database::fetch('SELECT email FROM users WHERE id = ? AND is_active = 1', [(int) $protocol['created_by']]);
            $address = $creator['email'] ?? null;
        }
        if (!$address) {
            $address = trim((string) Config::setting('company.email', ''));
        }
        if ($address === '' || $address === null || !filter_var($address, FILTER_VALIDATE_EMAIL)) {
            Logger::error('Keine interne Empfängeradresse für die Abschlussbenachrichtigung.', ['protocol' => $protocolId]);
            return;
        }

        $user = Auth::user() ?? [];
        $helperName = trim(($user['first_name'] ?? '') . ' ' . ($user['last_name'] ?? '')) ?: ($user['username'] ?? 'Gehilfe');
        $link = rtrim((string) Config::get('app.url'), '/') . url('/protocols/' . $protocolId);
        $lines = [
            'Guten Tag,',
            '',
            'das Übergabeprotokoll ' . ($protocol['protocol_number'] ?? protocol_number($protocolId))
                . (protocol_address($protocol) !== '' ? ' (' . protocol_address($protocol) . ')' : '')
                . ' wurde soeben durch den Gehilfenzugang "' . $helperName . '" abgeschlossen und festgeschrieben.',
            '',
            'Automatischer Versand der Durchschrift:',
            '  Zugestellt an: ' . ($dispatch['sent'] !== [] ? implode(', ', $dispatch['sent']) : 'niemand'),
        ];
        if ($dispatch['failed'] !== []) {
            $lines[] = '  Fehlgeschlagen: ' . implode(', ', $dispatch['failed']);
        }
        if ($dispatch['skipped'] !== []) {
            $lines[] = '  Übersprungen (ungültige Adresse): ' . implode(', ', $dispatch['skipped']);
        }
        if ($dispatch['error']) {
            $lines[] = '  Hinweis: Der Versand ist technisch fehlgeschlagen, bitte manuell nachholen.';
        }
        $lines[] = '';
        $lines[] = 'Zur Protokollansicht: ' . $link;
        $lines[] = '';
        $lines[] = 'Diese Nachricht wurde automatisch von U-Protokoll erzeugt.';

        $result = MailService::sendRaw($address, 'Abschluss durch Gehilfen: ' . ($protocol['protocol_number'] ?? protocol_number($protocolId)), implode("\n", $lines));
        if ($result['ok']) {
            Audit::log('staff_notified', 'protocols', $protocolId, $protocolId, null, $address);
        } else {
            Logger::error('Abschlussbenachrichtigung an die Hausverwaltung fehlgeschlagen: ' . (string) $result['error'], ['protocol' => $protocolId]);
        }
    }

    /** Fehlversuch in der Versandhistorie festhalten (ohne SMTP-Verbindung). */
    private static function logFailedDispatch(int $protocolId, string $recipient, string $subject, string $body, string $error, ?int $versionId): void
    {
        Database::insert('protocol_emails', [
            'protocol_id'         => $protocolId,
            'protocol_version_id' => $versionId,
            'sender'              => Config::get('smtp.from'),
            'recipients'          => $recipient,
            'subject'             => mb_substr($subject, 0, 255),
            'body'                => $body,
            'status'              => 'failed',
            'error_message'       => $error,
            'sent_by'             => Auth::id(),
        ]);
        Audit::log('email_failed', 'protocol_emails', null, $protocolId, null, $recipient);
    }
}
