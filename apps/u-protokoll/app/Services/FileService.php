<?php

declare(strict_types=1);

namespace App\Services;

use App\Core\Audit;
use App\Core\Auth;
use App\Core\Database;
use App\Services\Storage\Storage;

/**
 * Datei-Uploads: Validierung, sichere Zufallsnamen, Ablage im Dateispeicher,
 * Metadaten in MariaDB. Keine ausführbaren Dateien, MIME-Prüfung serverseitig.
 */
final class FileService
{
    private const MAX_SIZE = 25 * 1024 * 1024; // 25 MB je Datei

    private const ALLOWED = [
        'image/jpeg'      => 'jpg',
        'image/png'       => 'png',
        'image/webp'      => 'webp',
        'image/heic'      => 'heic',
        'image/heif'      => 'heic',
        'application/pdf' => 'pdf',
    ];

    /**
     * Verarbeitet eine hochgeladene Datei und liefert den protocol_files-Datensatz.
     *
     * @param array $upload Eintrag aus $_FILES
     * @param array $refs   Zuordnung: room_id, defect_id, meter_id, note_id, item_id
     */
    public static function store(array $protocol, array $upload, string $category, array $refs = [], array $meta = []): array
    {
        if (($upload['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK) {
            throw new \RuntimeException('Upload fehlgeschlagen (Code ' . ($upload['error'] ?? '?') . ').');
        }
        if (($upload['size'] ?? 0) > self::MAX_SIZE) {
            throw new \RuntimeException('Datei ist zu groß (max. 25 MB).');
        }

        $tmp = $upload['tmp_name'];
        $finfo = new \finfo(FILEINFO_MIME_TYPE);
        $mime = (string) $finfo->file($tmp);
        if (!isset(self::ALLOWED[$mime])) {
            throw new \RuntimeException('Dateityp nicht zulässig: ' . $mime);
        }

        $content = (string) file_get_contents($tmp);
        $ext = self::ALLOWED[$mime];
        $thumbContent = null;

        // HEIC/HEIF (iPhone-Standard) kann GD nicht lesen: nach JPEG konvertieren,
        // sonst mit verständlichem Hinweis ablehnen (statt unbrauchbar zu speichern)
        if (in_array($mime, ['image/heic', 'image/heif'], true)) {
            $converted = ImageService::heicToJpeg($content);
            if ($converted === null) {
                throw new \RuntimeException(
                    'HEIC-Fotos werden von diesem Server nicht unterstützt. '
                    . 'Bitte am iPhone unter Einstellungen, Kamera, Formate die Option "Maximale Kompatibilität" wählen oder das Foto als JPEG hochladen.'
                );
            }
            $content = $converted;
            $mime = 'image/jpeg';
            $ext = 'jpg';
        }

        // Schutz vor Dekompressions-Bomben: Pixelmaße vor dem Dekodieren prüfen
        if (ImageService::isImage($mime) && !ImageService::dimensionsAcceptable($content)) {
            throw new \RuntimeException('Bildauflösung zu groß (max. 50 Megapixel).');
        }

        // Bilder neu kodieren: Rotation, Skalierung, Metadaten (GPS) entfernen
        if (ImageService::isImage($mime)) {
            $processed = ImageService::process($content, $mime);
            if ($processed !== null) {
                $content = $processed['web'];
                $thumbContent = $processed['thumb'];
                $mime = 'image/jpeg';
                $ext = 'jpg';
            }
        }

        $storedName = bin2hex(random_bytes(16)) . '.' . $ext;
        $subDir = match ($category) {
            'meter_photo' => 'meters',
            'room_photo'  => 'rooms',
            'defect_photo'=> 'defects',
            'signature'   => 'signatures',
            'pdf'         => 'pdf',
            'attachment'  => 'attachments',
            default       => 'photos',
        };
        $dir = Storage::protocolDir((int) $protocol['id'], $subDir, $protocol['created_at'] ?? null);
        $path = $dir . '/' . $storedName;
        Storage::driver()->put($path, $content);

        $thumbPath = null;
        if ($thumbContent !== null) {
            $thumbPath = $dir . '/thumb_' . $storedName;
            Storage::driver()->put($thumbPath, $thumbContent);
        }

        $fileId = Database::insert('protocol_files', [
            'protocol_id'       => (int) $protocol['id'],
            'room_id'           => $refs['room_id'] ?? null,
            'defect_id'         => $refs['defect_id'] ?? null,
            'meter_id'          => $refs['meter_id'] ?? null,
            'note_id'           => $refs['note_id'] ?? null,
            'item_id'           => $refs['item_id'] ?? null,
            'file_category'     => $category,
            'attachment_type'   => $meta['attachment_type'] ?? null,
            'original_filename' => mb_substr((string) ($upload['name'] ?? ''), 0, 250),
            'stored_filename'   => $storedName,
            'storage_path'      => $path,
            'thumb_path'        => $thumbPath,
            'mime_type'         => $mime,
            'file_size'         => strlen($content),
            'sha256'            => hash('sha256', $content),
            'description'       => $meta['description'] ?? null,
            'is_internal'       => (int) ($meta['is_internal'] ?? 0),
            'created_by'        => Auth::id(),
        ]);

        Audit::log('file_uploaded', 'protocol_files', $fileId, (int) $protocol['id'], null, $upload['name'] ?? null);
        return Database::fetch('SELECT * FROM protocol_files WHERE id = ?', [$fileId]);
    }

    /** Speichert erzeugten Inhalt (Signatur-PNG, PDF) als Protokolldatei. */
    public static function storeGenerated(array $protocol, string $content, string $filename, string $mime, string $category): int
    {
        $subDir = $category === 'signature' ? 'signatures' : 'pdf';
        $path = Storage::protocolDir((int) $protocol['id'], $subDir, $protocol['created_at'] ?? null) . '/' . $filename;
        Storage::driver()->put($path, $content);

        return Database::insert('protocol_files', [
            'protocol_id'       => (int) $protocol['id'],
            'file_category'     => $category,
            'original_filename' => $filename,
            'stored_filename'   => $filename,
            'storage_path'      => $path,
            'mime_type'         => $mime,
            'file_size'         => strlen($content),
            'sha256'            => hash('sha256', $content),
            'is_internal'       => 0,
            'created_by'        => Auth::id(),
        ]);
    }

    public static function delete(array $file): void
    {
        // Physisch nur löschen, wenn keine andere Protokollversion dieselbe
        // Datei referenziert (Versionskopien teilen sich die physische Datei,
        // das Original muss unverändert reproduzierbar bleiben).
        $shared = Database::fetch(
            'SELECT COUNT(*) AS c FROM protocol_files WHERE storage_path = ? AND id != ?',
            [$file['storage_path'], (int) $file['id']]
        );
        if ((int) ($shared['c'] ?? 0) === 0) {
            Storage::driver()->delete($file['storage_path']);
            if (!empty($file['thumb_path'])) {
                Storage::driver()->delete($file['thumb_path']);
            }
        }
        Database::execute('DELETE FROM protocol_files WHERE id = ?', [$file['id']]);
        Audit::log('file_deleted', 'protocol_files', (int) $file['id'], (int) $file['protocol_id'], $file['original_filename']);
    }
}
