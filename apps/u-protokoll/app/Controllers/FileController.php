<?php

declare(strict_types=1);

namespace App\Controllers;

use App\Core\Auth;
use App\Core\Database;
use App\Core\Request;
use App\Core\Response;
use App\Repositories\ProtocolRepository as Repo;
use App\Services\FileService;
use App\Services\Storage\Storage;

/**
 * Datei-Upload und Auslieferung. Dateien werden nie direkt vom Webserver
 * ausgeliefert, sondern nur nach Berechtigungsprüfung über diesen Controller.
 */
final class FileController
{
    public function upload(string $id): void
    {
        Auth::requireWrite();
        $protocol = Repo::findOrFail((int) $id);
        if (Repo::isLocked($protocol)) {
            Response::json(['ok' => false, 'error' => 'Protokoll ist abgeschlossen und schreibgeschützt.'], 409);
        }

        $category = (string) Request::post('category', 'photo');
        $allowedCategories = ['photo', 'meter_photo', 'room_photo', 'defect_photo', 'attachment', 'item_photo'];
        if (!in_array($category, $allowedCategories, true)) {
            $category = 'photo';
        }
        $refs = [];
        foreach (['room_id', 'defect_id', 'meter_id', 'note_id', 'item_id'] as $ref) {
            $value = Request::post($ref);
            if ($value !== null && $value !== '') {
                $refs[$ref] = (int) $value;
            }
        }
        $meta = [
            'description'     => Request::post('description'),
            'attachment_type' => Request::post('attachment_type'),
            // Gehilfen können keine internen Anhänge erzeugen
            'is_internal'     => (!Auth::isHelper() && Request::post('is_internal') === '1') ? 1 : 0,
        ];

        // Mehrfachupload: files[] oder einzelne Datei "file"
        $uploads = [];
        if (isset($_FILES['files']) && is_array($_FILES['files']['name'])) {
            foreach ($_FILES['files']['name'] as $i => $name) {
                $uploads[] = [
                    'name' => $name,
                    'type' => $_FILES['files']['type'][$i],
                    'tmp_name' => $_FILES['files']['tmp_name'][$i],
                    'error' => $_FILES['files']['error'][$i],
                    'size' => $_FILES['files']['size'][$i],
                ];
            }
        } elseif (isset($_FILES['file'])) {
            $uploads[] = $_FILES['file'];
        }
        if ($uploads === []) {
            Response::json(['ok' => false, 'error' => 'Keine Datei übermittelt.'], 400);
        }

        $stored = [];
        $errors = [];
        foreach ($uploads as $upload) {
            try {
                $file = FileService::store($protocol, $upload, $category, $refs, $meta);
                $stored[] = [
                    'id'       => (int) $file['id'],
                    'name'     => $file['original_filename'],
                    'mime'     => $file['mime_type'],
                    'size'     => (int) $file['file_size'],
                    'thumbUrl' => url('/files/' . $file['id'] . '/thumb'),
                    'url'      => url('/files/' . $file['id']),
                ];
            } catch (\Throwable $e) {
                \App\Core\Logger::error('Upload-Fehler: ' . $e->getMessage(), ['protocol' => $id]);
                $errors[] = ['name' => $upload['name'] ?? '?', 'error' => $e->getMessage()];
            }
        }
        Response::json(['ok' => $errors === [], 'files' => $stored, 'errors' => $errors]);
    }

    public function delete(string $id, string $fileId): void
    {
        Auth::requireWrite();
        $protocol = Repo::findOrFail((int) $id);
        $file = Database::fetch('SELECT * FROM protocol_files WHERE id = ? AND protocol_id = ?', [(int) $fileId, (int) $id]);
        if ($file === null) {
            Response::json(['ok' => false, 'error' => 'Datei nicht gefunden.'], 404);
        }
        // Nach finaler Sperre keine Löschung mehr (außer Admin)
        if (Repo::isLocked($protocol) && !Auth::isAdmin()) {
            Response::json(['ok' => false, 'error' => 'Protokoll ist gesperrt.'], 409);
        }
        // Interne Dateien sind für Gehilfen unsichtbar und damit auch nicht löschbar
        if (Auth::isHelper() && !empty($file['is_internal'])) {
            Response::json(['ok' => false, 'error' => 'Datei nicht gefunden.'], 404);
        }
        if (in_array($file['file_category'], ['signature', 'pdf'], true) && !Auth::isAdmin()) {
            Response::json(['ok' => false, 'error' => 'Signaturen und PDF-Versionen können nicht gelöscht werden.'], 403);
        }
        FileService::delete($file);
        Response::json(['ok' => true]);
    }

    public function download(string $fileId): void
    {
        $file = $this->authorizedFile((int) $fileId);
        $content = Storage::driver()->get($file['storage_path']);
        Response::download($content, $file['original_filename'] ?: $file['stored_filename'], $file['mime_type'] ?: 'application/octet-stream', true);
    }

    public function thumbnail(string $fileId): void
    {
        $file = $this->authorizedFile((int) $fileId);
        $path = $file['thumb_path'] ?: $file['storage_path'];
        $content = Storage::driver()->get($path);
        header('Cache-Control: private, max-age=86400');
        Response::download($content, 'thumb.jpg', $file['thumb_path'] ? 'image/jpeg' : ($file['mime_type'] ?: 'application/octet-stream'), true);
    }

    private function authorizedFile(int $fileId): array
    {
        // Auth erzwingt der Router; hier Existenz- und Berechtigungsprüfung
        $file = Database::fetch('SELECT * FROM protocol_files WHERE id = ?', [$fileId]);
        if ($file === null) {
            Response::html('<p>Datei nicht gefunden.</p>', 404);
        }
        Auth::requireProtocolAccess((int) $file['protocol_id']);
        // Interne Dateien sind für Gehilfen nicht sichtbar
        if (Auth::isHelper() && !empty($file['is_internal'])) {
            Response::html('<p>Keine Berechtigung.</p>', 403);
        }
        return $file;
    }
}
