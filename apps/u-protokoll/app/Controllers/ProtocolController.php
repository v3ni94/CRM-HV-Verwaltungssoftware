<?php

declare(strict_types=1);

namespace App\Controllers;

use App\Core\Audit;
use App\Core\Auth;
use App\Core\Database;
use App\Core\Request;
use App\Core\Response;
use App\Core\View;
use App\Repositories\ProtocolRepository as Repo;
use App\Services\HelperService;
use App\Services\PdfService;

final class ProtocolController
{
    public function create(): void
    {
        Auth::requireStaff();
        $protocol = Repo::create((string) Request::post('protocol_type', 'rental'));
        Response::redirect('/protocols/' . $protocol['id'] . '/wizard/object');
    }

    public function show(string $id): void
    {
        $protocol = Repo::findOrFail((int) $id);
        // Gehilfen sehen keine Verwaltungsansicht: entweder Bearbeitung oder Abschlussseite
        if (Auth::isHelper()) {
            Response::redirect(Repo::isLocked($protocol)
                ? '/protocols/' . $id . '/done'
                : '/protocols/' . $id . '/wizard/' . ($protocol['current_step'] ?: 'object'));
        }
        $full = Repo::loadFull((int) $id);
        Audit::log('protocol_opened', 'protocols', (int) $id, (int) $id);
        // Änderungshistorie: wer hat wann was geändert (ohne reine Öffnungs-Einträge)
        $changes = Database::fetchAll(
            "SELECT username, action, created_at FROM audit_log
             WHERE protocol_id = ? AND action NOT IN ('protocol_opened')
             ORDER BY id DESC LIMIT 100",
            [(int) $id]
        );
        View::page('protocol/show', [
            'title'   => $full['protocol']['protocol_number'] ?? 'Protokoll',
            'changes' => $changes,
            'helpers' => HelperService::forProtocol((int) $id),
        ] + $full);
    }

    public function duplicate(string $id): void
    {
        Auth::requireStaff();
        $source = Repo::findOrFail((int) $id);
        $options = [
            'object' => Request::post('copy_object') === '1',
            'rooms'  => Request::post('copy_rooms') === '1',
            'meters' => Request::post('copy_meters') === '1',
            'keys'   => Request::post('copy_keys') === '1',
        ];
        $new = Repo::duplicate($source, $options);
        Response::redirect('/protocols/' . $new['id'] . '/wizard/object');
    }

    /** Sammel-Archivierung aus der Übersicht (nur Administratoren). */
    public function bulkArchive(): void
    {
        Auth::requireAdmin();
        $ids = array_filter(array_map('intval', (array) ($_POST['ids'] ?? [])));
        if ($ids === []) {
            $_SESSION['flash_error'] = 'Keine Protokolle ausgewählt.';
            Response::redirect('/protocols');
        }
        $count = 0;
        foreach ($ids as $id) {
            $protocol = Repo::find($id);
            if ($protocol === null || $protocol['status'] === 'archived') {
                continue;
            }
            Database::update('protocols', [
                'status'      => 'archived',
                'archived_at' => date('Y-m-d H:i:s'),
                'updated_by'  => Auth::id(),
            ], 'id = ?', [$id]);
            Audit::log('protocol_archived', 'protocols', $id, $id, $protocol['status'], 'archived');
            $count++;
        }
        $_SESSION['flash_success'] = $count . ' Protokoll(e) archiviert. Über den Filter "Archivierte anzeigen" bleiben sie erreichbar.';
        Response::redirect('/protocols');
    }

    public function archive(string $id): void
    {
        Auth::requireAdmin();
        $protocol = Repo::findOrFail((int) $id);
        Database::update('protocols', ['status' => 'archived', 'archived_at' => date('Y-m-d H:i:s'), 'updated_by' => Auth::id()], 'id = ?', [$protocol['id']]);
        Audit::log('protocol_archived', 'protocols', (int) $id, (int) $id, $protocol['status'], 'archived');
        Response::redirect('/protocols/' . $id);
    }

    /** Archivierung rückgängig machen: vorherigen Status wiederherstellen. */
    public function unarchive(string $id): void
    {
        Auth::requireAdmin();
        $protocol = Repo::findOrFail((int) $id);
        if ($protocol['status'] !== 'archived') {
            Response::redirect('/protocols/' . $id);
        }
        // Vorherigen Status aus dem Audit-Log der Archivierung übernehmen
        $lastArchive = Database::fetch(
            "SELECT old_value FROM audit_log WHERE protocol_id = ? AND action = 'protocol_archived' ORDER BY id DESC LIMIT 1",
            [(int) $id]
        );
        $previous = $lastArchive['old_value'] ?? null;
        if (!in_array($previous, array_keys(protocol_statuses()), true) || $previous === 'archived') {
            $previous = $protocol['completed_at'] ? 'completed' : 'in_progress';
        }
        Database::update('protocols', [
            'status'      => $previous,
            'archived_at' => null,
            'updated_by'  => Auth::id(),
        ], 'id = ?', [$protocol['id']]);
        Audit::log('protocol_unarchived', 'protocols', (int) $id, (int) $id, 'archived', $previous);
        $_SESSION['flash_success'] = 'Protokoll wurde aus dem Archiv zurückgeholt (Status: ' . protocol_statuses()[$previous] . ').';
        Response::redirect('/protocols/' . $id);
    }

    public function cancel(string $id): void
    {
        Auth::requireStaff();
        $protocol = Repo::findOrFail((int) $id);
        if (in_array($protocol['status'], ['completed', 'sent', 'archived'], true) && !Auth::isAdmin()) {
            Response::html('<p>Abgeschlossene Protokolle können nur durch Administratoren storniert werden.</p>', 403);
        }
        Database::update('protocols', ['status' => 'cancelled', 'updated_by' => Auth::id()], 'id = ?', [$protocol['id']]);
        Audit::log('protocol_cancelled', 'protocols', (int) $id, (int) $id, $protocol['status'], 'cancelled');
        Response::redirect('/protocols/' . $id);
    }

    public function newVersion(string $id): void
    {
        Auth::requireStaff();
        $source = Repo::findOrFail((int) $id);
        if (!in_array($source['status'], ['completed', 'sent', 'archived'], true)) {
            Response::html('<p>Eine neue Version ist nur für abgeschlossene Protokolle möglich.</p>', 400);
        }
        $reason = (string) Request::post('change_reason', '');
        $new = Repo::createNewVersion($source, $reason);
        Response::redirect('/protocols/' . $new['id'] . '/wizard/summary');
    }

    /**
     * Abschluss: Daten fixieren, PDF erzeugen, Version registrieren.
     * Mitarbeiter: Liegen Hinweise vor, zeigt der erste Versuch die Hinweise,
     * erst die Bestätigung mit force=1 schließt trotz Hinweisen ab.
     * Gehilfen: serverseitige Rückfrage (Ja/Nein) auf einer eigenen Seite,
     * danach automatischer Versand der Durchschrift und Information der HVM.
     */
    public function complete(string $id): void
    {
        Auth::requireWrite();
        $protocol = Repo::findOrFail((int) $id);
        if (Repo::isLocked($protocol)) {
            Response::redirect('/protocols/' . $id);
        }

        $full = Repo::loadFull((int) $id);
        $hints = completion_hints($full);
        $from = (string) Request::post('from', 'signatures');
        $steps = wizard_steps();

        if (Auth::isHelper()) {
            if (Request::post('confirmed') !== '1') {
                Response::redirect('/protocols/' . $id . '/confirm?from=' . urlencode(isset($steps[$from]) ? $from : 'signatures'));
            }
        } elseif ($hints !== [] && Request::post('force') !== '1') {
            $_SESSION['completion_hints'] = $hints;
            Response::redirect('/protocols/' . $id . '/wizard/' . (isset($steps[$from]) ? $from : 'signatures'));
        }
        unset($_SESSION['completion_hints']);

        Database::update('protocols', [
            'status'       => 'completed',
            'completed_at' => date('Y-m-d H:i:s'),
            'completed_by' => Auth::id(),
            'updated_by'   => Auth::id(),
        ], 'id = ?', [$protocol['id']]);
        Audit::log('protocol_completed', 'protocols', (int) $id, (int) $id, $protocol['status'], 'completed');

        $completed = null;
        try {
            $completed = Repo::loadUnfiltered((int) $id); // Status ist jetzt "completed"
            PdfService::generate($completed, $protocol['version'] > 1 ? ($protocol['change_reason'] ?? null) : null);
        } catch (\Throwable $e) {
            \App\Core\Logger::error('PDF-Erzeugung beim Abschluss fehlgeschlagen: ' . $e->getMessage(), ['protocol' => $id]);
            $_SESSION['flash_error'] = 'Das Protokoll wurde abgeschlossen, die PDF-Erzeugung ist jedoch fehlgeschlagen. Bitte erneut über "PDF anzeigen" versuchen.';
        }

        // Automatische Durchschrift, sobald Gehilfen beteiligt sind, unabhängig davon,
        // wer den Abschluss auslöst (die Zugangsmail sagt den Versand zu)
        $helpers = HelperService::forProtocol((int) $id);
        if ($helpers !== [] || Auth::isHelper()) {
            $dispatch = ['sent' => [], 'failed' => [], 'skipped' => [], 'error' => true];
            if ($completed !== null) {
                try {
                    $dispatch = HelperService::sendCompletionCopies($completed);
                } catch (\Throwable $e) {
                    \App\Core\Logger::error('Automatischer Versand nach Abschluss fehlgeschlagen: ' . $e->getMessage(), ['protocol' => $id]);
                    Audit::log('completion_dispatch_failed', 'protocols', (int) $id, (int) $id);
                }
            }
            HelperService::limitAccessAfterCompletion((int) $id);

            if (Auth::isHelper()) {
                try {
                    HelperService::notifyStaffOfCompletion(Repo::find((int) $id) ?? $protocol, $dispatch);
                } catch (\Throwable $e) {
                    \App\Core\Logger::error('Abschlussbenachrichtigung fehlgeschlagen: ' . $e->getMessage(), ['protocol' => $id]);
                }
                $_SESSION['completion_dispatch'] = [(int) $id => $dispatch];
                Response::redirect('/protocols/' . $id . '/done');
            }

            if ($dispatch['error']) {
                $_SESSION['flash_error'] = trim(($_SESSION['flash_error'] ?? '') . ' Der automatische Versand an die Beteiligten ist fehlgeschlagen, bitte manuell über "E-Mail" nachholen.');
            } else {
                $_SESSION['flash_success'] = 'Protokoll abgeschlossen. Durchschrift versendet an: '
                    . ($dispatch['sent'] !== [] ? implode(', ', $dispatch['sent']) : 'niemand (keine gültige Adresse)')
                    . ($dispatch['failed'] !== [] ? '. Fehlgeschlagen: ' . implode(', ', $dispatch['failed']) : '') . '.';
            }
        }

        Response::redirect('/protocols/' . $id);
    }

    /** Browserbasierte Druckansicht (identisches Template wie das PDF). */
    public function printView(string $id): void
    {
        $full = Repo::loadFull((int) $id);
        Response::html(View::render('pdf/protocol', $full + ['forPdf' => false]));
    }
}
