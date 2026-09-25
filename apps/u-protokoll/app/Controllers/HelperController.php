<?php

declare(strict_types=1);

namespace App\Controllers;

use App\Core\Auth;
use App\Core\Database;
use App\Core\Request;
use App\Core\Response;
use App\Core\View;
use App\Repositories\ProtocolRepository as Repo;
use App\Services\HelperService;

/**
 * Gehilfenzugänge: Anlage durch die Hausverwaltung sowie die auf ein
 * Protokoll beschränkte Ansicht des Gehilfen selbst.
 */
final class HelperController
{
    /** Startseite eines Gehilfen: ausschließlich die zugewiesenen Protokolle. */
    public function home(): void
    {
        $rows = HelperService::protocolsOf((int) Auth::id());
        // Abgelaufene Zuweisungen bleiben sichtbar, aber ohne Zugriff
        $expired = static fn(array $r): bool => !empty($r['valid_until']) && strtotime((string) $r['valid_until']) <= time();
        $open = array_values(array_filter($rows, static fn(array $r): bool => !Repo::isLocked($r) && !$expired($r)));

        // Genau ein offenes Protokoll und keine Rückmeldung anzuzeigen: direkt in die Bearbeitung
        if (count($rows) === 1 && count($open) === 1 && empty($_SESSION['flash_success']) && empty($_SESSION['flash_error'])) {
            Response::redirect('/protocols/' . $open[0]['id'] . '/wizard/' . ($open[0]['current_step'] ?: 'object'));
        }
        View::page('helper/home', [
            'title'   => count($rows) > 1 ? 'Meine Übergaben' : 'Meine Übergabe',
            'rows'    => $rows,
            'open'    => count($open),
            'expired' => $expired,
        ]);
    }

    /**
     * Abschlussseite: PDF-Download und Versandstatus. Stornierte oder ohne
     * Abschluss geschlossene Protokolle werden neutral als geschlossen gezeigt.
     */
    public function done(string $id): void
    {
        $protocol = Repo::findOrFail((int) $id);
        if (!Repo::isLocked($protocol)) {
            Response::redirect('/protocols/' . $id . '/wizard/summary');
        }
        $dispatch = $_SESSION['completion_dispatch'][(int) $id] ?? null;
        unset($_SESSION['completion_dispatch'][(int) $id]);

        // Gehilfen sehen nur Versendungen an ihre eigene Adresse (Durchschriften),
        // nie manuelle Versendungen der Verwaltung an Dritte
        $emails = Auth::isHelper()
            ? Database::fetchAll(
                'SELECT recipients, status, sent_at FROM protocol_emails WHERE protocol_id = ? AND LOWER(TRIM(recipients)) = LOWER(?) ORDER BY id DESC LIMIT 20',
                [(int) $id, (string) (Auth::user()['email'] ?? '')]
            )
            : Database::fetchAll(
                'SELECT recipients, status, sent_at FROM protocol_emails WHERE protocol_id = ? ORDER BY id DESC LIMIT 20',
                [(int) $id]
            );

        View::page('helper/done', [
            'title'     => protocol_is_finalized($protocol) ? 'Übergabe abgeschlossen' : 'Protokoll geschlossen',
            'protocol'  => $protocol,
            'finalized' => protocol_is_finalized($protocol),
            'dispatch'  => $dispatch,
            'emails'    => $emails,
        ]);
    }

    /**
     * Serverseitige Rückfrage vor dem endgültigen Abschluss durch einen
     * Gehilfen (Ja/Nein, unabhängig von JavaScript), inklusive Hinweise.
     */
    public function confirm(string $id): void
    {
        $protocol = Repo::findOrFail((int) $id);
        if (Repo::isLocked($protocol)) {
            Response::redirect('/protocols/' . $id . '/done');
        }
        $full = Repo::loadFull((int) $id);
        View::page('helper/confirm', [
            'title'    => 'Übergabe abschließen',
            'protocol' => $protocol,
            'hints'    => completion_hints($full),
            'from'     => (string) Request::get('from', 'signatures'),
        ]);
    }

    /**
     * Gehilfen für ein bestehendes Protokoll anlegen oder einen vorhandenen
     * Gehilfen zusätzlich freischalten (aus der Protokollansicht).
     */
    public function createForProtocol(string $id): void
    {
        Auth::requireStaff();
        $protocol = Repo::findOrFail((int) $id);
        $redirect = '/protocols/' . $id;
        $target = $this->resolveTarget($redirect);
        $this->guardProtocolForHelper($protocol, $redirect);
        $this->grantAndNotify($protocol, $target, $redirect);
    }

    /**
     * Anlage mit automatischer Protokollvorlage (Benutzerverwaltung oder
     * Übersicht). Ohne bestehendes Protokoll wird eines angelegt; der Gehilfe
     * kann direkt als Beteiligter übernommen werden.
     */
    public function createWithTemplate(): void
    {
        Auth::requireStaff();
        $redirect = Request::post('return_to') === 'admin' && Auth::isAdmin() ? '/admin/users' : '/';
        $target = $this->resolveTarget($redirect);

        $protocolId = (int) Request::post('protocol_id', '0');
        if ($protocolId > 0) {
            $protocol = Repo::find($protocolId);
            if ($protocol === null) {
                $_SESSION['flash_error'] = 'Das Protokoll mit der ID ' . $protocolId . ' wurde nicht gefunden. Bitte die ID prüfen oder das Feld leer lassen.';
                Response::redirect($redirect);
            }
            $this->guardProtocolForHelper($protocol, $redirect);
        } else {
            $protocol = Repo::create((string) Request::post('protocol_type', 'rental'));
            $fields = array_intersect_key($_POST, array_flip(['street', 'house_number', 'postal_code', 'city', 'unit_number', 'handover_date']));
            if (array_filter($fields) !== []) {
                Repo::updateFields((int) $protocol['id'], $fields);
            }
            $this->addHelperAsParticipant((int) $protocol['id'], (string) $protocol['protocol_type'], $target);
            $protocol = Repo::find((int) $protocol['id']);
        }
        $this->grantAndNotify($protocol, $target, $redirect);
    }

    /** Zugang entziehen (Benutzer bleibt bestehen, Protokoll wird gesperrt). */
    public function revoke(string $id): void
    {
        Auth::requireStaff();
        Repo::findOrFail((int) $id);
        $userId = (int) Request::post('user_id', '0');
        HelperService::revokeAccess((int) $id, $userId);
        $_SESSION['flash_success'] = 'Der Zugang zu diesem Protokoll wurde entzogen.';
        Response::redirect('/protocols/' . $id);
    }

    /**
     * Neues Passwort erzeugen und Zugangsdaten erneut versenden. Aufruf aus
     * der Protokollansicht (mit Protokoll-ID, nur für dort zugewiesene
     * Gehilfen) oder aus der Benutzerverwaltung (nur Administratoren).
     */
    public function resendCredentials(?string $id = null): void
    {
        Auth::requireStaff();
        if ($id === null) {
            Auth::requireAdmin();
        }
        $redirect = $id !== null ? '/protocols/' . $id : '/admin/users';
        $userId = (int) Request::post('user_id', '0');
        $user = Database::fetch("SELECT * FROM users WHERE id = ? AND role = 'helper'", [$userId]);
        if ($user === null) {
            $_SESSION['flash_error'] = 'Gehilfe nicht gefunden.';
            Response::redirect($redirect);
        }
        if ((int) $user['is_active'] !== 1) {
            $_SESSION['flash_error'] = 'Dieser Gehilfenzugang ist deaktiviert. Bitte das Konto zuerst in der Benutzerverwaltung aktivieren.';
            Response::redirect($redirect);
        }

        $protocol = null;
        if ($id !== null) {
            $protocol = Repo::findOrFail((int) $id);
            if (!HelperService::hasAccess((int) $protocol['id'], $userId)) {
                $_SESSION['flash_error'] = 'Dieser Gehilfe ist diesem Protokoll nicht zugewiesen.';
                Response::redirect($redirect);
            }
        } else {
            // Aus der Benutzerverwaltung: eindeutig zugewiesenes Protokoll für die Anrede nutzen
            $assigned = HelperService::protocolsOf($userId);
            $protocol = count($assigned) === 1 ? $assigned[0] : null;
        }

        $password = HelperService::resetPassword($userId);
        $result = HelperService::sendCredentials($user, $password, $protocol);
        $this->flashCredentials($user, $password, $result);
        Response::redirect($redirect);
    }

    /**
     * Zieladresse prüfen und vorhandenen Gehilfen ermitteln, bevor irgendetwas
     * angelegt wird (kein verwaistes Protokoll bei Abbruch).
     *
     * @return array{email:string, existing:?array}
     */
    private function resolveTarget(string $redirect): array
    {
        $email = trim((string) Request::post('email', ''));
        if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
            $_SESSION['flash_error'] = 'Bitte eine gültige E-Mail-Adresse für den Gehilfenzugang angeben.';
            Response::redirect($redirect);
        }
        $existing = Database::fetch('SELECT * FROM users WHERE email = ?', [$email]);
        if ($existing !== null && $existing['role'] !== 'helper') {
            $_SESSION['flash_error'] = 'Diese E-Mail-Adresse gehört zu einem internen Benutzerkonto. Bitte eine andere Adresse verwenden.';
            Response::redirect($redirect);
        }
        if ($existing !== null && (int) $existing['is_active'] !== 1) {
            $_SESSION['flash_error'] = 'Dieser Gehilfenzugang ist deaktiviert. Bitte das Konto zuerst in der Benutzerverwaltung aktivieren.';
            Response::redirect($redirect);
        }
        if ($existing === null && Database::fetch('SELECT id FROM user_invitations WHERE email = ? AND accepted_at IS NULL', [$email]) !== null) {
            $_SESSION['flash_error'] = 'Für diese E-Mail-Adresse liegt eine offene Mitarbeiter-Einladung vor. Bitte zuerst die Einladung zurückziehen oder eine andere Adresse verwenden.';
            Response::redirect($redirect);
        }
        return ['email' => $email, 'existing' => $existing];
    }

    /** Gehilfenzugänge nur für noch bearbeitbare Protokolle. */
    private function guardProtocolForHelper(array $protocol, string $redirect): void
    {
        if (Repo::isLocked($protocol)) {
            $_SESSION['flash_error'] = 'Für abgeschlossene, archivierte oder stornierte Protokolle kann kein Gehilfenzugang angelegt werden.';
            Response::redirect($redirect);
        }
    }

    /** Gehilfen bei Anlage einer Vorlage als Beteiligten übernehmen (Auswahl im Formular). */
    private function addHelperAsParticipant(int $protocolId, string $protocolType, array $target): void
    {
        $side = (string) Request::post('participant_side', '');
        if (!in_array($side, ['in', 'out'], true)) {
            return;
        }
        [$outRole, $inRole] = party_roles($protocolType);
        Repo::saveEntity($protocolId, 'participant', [
            'role'       => $side === 'in' ? $inRole : $outRole,
            'first_name' => trim((string) Request::post('first_name', '')),
            'last_name'  => trim((string) Request::post('last_name', '')),
            'email'      => $target['email'],
            'sort_order' => 0,
        ]);
    }

    /**
     * Gemeinsamer Abschluss der Anlage: Benutzer anlegen oder vorhandenen
     * verwenden, Protokoll freischalten, per E-Mail informieren.
     *
     * @param array{email:string, existing:?array} $target
     */
    private function grantAndNotify(array $protocol, array $target, string $redirect): void
    {
        $existing = $target['existing'];
        if ($existing !== null) {
            if (HelperService::hasAccess((int) $protocol['id'], (int) $existing['id'])) {
                $_SESSION['flash_error'] = 'Dieser Gehilfe ist dem Protokoll bereits zugewiesen. Über "Zugangsdaten erneut senden" erhält er ein neues Passwort.';
                Response::redirect('/protocols/' . $protocol['id']);
            }
            // Vorhandener Gehilfe: Freischaltung ohne Passwortwechsel
            HelperService::grantAccess((int) $protocol['id'], (int) $existing['id']);
            $result = HelperService::sendAccessNotice($existing, $protocol);
            $_SESSION[$result['ok'] ? 'flash_success' : 'flash_error'] = $result['ok']
                ? 'Der bestehende Gehilfenzugang ' . $existing['username'] . ' wurde für dieses Protokoll freigeschaltet und per E-Mail informiert.'
                : 'Der Zugang wurde freigeschaltet, die Benachrichtigung an ' . $existing['email'] . ' konnte jedoch nicht versendet werden.';
            Response::redirect('/protocols/' . $protocol['id']);
        }

        $created = HelperService::createUser(
            $target['email'],
            trim((string) Request::post('first_name', '')),
            trim((string) Request::post('last_name', '')),
            (string) Request::post('helper_type', 'tenant')
        );
        HelperService::grantAccess((int) $protocol['id'], (int) $created['user']['id']);
        $result = HelperService::sendCredentials($created['user'], $created['password'], $protocol);
        $this->flashCredentials($created['user'], $created['password'], $result);
        Response::redirect('/protocols/' . $protocol['id']);
    }

    /** Erfolg melden; bei SMTP-Fehler die Zugangsdaten einmalig anzeigen. */
    private function flashCredentials(array $user, #[\SensitiveParameter] string $password, array $result): void
    {
        if ($result['ok']) {
            $_SESSION['flash_success'] = 'Zugangsdaten wurden an ' . $user['email'] . ' versendet (Benutzername: ' . $user['username'] . ').';
        } else {
            $_SESSION['flash_error'] = 'E-Mail-Versand fehlgeschlagen. Bitte die Zugangsdaten manuell weitergeben: Benutzername '
                . $user['username'] . ', Passwort ' . $password;
        }
    }
}
