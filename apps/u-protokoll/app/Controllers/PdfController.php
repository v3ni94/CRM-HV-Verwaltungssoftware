<?php

declare(strict_types=1);

namespace App\Controllers;

use App\Core\Database;
use App\Core\Response;
use App\Core\View;
use App\Repositories\ProtocolRepository as Repo;
use App\Services\PdfService;
use App\Services\Storage\Storage;

final class PdfController
{
    /** Zeigt das aktuelle PDF an; erzeugt es bei Bedarf neu (nur Entwürfe). */
    public function show(string $id): void
    {
        $this->deliver($id, true);
    }

    public function download(string $id): void
    {
        $this->deliver($id, false);
    }

    private function deliver(string $id, bool $inline): void
    {
        $full = Repo::loadFull((int) $id);
        $protocol = $full['protocol'];

        // Abgeschlossen: gespeicherte Version ausliefern (reproduzierbar)
        $version = Database::fetch(
            'SELECT v.*, f.storage_path, f.original_filename FROM protocol_versions v
             JOIN protocol_files f ON f.id = v.pdf_file_id
             WHERE v.protocol_id = ? ORDER BY v.id DESC LIMIT 1',
            [(int) $id]
        );

        // Stornierte Protokolle werden nie aus der gespeicherten Version ausgeliefert,
        // damit der Stornohinweis sichtbar ist
        if ($version !== null && Repo::isLocked($protocol) && $protocol['status'] !== 'cancelled') {
            $content = Storage::driver()->get($version['storage_path']);
            Response::download($content, $version['original_filename'], 'application/pdf', $inline);
        }

        // Entwurf: Vorschau-PDF on the fly (ohne Versionseintrag)
        $html = View::render('pdf/protocol', $full + [
            'forPdf'       => true,
            'draftPreview' => !protocol_is_finalized($protocol),
            'cancelledMark'=> $protocol['status'] === 'cancelled',
        ]);
        $content = PdfService::htmlToPdf($html);
        Response::download($content, PdfService::filename($protocol), 'application/pdf', $inline);
    }

    /** Separater Mängellisten-Export (Raum, Mangel, Priorität, Foto). */
    public function defectList(string $id): void
    {
        $full = Repo::loadFull((int) $id);
        $html = View::render('pdf/defects', $full);
        $content = PdfService::htmlToPdf($html);
        $name = 'Maengelliste_' . sprintf('%06d', (int) $id) . '.pdf';
        Response::download($content, $name, 'application/pdf', true);
    }
}
