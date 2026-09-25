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

/**
 * Mehrstufiger Assistent. Kein inhaltliches Feld ist Pflicht; jeder Schritt
 * kann übersprungen werden. Autosave speichert nach Feldwechsel per JSON.
 */
final class WizardController
{
    public function step(string $id, string $step): void
    {
        $steps = visible_wizard_steps();
        if (!isset($steps[$step])) {
            Response::redirect('/protocols/' . $id . '/wizard/object');
        }
        $full = Repo::loadFull((int) $id);
        $protocol = $full['protocol'];

        if (Repo::isLocked($protocol)) {
            Response::redirect('/protocols/' . $id);
        }
        // zuletzt bearbeiteten Schritt merken (Fortsetzen von Entwürfen);
        // reines Ansehen durch Nur-Lesen-Benutzer verändert nichts
        if (Auth::canWrite() && $protocol['current_step'] !== $step) {
            Database::update('protocols', ['current_step' => $step], 'id = ?', [$protocol['id']]);
        }

        View::page('wizard/' . $step, [
            'title'    => ($protocol['protocol_number'] ?? '') . ': ' . $steps[$step],
            'step'     => $step,
            'steps'    => $steps,
            'isWizard' => true,
        ] + $full);
    }

    /** Klassischer POST eines Schrittes (Weiter/Zurück/Speichern ohne JS). */
    public function saveStep(string $id, string $step): void
    {
        Auth::requireWrite();
        $protocol = Repo::findOrFail((int) $id);
        if (Repo::isLocked($protocol)) {
            Response::redirect('/protocols/' . $id);
        }

        if (!isset(visible_wizard_steps()[$step])) {
            Response::redirect('/protocols/' . $id . '/wizard/object');
        }
        $data = $_POST;
        // Checkbox nur auswerten, wenn ihr Formular sie tatsächlich enthält
        if (isset($_POST['hide_time_information_present'])) {
            $data['hide_time_information'] = isset($_POST['hide_time_information']) ? '1' : '0';
        } else {
            unset($data['hide_time_information']);
        }
        Repo::updateFields((int) $id, $data);
        Audit::log('fields_changed', 'protocols', (int) $id, (int) $id, null, 'Schritt ' . $step);

        $target = (string) Request::post('_nav', 'next');
        $steps = array_keys(visible_wizard_steps());
        $index = array_search($step, $steps, true);
        $next = match ($target) {
            'back' => $steps[max(0, (int) $index - 1)],
            'stay' => $step,
            'exit' => null,
            default => $steps[min(count($steps) - 1, (int) $index + 1)],
        };
        if ($target !== 'exit' && str_starts_with($target, 'goto:')) {
            $goto = substr($target, 5);
            $next = in_array($goto, $steps, true) ? $goto : $next;
        }
        if ($next === null) {
            $_SESSION['flash_success'] = 'Ihre Eingaben wurden gespeichert. Sie können die Bearbeitung jederzeit fortsetzen.';
            Response::redirect(Auth::isHelper() ? '/meine-uebergabe' : '/');
        }
        Response::redirect('/protocols/' . $id . '/wizard/' . $next);
    }

    /** Autosave per fetch(): JSON mit Feldwerten, Antwort mit Zeitstempel. */
    public function autosave(string $id): void
    {
        Auth::requireWrite();
        $protocol = Repo::findOrFail((int) $id);
        if (Repo::isLocked($protocol)) {
            Response::json(['ok' => false, 'error' => 'Protokoll ist abgeschlossen und schreibgeschützt.'], 409);
        }
        $data = Request::jsonBody();
        $fields = $data['fields'] ?? [];
        if (is_array($fields) && $fields !== []) {
            $stringFields = [];
            foreach ($fields as $k => $v) {
                if (is_scalar($v) || $v === null) {
                    $stringFields[(string) $k] = $v === null ? '' : (string) $v;
                }
            }
            Repo::updateFields((int) $id, $stringFields);
        }
        Response::json(['ok' => true, 'saved_at' => date('H:i')]);
    }
}
