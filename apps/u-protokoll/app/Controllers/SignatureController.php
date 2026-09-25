<?php

declare(strict_types=1);

namespace App\Controllers;

use App\Core\Audit;
use App\Core\Auth;
use App\Core\Database;
use App\Core\Request;
use App\Core\Response;
use App\Repositories\ProtocolRepository as Repo;
use App\Services\FileService;

/**
 * Digitale Unterschriften: Canvas liefert ein PNG als Data-URI.
 * Das PNG wird im Dateispeicher abgelegt, SHA-256 und Zeitpunkt in der DB.
 */
final class SignatureController
{
    public function save(string $id): void
    {
        Auth::requireWrite();
        $protocol = Repo::findOrFail((int) $id);
        if (Repo::isLocked($protocol)) {
            Response::json(['ok' => false, 'error' => 'Protokoll ist abgeschlossen und schreibgeschützt.'], 409);
        }

        $body = Request::jsonBody();

        // Dublettenschutz: je Beteiligtem höchstens eine Unterschrift
        if (!empty($body['participant_id'])) {
            $existing = Database::fetch(
                'SELECT id FROM protocol_signatures WHERE protocol_id = ? AND participant_id = ?',
                [(int) $id, (int) $body['participant_id']]
            );
            if ($existing !== null) {
                Response::json(['ok' => false, 'error' => 'Für diese Person liegt bereits eine Unterschrift vor. Bitte zuerst die vorhandene löschen.'], 409);
            }
        }

        $dataUri = (string) ($body['image'] ?? '');
        if (!preg_match('#^data:image/png;base64,([A-Za-z0-9+/=]+)$#', $dataUri, $m)) {
            Response::json(['ok' => false, 'error' => 'Keine gültige Unterschrift übermittelt.'], 400);
        }
        $png = base64_decode($m[1], true);
        if ($png === false || strlen($png) < 100 || strlen($png) > 2 * 1024 * 1024) {
            Response::json(['ok' => false, 'error' => 'Unterschriftsdaten ungültig.'], 400);
        }
        // Serverseitig verifizieren, dass es tatsächlich ein PNG ist
        if (!str_starts_with($png, "\x89PNG")) {
            Response::json(['ok' => false, 'error' => 'Unterschriftsdaten ungültig.'], 400);
        }

        $filename = 'sig_' . bin2hex(random_bytes(12)) . '.png';
        $fileId = FileService::storeGenerated($protocol, $png, $filename, 'image/png', 'signature');

        $sigId = Database::insert('protocol_signatures', [
            'protocol_id'       => (int) $id,
            'participant_id'    => !empty($body['participant_id']) ? (int) $body['participant_id'] : null,
            'signer_name'       => mb_substr((string) ($body['signer_name'] ?? ''), 0, 190) ?: null,
            'signer_role'       => mb_substr((string) ($body['signer_role'] ?? ''), 0, 60) ?: null,
            'signature_file_id' => $fileId,
            'sha256'            => hash('sha256', $png),
            'signed_at'         => date('Y-m-d H:i:s'),
            'signed_location'   => mb_substr((string) ($body['signed_location'] ?? ''), 0, 190) ?: null,
            'comment'           => mb_substr((string) ($body['comment'] ?? ''), 0, 255) ?: null,
        ]);

        Audit::log('signature_created', 'protocol_signatures', $sigId, (int) $id, null, $body['signer_name'] ?? null);
        Database::execute("UPDATE protocols SET status = 'signature_pending' WHERE id = ? AND status IN ('draft','in_progress')", [(int) $id]);
        Response::json(['ok' => true, 'signature_id' => $sigId]);
    }

    public function delete(string $id, string $sigId): void
    {
        Auth::requireWrite();
        $protocol = Repo::findOrFail((int) $id);
        if (Repo::isLocked($protocol)) {
            Response::json(['ok' => false, 'error' => 'Protokoll ist gesperrt.'], 409);
        }
        $sig = Database::fetch('SELECT * FROM protocol_signatures WHERE id = ? AND protocol_id = ?', [(int) $sigId, (int) $id]);
        if ($sig === null) {
            Response::json(['ok' => false, 'error' => 'Signatur nicht gefunden.'], 404);
        }
        if ($sig['signature_file_id']) {
            $file = Database::fetch('SELECT * FROM protocol_files WHERE id = ?', [$sig['signature_file_id']]);
            if ($file) {
                \App\Services\FileService::delete($file);
            }
        }
        Database::execute('DELETE FROM protocol_signatures WHERE id = ?', [(int) $sigId]);
        Audit::log('signature_deleted', 'protocol_signatures', (int) $sigId, (int) $id);
        Response::json(['ok' => true]);
    }
}
