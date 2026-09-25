<?php
/** Separater Mängellisten-Export: Raum, Mangel, Priorität, Bemerkung, Fotos. */
use App\Services\PdfService;

$p = $protocol;
$roomsById = [];
foreach ($rooms as $room) { $roomsById[(int) $room['id']] = $room; }
$photosByDefect = [];
foreach ($files as $f) {
    if ($f['defect_id'] && !$f['is_internal'] && str_starts_with((string) $f['mime_type'], 'image/')) {
        $photosByDefect[(int) $f['defect_id']][] = $f;
    }
}
?>
<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>Mängelliste <?= e($p['protocol_number']) ?></title>
<style>
    body { font-family: DejaVu Sans, Helvetica, Arial, sans-serif; font-size: 9.5pt; color: #1A1A1A; }
    .kennlinie { height: 6px; font-size: 0; line-height: 0; margin-bottom: 10px; }
    .kennlinie span { display: inline-block; height: 6px; }
    h1 { font-size: 14pt; color: #1A1A1A; }
    table { width: 100%; border-collapse: collapse; }
    td, th { border: 1px solid #D7D8DA; padding: 4px 6px; font-size: 9pt; vertical-align: top; text-align: left; word-wrap: break-word; }
    th { background: #ECECEC; }
    img { max-height: 110px; max-width: 200px; margin: 2px; }
    .caption { font-size: 7.5pt; color: #87888A; }
    .logo { width: 55px; float: right; }
</style>
</head>
<body>
<div class="kennlinie"><span style="width:40%;background:#87888A"></span><span style="width:20%;background:#9C9D9F"></span><span style="width:7.5%;background:#E6A83C"></span><span style="width:32.5%;background:#D7D8DA"></span></div>
<?php $logo = PdfService::logoDataUri(); if ($logo): ?><img class="logo" src="<?= $logo ?>" alt=""><?php endif; ?>
<h1>Mängelliste zum Protokoll <?= e($p['protocol_number']) ?></h1>
<p><?= e(protocol_address($p)) ?><?= $p['handover_date'] ? ' · Übergabe am ' . e(fmt_date($p['handover_date'])) : '' ?></p>

<?php if ($defects === []): ?>
    <p>Es wurden keine Mängel erfasst.</p>
<?php else: ?>
<table>
    <thead><tr><th>Raum</th><th>Mangel</th><th>Priorität</th><th>Bemerkung</th><th>Fotos</th></tr></thead>
    <tbody>
    <?php foreach ($defects as $d): $room = $roomsById[(int) $d['room_id']] ?? null; ?>
        <tr>
            <td><?= e($room ? ($room['room_name'] ?: $room['room_type']) : '–') ?></td>
            <td><strong><?= e($d['title'] ?: $d['category']) ?></strong><?= $d['description'] ? '<br>' . e($d['description']) : '' ?><?= $d['location'] ? '<br><span class="caption">Position: ' . e($d['location']) . '</span>' : '' ?></td>
            <td><?= e(defect_priorities()[$d['priority']] ?? '') ?></td>
            <td><?= e(trim(($d['comment'] ?? '') . ' ' . ($d['responsibility'] ? 'Verantwortlich: ' . $d['responsibility'] : ''))) ?></td>
            <td><?php foreach ($photosByDefect[(int) $d['id']] ?? [] as $ph): $src = PdfService::imageDataUri($ph['storage_path'], $ph['mime_type']); ?>
                <?= $src ? '<img src="' . e($src) . '" alt="">' : '' ?>
            <?php endforeach; ?></td>
        </tr>
    <?php endforeach; ?>
    </tbody>
</table>
<?php endif; ?>
</body>
</html>
