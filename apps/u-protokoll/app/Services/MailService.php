<?php

declare(strict_types=1);

namespace App\Services;

use App\Core\Auth;
use App\Core\Config;
use App\Core\Database;
use App\Core\Logger;

/**
 * SMTP-Versand über PHPMailer (composer: phpmailer/phpmailer).
 * Jeder Versand wird in protocol_emails protokolliert (Versandhistorie).
 */
final class MailService
{
    /**
     * @param array $attachments Liste aus [content, filename, mime]
     * @return array{ok:bool, error:?string}
     */
    public static function send(
        array $protocol,
        array $to,
        array $cc,
        array $bcc,
        string $subject,
        string $body,
        array $attachments = [],
        ?int $versionId = null
    ): array {
        $status = 'sent';
        $error = null;
        $smtpResponse = null;

        try {
            if (!class_exists(\PHPMailer\PHPMailer\PHPMailer::class)) {
                throw new \RuntimeException('PHPMailer nicht installiert (composer install ausführen).');
            }
            $mail = new \PHPMailer\PHPMailer\PHPMailer(true);
            $mail->CharSet = 'UTF-8';
            $mail->Timeout = 20; // nicht antwortender SMTP-Host blockiert den Request nicht minutenlang
            $mail->isSMTP();
            $mail->Host = (string) Config::get('smtp.host');
            $mail->Port = (int) Config::get('smtp.port');
            $mail->SMTPAuth = Config::get('smtp.user') !== '';
            $mail->Username = (string) Config::get('smtp.user');
            $mail->Password = (string) Config::get('smtp.password');
            $enc = (string) Config::get('smtp.encryption');
            if ($enc === 'ssl') {
                $mail->SMTPSecure = \PHPMailer\PHPMailer\PHPMailer::ENCRYPTION_SMTPS;
            } elseif ($enc === 'tls') {
                $mail->SMTPSecure = \PHPMailer\PHPMailer\PHPMailer::ENCRYPTION_STARTTLS;
            }
            $mail->setFrom((string) Config::get('smtp.from'), (string) Config::get('smtp.from_name'));
            if (Config::get('smtp.reply_to')) {
                $mail->addReplyTo((string) Config::get('smtp.reply_to'));
            }
            foreach ($to as $addr) {
                $mail->addAddress($addr);
            }
            foreach ($cc as $addr) {
                $mail->addCC($addr);
            }
            foreach ($bcc as $addr) {
                $mail->addBCC($addr);
            }
            $mail->Subject = $subject;
            $mail->Body = $body;
            foreach ($attachments as $att) {
                $mail->addStringAttachment($att['content'], $att['filename'], 'base64', $att['mime'] ?? 'application/octet-stream');
            }
            $mail->send();
            $smtpResponse = 'OK';
        } catch (\Throwable $e) {
            $status = 'failed';
            $error = $e->getMessage();
            Logger::error('E-Mail-Versand fehlgeschlagen: ' . $error, ['protocol' => $protocol['id']]);
        }

        Database::insert('protocol_emails', [
            'protocol_id'         => (int) $protocol['id'],
            'protocol_version_id' => $versionId,
            'sender'              => Config::get('smtp.from'),
            'recipients'          => implode(', ', $to),
            'cc'                  => implode(', ', $cc) ?: null,
            'bcc'                 => implode(', ', $bcc) ?: null,
            'subject'             => mb_substr($subject, 0, 255),
            'body'                => $body,
            'status'              => $status,
            'smtp_response'       => $smtpResponse,
            'error_message'       => $error,
            'sent_by'             => Auth::id(),
        ]);
        \App\Core\Audit::log('email_' . $status, 'protocol_emails', null, (int) $protocol['id'], null, implode(', ', $to));

        return ['ok' => $status === 'sent', 'error' => $error];
    }

    /**
     * Allgemeiner Versand ohne Protokollbezug (z. B. Benutzereinladungen).
     * @return array{ok:bool, error:?string}
     */
    public static function sendRaw(string $to, string $subject, string $body): array
    {
        try {
            if (!class_exists(\PHPMailer\PHPMailer\PHPMailer::class)) {
                throw new \RuntimeException('PHPMailer nicht installiert (composer install ausführen).');
            }
            $mail = new \PHPMailer\PHPMailer\PHPMailer(true);
            $mail->CharSet = 'UTF-8';
            $mail->Timeout = 20; // nicht antwortender SMTP-Host blockiert den Request nicht minutenlang
            $mail->isSMTP();
            $mail->Host = (string) Config::get('smtp.host');
            $mail->Port = (int) Config::get('smtp.port');
            $mail->SMTPAuth = Config::get('smtp.user') !== '';
            $mail->Username = (string) Config::get('smtp.user');
            $mail->Password = (string) Config::get('smtp.password');
            $enc = (string) Config::get('smtp.encryption');
            if ($enc === 'ssl') {
                $mail->SMTPSecure = \PHPMailer\PHPMailer\PHPMailer::ENCRYPTION_SMTPS;
            } elseif ($enc === 'tls') {
                $mail->SMTPSecure = \PHPMailer\PHPMailer\PHPMailer::ENCRYPTION_STARTTLS;
            }
            $mail->setFrom((string) Config::get('smtp.from'), (string) Config::get('smtp.from_name'));
            if (Config::get('smtp.reply_to')) {
                $mail->addReplyTo((string) Config::get('smtp.reply_to'));
            }
            $mail->addAddress($to);
            $mail->Subject = $subject;
            $mail->Body = $body;
            $mail->send();
            return ['ok' => true, 'error' => null];
        } catch (\Throwable $e) {
            Logger::error('E-Mail-Versand (raw) fehlgeschlagen: ' . $e->getMessage(), ['to' => $to]);
            return ['ok' => false, 'error' => $e->getMessage()];
        }
    }

    /** Ersetzt Platzhalter der administrativ gepflegten Vorlage. */
    public static function renderTemplate(string $template, array $protocol): string
    {
        $number = (string) ($protocol['protocol_number'] ?? '');
        if ($number === '' && isset($protocol['id'])) {
            $number = protocol_number((int) $protocol['id']);
        }
        return strtr($template, [
            '{{OBJECT_ADDRESS}}'  => protocol_address($protocol) ?: 'ohne Objektadresse',
            '{{HANDOVER_DATE}}'   => fmt_date($protocol['handover_date'] ?? null) ?: 'ohne Datumsangabe',
            '{{PROTOCOL_NUMBER}}' => $number !== '' ? $number : 'ohne Protokollnummer',
        ]);
    }
}
