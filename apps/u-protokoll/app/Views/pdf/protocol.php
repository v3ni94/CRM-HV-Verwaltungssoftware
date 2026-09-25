<?php
/**
 * Protokoll-PDF / Druckansicht.
 * $forPdf = true: Bilder als Data-URI einbetten (Dompdf); false: Browser-Druckansicht.
 * Interne Daten (is_internal, internal_note) erscheinen hier grundsätzlich NICHT.
 */
use App\Core\Config;
use App\Services\PdfService;

$p = $protocol;
$forPdf = $forPdf ?? true;
$draftPreview = $draftPreview ?? false;
$companyName = Config::setting('company.name', 'Hausverwaltung Müller GmbH');
$companyStreet = Config::setting('company.street', 'Rheinpromenade 13, 40789 Monheim am Rhein');
$companyRegister = Config::setting('company.register', 'Amtsgericht Düsseldorf, HRB 104762');
$companyCeo = Config::setting('company.ceo', 'Geschäftsführer: Timo Müller');
$companyWeb = Config::setting('company.website', 'www.muellerhv.de');
$brandFooter = Config::setting('company.brand_footer', 'Eine Marke der Müller Holding Aktiengesellschaft');
$showBrand = Config::setting('pdf.show_brand_footer', '1') === '1';
$logo = PdfService::logoDataUri();
$subtitle = protocol_types()[$p['protocol_type']] ?? '';
$hideTime = (bool) $p['hide_time_information'];

$img = function (?array $file, int $maxHeight = 160) use ($forPdf): string {
    if (!$file) { return ''; }
    if ($forPdf) {
        $src = PdfService::imageDataUri($file['storage_path'], $file['mime_type']);
        if (!$src) { return ''; }
    } else {
        $src = url('/files/' . $file['id']);
    }
    return '<img src="' . e($src) . '" style="max-height:' . $maxHeight . 'px;max-width:230px;margin:2px" alt="">';
};

$publicFiles = array_values(array_filter($files, fn($f) => !$f['is_internal'] && !in_array($f['file_category'], ['signature', 'pdf'], true)));
$filesBy = function (string $key, int $id) use ($publicFiles): array {
    return array_values(array_filter($publicFiles, fn($f) => (int) ($f[$key] ?? 0) === $id && str_starts_with((string) $f['mime_type'], 'image/')));
};
$publicNotes = array_values(array_filter($notes, fn($n) => empty($n['is_internal'])));
$attachmentsPublic = array_values(array_filter($publicFiles, fn($f) => $f['file_category'] === 'attachment'));

// Leere Angaben werden nicht ausgeblendet, sondern ausgegraut dargestellt
$dash = fn(?string $value): string => ($value !== null && trim($value) !== '')
    ? e($value)
    : '<span class="empty">–</span>';
?>
<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title><?= e($p['protocol_number']) ?></title>
<style>
    /* HVM-CI: Orange #E6A83C nur als Akzent, Anthrazit #87888A, Hellgrau #D7D8DA, Text #1A1A1A */
    @page { margin: 105px 45px 78px 45px; }
    body { font-family: DejaVu Sans, Helvetica, Arial, sans-serif; font-size: 9.5pt; color: #1A1A1A; margin: 0; }
    .kennlinie { height: 8px; font-size: 0; line-height: 0; }
    .kennlinie span { display: inline-block; height: 8px; }
    .pdf-header { position: fixed; top: -85px; left: 0; right: 0; }
    .pdf-header .head-table { margin-top: 6px; }
    .pdf-footer { position: fixed; bottom: -62px; left: 0; right: 0; font-size: 7.5pt; color: #87888A; text-align: center; }
    .company { font-size: 8pt; color: #87888A; }
    h1 { font-size: 15pt; color: #1A1A1A; margin: 0; }
    .subtitle-marker { display: inline-block; width: 20px; height: 4px; background: #E6A83C; margin-right: 5px; }
    h2 { font-size: 11pt; color: #1A1A1A; border-bottom: 2px solid #E6A83C; padding-bottom: 2px; margin: 16px 0 6px; page-break-after: avoid; }
    h3 { font-size: 10pt; color: #1A1A1A; margin: 10px 0 4px; page-break-after: avoid; }
    table { width: 100%; border-collapse: collapse; }
    table.data td, table.data th { border: 1px solid #D7D8DA; padding: 4px 6px; font-size: 9pt; vertical-align: top; text-align: left; word-wrap: break-word; }
    table.data th { background: #ECECEC; color: #1A1A1A; }
    table.data tr:nth-child(even) td { background: #f7f7f8; }
    table.kv td { padding: 2px 6px 2px 0; vertical-align: top; }
    table.kv td.k { width: 32%; color: #87888A; }
    .badge { font-size: 8pt; color: #87888A; }
    .photos { margin: 4px 0; }
    .caption { font-size: 7.5pt; color: #87888A; }
    .sig-block { display: inline-block; width: 44%; margin: 8px 2%; vertical-align: top; }
    .sig-line { border-bottom: 1px solid #1A1A1A; min-height: 60px; }
    .draft-mark { color: #b03030; font-weight: bold; border: 1px solid #b03030; display: inline-block; padding: 2px 8px; margin-bottom: 6px; }
    .empty { color: #9C9D9F; }
    <?php if (!$forPdf): ?>
    body { max-width: 800px; margin: 2rem auto; }
    .pdf-header, .pdf-footer { position: static; }
    <?php endif; ?>
</style>
</head>
<body>

<div class="pdf-header">
    <div class="kennlinie"><span style="width:40%;background:#87888A"></span><span style="width:20%;background:#9C9D9F"></span><span style="width:7.5%;background:#E6A83C"></span><span style="width:32.5%;background:#D7D8DA"></span></div>
    <table class="head-table"><tr>
        <td style="vertical-align:middle">
            <h1>U-Protokoll</h1>
            <div><span class="subtitle-marker"></span><?= e($subtitle) ?></div>
        </td>
        <td style="text-align:right;vertical-align:middle" class="company">
            <?php if ($logo): ?>
                <img src="<?= $logo ?>" style="width:58px" alt="">
            <?php else: ?>
                <strong><?= e($companyName) ?></strong>
            <?php endif; ?>
        </td>
    </tr></table>
</div>
<div class="pdf-footer">
    <div class="kennlinie" style="height:3px;margin-bottom:3px"><span style="width:40%;height:3px;background:#87888A"></span><span style="width:20%;height:3px;background:#9C9D9F"></span><span style="width:7.5%;height:3px;background:#E6A83C"></span><span style="width:32.5%;height:3px;background:#D7D8DA"></span></div>
    <?= e($companyName) ?> | <?= e($companyStreet) ?><?= $showBrand ? ' | ' . e($brandFooter) : '' ?><br>
    <?= e($companyRegister) ?> | <?= e($companyCeo) ?> | <?= e($companyWeb) ?> | Protokoll <?= e($p['protocol_number']) ?><?= (int) $p['version'] > 1 ? ', Version ' . (int) $p['version'] : '' ?>
</div>

<?php if (!empty($cancelledMark)): ?><div class="draft-mark">STORNIERT: Dieses Protokoll ist nicht wirksam</div>
<?php elseif ($draftPreview): ?><div class="draft-mark">ENTWURF: Protokoll noch nicht abgeschlossen</div><?php endif; ?>

<h2>Protokoll- und Objektdaten</h2>
<table class="kv">
    <tr><td class="k">Protokollnummer</td><td><?= e($p['protocol_number']) ?><?= (int) $p['version'] > 1 ? ' (Version ' . (int) $p['version'] . ')' : '' ?></td></tr>
    <tr><td class="k">Ticketnummer</td><td><?= $dash($p['ticket_number']) ?></td></tr>
    <tr><td class="k">Objekt</td><td><?= $dash(protocol_address($p)) ?></td></tr>
    <?php
    $notBlank = fn($v) => $v !== null && $v !== '';
    $unitParts = array_filter([
        $p['object_label'],
        $notBlank($p['building']) ? 'Gebäude ' . $p['building'] : null,
        $notBlank($p['floor']) ? 'Etage ' . $p['floor'] : null,
        $notBlank($p['unit_number']) ? 'Einheit ' . $p['unit_number'] : null,
        $p['unit_position'],
    ], $notBlank);
    ?>
    <tr><td class="k">Einheit</td><td><?= $dash(trim(implode(' · ', $unitParts))) ?></td></tr>
    <tr><td class="k">Mietvertragsnummer</td><td><?= $dash($p['rental_contract_number']) ?></td></tr>
    <tr><td class="k">Objektnummer</td><td><?= $dash($p['internal_object_number']) ?></td></tr>
    <tr><td class="k">Verwaltungsnummer</td><td><?= $dash($p['management_number']) ?></td></tr>
    <tr><td class="k">Referenznummer</td><td><?= $dash($p['reference_number']) ?></td></tr>
    <tr><td class="k">Übergabedatum</td><td><?= $dash(fmt_date($p['handover_date'])) ?></td></tr>
    <?php if (!$hideTime): ?>
        <tr><td class="k">Uhrzeit</td><td><?= $dash(trim(fmt_time($p['handover_start']) . ($p['handover_end'] ? ' bis ' . fmt_time($p['handover_end']) : ''))) ?></td></tr>
    <?php endif; ?>
    <tr><td class="k">Übergabeort</td><td><?= $dash($p['handover_location']) ?></td></tr>
</table>

<h2>Beteiligte</h2>
<?php if ($participants === []): ?>
    <p class="empty">Keine Angaben erfasst.</p>
<?php else: ?>
<table class="data">
    <thead><tr><th>Rolle</th><th>Name / Firma</th><th>Anschrift</th><th>Kontakt</th></tr></thead><tbody>
    <?php foreach ($participants as $pt): ?>
        <tr>
            <td><?= e(participant_role_label($pt['role'], $p['protocol_type'])) ?></td>
            <td><?= $dash(trim(($pt['salutation'] ?? '') . ' ' . ($pt['first_name'] ?? '') . ' ' . ($pt['last_name'] ?? ''))) ?><?= $pt['company'] ? '<br>' . e($pt['company']) : '' ?></td>
            <td><?= e(trim(($pt['street'] ?? '') . ' ' . ($pt['house_number'] ?? ''))) ?><br><?= e(trim(($pt['postal_code'] ?? '') . ' ' . ($pt['city'] ?? ''))) ?></td>
            <td><?= e($pt['email']) ?><?= $pt['phone'] ? '<br>Tel. ' . e($pt['phone']) : '' ?><?= $pt['mobile'] ? '<br>Mobil ' . e($pt['mobile']) : '' ?></td>
        </tr>
    <?php endforeach; ?>
</tbody></table>
<?php endif; ?>

<h2>Kaution / Bankverbindung</h2>
<?php if ($bank === null || !empty($bank['no_bank_given'])): ?>
    <p class="empty"><?= $bank && $bank['no_bank_given'] ? 'Keine Bankverbindung angegeben.' : 'Keine Angaben erfasst.' ?></p>
<?php else: ?>
<table class="kv">
    <tr><td class="k">Kautionsbetrag</td><td><?= $dash(fmt_amount($bank['deposit_amount'])) ?></td></tr>
    <tr><td class="k">Kontoinhaber</td><td><?= $dash($bank['account_holder']) ?></td></tr>
    <tr><td class="k">IBAN</td><td><?= $dash($bank['iban']) ?></td></tr>
    <tr><td class="k">BIC</td><td><?= $dash($bank['bic']) ?></td></tr>
    <tr><td class="k">Bank</td><td><?= $dash($bank['bank_name']) ?></td></tr>
    <tr><td class="k">Abweichender Zahlungsempfänger</td><td><?= $dash($bank['alt_payee']) ?></td></tr>
    <tr><td class="k">Bemerkung</td><td><?= $dash($bank['comment']) ?></td></tr>
    <?php if ($bank['deposit_separate']): ?><tr><td class="k">Hinweis</td><td>Die Kautionsabrechnung erfolgt separat.</td></tr><?php endif; ?>
</table>
<?php endif; ?>

<h2>Zählerstände</h2>
<?php if ($meters === []): ?>
    <p class="empty">Keine Zählerstände erfasst.</p>
<?php else: ?>
<table class="data">
    <thead><tr><th>Zähler</th><th>Zählernummer</th><th>Stand</th><th>Einheit</th><th>Ablesung</th><th>Standort / Bemerkung</th></tr></thead><tbody>
    <?php foreach ($meters as $m): ?>
        <tr>
            <td><?= e($m['custom_type'] ?: (meter_types()[$m['meter_type']] ?? '')) ?></td>
            <td><?= e($m['meter_number']) ?></td>
            <td><?= e($m['meter_value']) ?></td>
            <td><?= e($m['unit']) ?></td>
            <td><?= e(trim(fmt_date($m['reading_date']) . ' ' . ($hideTime ? '' : fmt_time($m['reading_time'])))) ?></td>
            <td><?= e(trim(($m['location'] ?? '') . ' ' . ($m['comment'] ?? ''))) ?></td>
        </tr>
    <?php endforeach; ?>
</tbody></table>
<?php foreach ($meters as $m): $photos = $filesBy('meter_id', (int) $m['id']); if ($photos === []) continue; ?>
    <div class="photos"><span class="caption"><?= e($m['custom_type'] ?: (meter_types()[$m['meter_type']] ?? 'Zähler')) ?>:</span><br>
        <?php foreach ($photos as $ph): ?><?= $img($ph, 120) ?><?php endforeach; ?></div>
<?php endforeach; ?>
<?php endif; ?>

<h2>Raumprotokoll</h2>
<?php if ($rooms === []): ?>
    <p class="empty">Keine Räume erfasst.</p>
<?php endif; ?>
<?php foreach ($rooms as $room): $roomId = (int) $room['id']; ?>
    <h3><?= e($room['room_name'] ?: $room['room_type'] ?: 'Raum') ?>: <?= e(room_conditions()[$room['condition_status']] ?? 'Keine Angabe') ?></h3>
    <?php if ($room['comment']): ?><p><?= e($room['comment']) ?></p><?php endif; ?>
    <?php $roomDefects = array_values(array_filter($defects, fn($d) => (int) $d['room_id'] === $roomId)); ?>
    <?php if ($roomDefects !== []): ?>
        <table class="data">
            <thead><tr><th>Mangel</th><th>Kategorie</th><th>Position</th><th>Priorität</th><th>Feststellung</th><th>Beschreibung</th></tr></thead><tbody>
            <?php foreach ($roomDefects as $d): ?>
                <tr>
                    <td><?= e($d['title']) ?></td>
                    <td><?= e($d['category']) ?></td>
                    <td><?= e($d['location']) ?></td>
                    <td><?= e(defect_priorities()[$d['priority']] ?? '') ?></td>
                    <td><?= e(defect_statuses()[$d['defect_status']] ?? '') ?></td>
                    <td><?= e(trim(($d['description'] ?? '') . ' ' . ($d['comment'] ?? ''))) ?></td>
                </tr>
            <?php endforeach; ?>
        </tbody></table>
        <?php foreach ($roomDefects as $d): $photos = $filesBy('defect_id', (int) $d['id']); if ($photos === []) continue; ?>
            <div class="photos"><span class="caption">Fotos zum Mangel „<?= e($d['title'] ?: $d['category']) ?>“:</span><br>
                <?php foreach ($photos as $ph): ?><?= $img($ph, 140) ?><?php endforeach; ?></div>
        <?php endforeach; ?>
    <?php endif; ?>
    <?php $roomPhotos = $filesBy('room_id', $roomId); if ($roomPhotos !== []): ?>
        <div class="photos"><span class="caption">Raumfotos:</span><br>
            <?php foreach ($roomPhotos as $ph): ?><?= $img($ph, 140) ?><?php endforeach; ?></div>
    <?php endif; ?>
<?php endforeach; ?>

<h2>Schlüsselübergabe</h2>
<?php if ($keys === []): ?>
    <p class="empty">Keine Schlüssel erfasst.</p>
<?php else: ?>
<table class="data">
    <thead><tr><th>Schlüssel</th><th>Bezeichnung</th><th>Anzahl</th><th>Schlüsselnummer</th><th>Status</th><th>Bemerkung</th></tr></thead><tbody>
    <?php foreach ($keys as $k): ?>
        <tr>
            <td><?= e($k['key_type']) ?></td>
            <td><?= e($k['custom_name']) ?></td>
            <td><?= $k['quantity'] !== null ? (int) $k['quantity'] : '' ?></td>
            <td><?= e($k['key_number']) ?></td>
            <td><?= e(key_statuses()[$k['status']] ?? '') ?></td>
            <td><?= e($k['comment']) ?></td>
        </tr>
    <?php endforeach; ?>
</tbody></table>
<?php endif; ?>

<h2>Weitere Übergabegegenstände</h2>
<?php if ($items === []): ?>
    <p class="empty">Keine weiteren Übergabegegenstände erfasst.</p>
<?php else: ?>
<table class="data">
    <thead><tr><th>Art</th><th>Bezeichnung</th><th>Anzahl</th><th>Zustand</th><th>Bemerkung</th></tr></thead><tbody>
    <?php foreach ($items as $it): ?>
        <tr>
            <td><?= e($it['item_type']) ?></td>
            <td><?= e($it['name']) ?></td>
            <td><?= $it['quantity'] !== null ? (int) $it['quantity'] : '' ?></td>
            <td><?= e($it['condition_status']) ?></td>
            <td><?= e($it['comment']) ?></td>
        </tr>
    <?php endforeach; ?>
</tbody></table>
<?php endif; ?>

<h2>Sonstige Vereinbarungen und Bemerkungen</h2>
<?php if ($publicNotes === []): ?>
    <p class="empty">Keine Vereinbarungen oder Bemerkungen erfasst.</p>
<?php else: ?>
<table class="data">
    <thead><tr><th>Kategorie</th><th>Text</th><th>Verantwortlich</th><th>Frist</th><th>Status</th></tr></thead><tbody>
    <?php foreach ($publicNotes as $n): ?>
        <tr>
            <td><?= e(note_categories()[$n['category']] ?? '') ?></td>
            <td><?= e($n['text']) ?><?= $n['comment'] ? '<br><span class="caption">' . e($n['comment']) . '</span>' : '' ?></td>
            <td><?= e($n['responsible_party']) ?></td>
            <td><?= e(fmt_date($n['due_date'])) ?></td>
            <td><?= e($n['status']) ?></td>
        </tr>
    <?php endforeach; ?>
</tbody></table>
<?php endif; ?>

<h2>Anhänge</h2>
<?php if ($attachmentsPublic === []): ?>
    <p class="empty">Keine Anhänge vorhanden.</p>
<?php else: ?>
<table class="data">
    <thead><tr><th>Datei</th><th>Kategorie</th><th>Beschreibung</th></tr></thead><tbody>
    <?php foreach ($attachmentsPublic as $f): ?>
        <tr><td><?= e($f['original_filename']) ?></td><td><?= e(attachment_categories()[$f['attachment_type']] ?? '') ?></td><td><?= e($f['description']) ?></td></tr>
    <?php endforeach; ?>
</tbody></table>
<?php endif; ?>

<h2>Unterschriften</h2>
<p style="font-size:8.5pt"><?= e(signature_consent_text()) ?></p>
<?php if ($signatures === []): ?>
    <p class="empty">Das Protokoll wurde ohne digitale Unterschrift abgeschlossen.</p>
<?php else: ?>
    <?php foreach ($signatures as $sig): ?>
        <div class="sig-block">
            <?php
            $sigFile = null;
            foreach ($files as $f) { if ((int) $f['id'] === (int) $sig['signature_file_id']) { $sigFile = $f; break; } }
            ?>
            <div class="sig-line"><?= $sigFile ? $img($sigFile, 60) : '' ?></div>
            <div class="caption">
                <?= e($sig['signer_name'] ?: '') ?>, <?= e(signature_roles($p['protocol_type'])[$sig['signer_role']] ?? $sig['signer_role']) ?><br>
                <?= e(trim(($sig['signed_location'] ? $sig['signed_location'] . ', ' : '') . ($hideTime ? fmt_date($sig['signed_at']) : fmt_datetime($sig['signed_at'])))) ?>
                <?= $sig['comment'] ? '<br>' . e($sig['comment']) : '' ?>
            </div>
        </div>
    <?php endforeach; ?>
<?php endif; ?>

<h2>Abschlussinformationen</h2>
<table class="kv">
    <tr><td class="k">Erstellt am</td><td><?= e($hideTime ? fmt_date($p['created_at']) : fmt_datetime($p['created_at'])) ?></td></tr>
    <?php if ($p['completed_at']): ?><tr><td class="k">Abgeschlossen am</td><td><?= e($hideTime ? fmt_date($p['completed_at']) : fmt_datetime($p['completed_at'])) ?></td></tr><?php endif; ?>
    <tr><td class="k">Dokument</td><td><?= e($p['protocol_number']) ?>, Version <?= (int) $p['version'] ?></td></tr>
</table>

</body>
</html>
