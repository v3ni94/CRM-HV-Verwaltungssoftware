<?php

declare(strict_types=1);

namespace App\Controllers;

use App\Core\Auth;
use App\Core\Config;
use App\Core\Database;
use App\Core\Request;
use App\Core\Response;
use App\Core\View;
use App\Repositories\ProtocolRepository as Repo;
use App\Services\MailService;
use App\Services\PdfService;
use App\Services\Storage\Storage;

/**
 * E-Mail-Versand des Protokoll-PDFs: an ausgewählte Beteiligte oder manuell.
 */
final class EmailController
{
    public function form(string $id): void
    {
        Auth::requireStaff();
        $full = Repo::loadFull((int) $id);
        $protocol = $full['protocol'];
        $subject = MailService::renderTemplate(
            Config::setting('email.default_subject', 'Übergabeprotokoll {{PROTOCOL_NUMBER}}'),
            $protocol
        );
        $body = MailService::renderTemplate(Config::setting('email.default_body', ''), $protocol);

        View::page('email/form', [
            'title'   => 'E-Mail-Versand: ' . ($protocol['protocol_number'] ?? ''),
            'subject' => $subject,
            'body'    => $body,
        ] + $full);
    }

    public function send(string $id): void
    {
        Auth::requireStaff();
        $full = Repo::loadFull((int) $id);
        $protocol = $full['protocol'];

        // Empfänger: angehakte Beteiligte plus manuelle Eingaben
        $to = [];
        foreach ((array) ($_POST['participant_emails'] ?? []) as $email) {
            if (filter_var($email, FILTER_VALIDATE_EMAIL)) {
                $to[] = $email;
            }
        }
        foreach ($this->splitAddresses((string) Request::post('to', '')) as $email) {
            $to[] = $email;
        }
        $to = array_values(array_unique($to));
        $cc = $this->splitAddresses((string) Request::post('cc', ''));
        $bcc = $this->splitAddresses((string) Request::post('bcc', ''));

        if ($to === []) {
            $_SESSION['flash_error'] = 'Bitte mindestens einen gültigen Empfänger angeben.';
            Response::redirect('/protocols/' . $id . '/email');
        }

        // Aktuelles PDF anhängen (gespeicherte Version, sonst frische Vorschau)
        $version = Database::fetch(
            'SELECT v.*, f.storage_path, f.original_filename FROM protocol_versions v
             JOIN protocol_files f ON f.id = v.pdf_file_id
             WHERE v.protocol_id = ? ORDER BY v.id DESC LIMIT 1',
            [(int) $id]
        );
        if ($version !== null) {
            $pdfContent = Storage::driver()->get($version['storage_path']);
            $pdfName = $version['original_filename'];
            $versionId = (int) $version['id'];
        } else {
            $html = View::render('pdf/protocol', $full + ['forPdf' => true, 'draftPreview' => true]);
            $pdfContent = PdfService::htmlToPdf($html);
            $pdfName = PdfService::filename($protocol);
            $versionId = null;
        }
        $attachments = [['content' => $pdfContent, 'filename' => $pdfName, 'mime' => 'application/pdf']];

        // Optionale weitere Anhänge aus dem Protokoll (nur nicht-interne)
        foreach ((array) ($_POST['attach_file_ids'] ?? []) as $fileId) {
            $file = Database::fetch('SELECT * FROM protocol_files WHERE id = ? AND protocol_id = ? AND is_internal = 0', [(int) $fileId, (int) $id]);
            if ($file) {
                $attachments[] = [
                    'content'  => Storage::driver()->get($file['storage_path']),
                    'filename' => $file['original_filename'] ?: $file['stored_filename'],
                    'mime'     => $file['mime_type'],
                ];
            }
        }

        $result = MailService::send(
            $protocol,
            $to,
            $cc,
            $bcc,
            (string) Request::post('subject', 'Übergabeprotokoll'),
            (string) Request::post('body', ''),
            $attachments,
            $versionId
        );

        if ($result['ok']) {
            Database::execute("UPDATE protocols SET status = 'sent' WHERE id = ? AND status = 'completed'", [(int) $id]);
            $_SESSION['flash_success'] = 'E-Mail wurde versendet an: ' . implode(', ', $to);
        } else {
            $_SESSION['flash_error'] = 'Versand fehlgeschlagen. Details siehe Versandhistorie.';
        }
        Response::redirect('/protocols/' . $id);
    }

    /** @return string[] */
    private function splitAddresses(string $raw): array
    {
        $out = [];
        foreach (preg_split('/[;,\s]+/', $raw) ?: [] as $part) {
            if ($part !== '' && filter_var($part, FILTER_VALIDATE_EMAIL)) {
                $out[] = $part;
            }
        }
        return $out;
    }
}
