<?php

declare(strict_types=1);

namespace App\Services;

use App\Core\Auth;
use App\Core\Config;
use App\Core\Database;
use App\Core\Logger;
use App\Core\View;
use App\Services\Storage\Storage;

/**
 * PDF-Erzeugung mit Dompdf (composer: dompdf/dompdf).
 * Das PDF wird aus app/Views/pdf/protocol.php gerendert, im Dateispeicher
 * abgelegt und als Version in protocol_versions registriert.
 */
final class PdfService
{
    /** Erzeugt das Protokoll-PDF und liefert [versionId, fileId, filename]. */
    public static function generate(array $full, ?string $changeReason = null): array
    {
        $protocol = $full['protocol'];
        $html = View::render('pdf/protocol', $full + ['forPdf' => true]);
        $pdfContent = self::htmlToPdf($html);

        $filename = self::filename($protocol);
        $fileId = FileService::storeGenerated($protocol, $pdfContent, $filename, 'application/pdf', 'pdf');
        $sha = hash('sha256', $pdfContent);

        $versionId = Database::insert('protocol_versions', [
            'protocol_id'    => (int) $protocol['id'],
            'version_number' => (int) $protocol['version'],
            'pdf_file_id'    => $fileId,
            'sha256'         => $sha,
            'change_reason'  => $changeReason,
            'created_by'     => Auth::id(),
        ]);

        \App\Core\Audit::log('pdf_generated', 'protocol_versions', $versionId, (int) $protocol['id'], null, $filename);
        return [$versionId, $fileId, $filename];
    }

    public static function htmlToPdf(string $html): string
    {
        if (!class_exists(\Dompdf\Dompdf::class)) {
            Logger::error('Dompdf nicht installiert.');
            throw new \RuntimeException('PDF-Komponente nicht installiert (composer install ausführen).');
        }
        $options = new \Dompdf\Options();
        $options->set('isRemoteEnabled', false);
        $options->set('defaultFont', 'DejaVu Sans');
        $options->setChroot(BASE_PATH . '/storage');
        $dompdf = new \Dompdf\Dompdf($options);
        $dompdf->loadHtml($html, 'UTF-8');
        $dompdf->setPaper('A4', 'portrait');
        $dompdf->render();

        // Seitenzahlen "Seite X von Y"
        $canvas = $dompdf->getCanvas();
        $canvas->page_text(495, 826, 'Seite {PAGE_NUM} von {PAGE_COUNT}', 'DejaVu Sans', 8, [0.53, 0.53, 0.54]);

        return (string) $dompdf->output();
    }

    /** Dateiname: U-Protokoll_000125_Musterstrasse-12_Berlin_2026-08-28.pdf */
    public static function filename(array $protocol): string
    {
        $numberPart = preg_replace('/[^A-Za-z0-9\-]/', '', (string) ($protocol['protocol_number'] ?? ''))
            ?: sprintf('%06d', (int) $protocol['id']);
        $parts = ['U-Protokoll', $numberPart];
        $street = trim(($protocol['street'] ?? '') . '-' . ($protocol['house_number'] ?? ''), '-');
        if ($street !== '') {
            $parts[] = self::slug($street);
        }
        if (!empty($protocol['city'])) {
            $parts[] = self::slug($protocol['city']);
        }
        if (!empty($protocol['handover_date'])) {
            $parts[] = $protocol['handover_date'];
        }
        if ((int) $protocol['version'] > 1) {
            $parts[] = 'V' . $protocol['version'];
        }
        return implode('_', $parts) . '.pdf';
    }

    private static function slug(string $value): string
    {
        $value = str_replace(
            ['ä', 'ö', 'ü', 'Ä', 'Ö', 'Ü', 'ß', ' '],
            ['ae', 'oe', 'ue', 'Ae', 'Oe', 'Ue', 'ss', '-'],
            $value
        );
        $value = preg_replace('/[^A-Za-z0-9\-]/', '', $value) ?? '';
        return trim(preg_replace('/-+/', '-', $value) ?? '', '-');
    }

    /** HVM-Logo als Data-URI für PDF und Druckansicht. */
    public static function logoDataUri(): ?string
    {
        static $uri = null;
        if ($uri === null) {
            $file = BASE_PATH . '/public/assets/img/logo-hvm.jpg';
            $uri = is_file($file) ? 'data:image/jpeg;base64,' . base64_encode((string) file_get_contents($file)) : '';
        }
        return $uri ?: null;
    }

    /** Base64-Data-URI eines gespeicherten Bildes für die PDF-Einbettung. */
    public static function imageDataUri(?string $storagePath, ?string $mime = 'image/jpeg'): ?string
    {
        if (!$storagePath) {
            return null;
        }
        try {
            $content = Storage::driver()->get($storagePath);
            return 'data:' . ($mime ?: 'image/jpeg') . ';base64,' . base64_encode($content);
        } catch (\Throwable $e) {
            Logger::error('PDF-Bild nicht ladbar: ' . $e->getMessage());
            return null;
        }
    }
}
