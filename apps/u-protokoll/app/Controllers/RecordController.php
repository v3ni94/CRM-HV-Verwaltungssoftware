<?php

declare(strict_types=1);

namespace App\Controllers;

use App\Core\Auth;
use App\Core\Database;
use App\Core\Request;
use App\Core\Response;
use App\Repositories\ProtocolRepository as Repo;
use App\Repositories\RecordNotFoundException;

/**
 * CRUD für Teilentitäten (Räume, Mängel, Zähler, Schlüssel, Gegenstände,
 * Bemerkungen, Beteiligte, Kaution) – als JSON-Endpunkte für den Wizard.
 */
final class RecordController
{
    private function guard(string $id): array
    {
        Auth::requireWrite();
        $protocol = Repo::findOrFail((int) $id);
        if (Repo::isLocked($protocol)) {
            Response::json(['ok' => false, 'error' => 'Protokoll ist abgeschlossen und schreibgeschützt.'], 409);
        }
        return $protocol;
    }

    public function save(string $id, string $entity): void
    {
        $this->guard($id);
        $body = Request::jsonBody() ?: $_POST;
        $recordId = isset($body['record_id']) && $body['record_id'] !== '' ? (int) $body['record_id'] : null;

        // Formale IBAN-Prüfung nur als Hinweis, Speichern bleibt möglich
        $ibanWarning = null;
        if ($entity === 'bank' && !empty($body['iban']) && !iban_is_valid((string) $body['iban'])) {
            $ibanWarning = 'Die IBAN erscheint formal ungültig. Bitte prüfen.';
        }
        // Kautionsbetrag: deutsches Zahlenformat (1.500,00) in DECIMAL-Format wandeln
        if ($entity === 'bank' && isset($body['deposit_amount']) && is_string($body['deposit_amount']) && $body['deposit_amount'] !== '') {
            $normalized = str_replace(' ', '', $body['deposit_amount']);
            if (str_contains($normalized, ',')) {
                $normalized = str_replace('.', '', $normalized);   // Tausenderpunkte
                $normalized = str_replace(',', '.', $normalized);  // Dezimalkomma
            }
            $body['deposit_amount'] = is_numeric($normalized) ? $normalized : null;
        }

        try {
            $savedId = Repo::saveEntity((int) $id, $entity, $body, $recordId);
        } catch (\InvalidArgumentException) {
            Response::json(['ok' => false, 'error' => 'Unbekannter Datentyp.'], 400);
        } catch (RecordNotFoundException) {
            Response::json(['ok' => false, 'error' => 'Datensatz nicht gefunden. Bitte Seite neu laden.'], 404);
        }
        Response::json(['ok' => true, 'record_id' => $savedId, 'saved_at' => date('H:i'), 'warning' => $ibanWarning]);
    }

    public function delete(string $id, string $entity): void
    {
        $this->guard($id);
        $body = Request::jsonBody() ?: $_POST;
        $recordId = (int) ($body['record_id'] ?? 0);
        if ($recordId < 1) {
            Response::json(['ok' => false, 'error' => 'Keine Datensatz-ID.'], 400);
        }
        try {
            Repo::deleteEntity((int) $id, $entity, $recordId);
        } catch (\InvalidArgumentException) {
            Response::json(['ok' => false, 'error' => 'Unbekannter Datentyp.'], 400);
        } catch (RecordNotFoundException) {
            Response::json(['ok' => false, 'error' => 'Datensatz nicht gefunden. Bitte Seite neu laden.'], 404);
        }
        Response::json(['ok' => true]);
    }

    /** Sortierung per Drag & Drop: erwartet geordnete Liste von IDs. */
    public function sort(string $id, string $entity): void
    {
        $this->guard($id);
        $def = Repo::ENTITIES[$entity] ?? null;
        if ($def === null || !in_array('sort_order', $def['fields'], true)) {
            Response::json(['ok' => false, 'error' => 'Nicht sortierbar.'], 400);
        }
        $ids = Request::jsonBody()['order'] ?? [];
        foreach (array_values((array) $ids) as $index => $recordId) {
            Database::execute("UPDATE `{$def['table']}` SET sort_order = ? WHERE id = ? AND protocol_id = ?", [$index, (int) $recordId, (int) $id]);
        }
        Response::json(['ok' => true]);
    }

    /** Dupliziert einen Raum (ohne Mängel und Fotos). */
    public function duplicateRoom(string $id, string $roomId): void
    {
        $this->guard($id);
        $room = Database::fetch('SELECT * FROM protocol_rooms WHERE id = ? AND protocol_id = ?', [(int) $roomId, (int) $id]);
        if ($room === null) {
            Response::json(['ok' => false, 'error' => 'Raum nicht gefunden.'], 404);
        }
        $newId = Repo::saveEntity((int) $id, 'room', [
            'room_type'  => $room['room_type'],
            'room_name'  => trim(($room['room_name'] ?: $room['room_type']) . ' (Kopie)'),
            'comment'    => $room['comment'],
            'sort_order' => (int) $room['sort_order'] + 1,
        ]);
        Response::json(['ok' => true, 'record_id' => $newId]);
    }
}
