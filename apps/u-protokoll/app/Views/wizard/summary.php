<?php
/** Zusammenfassung vor Unterschrift: alle Bereiche mit Bearbeiten-Links und Hinweisen. */
$p = $protocol;
$base = url('/protocols/' . $p['id']);
[$outRole, $inRole, $outLabel, $inLabel] = party_roles($p['protocol_type']);

$hints = completion_hints([
    'protocol' => $p, 'participants' => $participants, 'meters' => $meters,
    'rooms' => $rooms, 'keys' => $keys, 'signatures' => $signatures,
]);

require __DIR__ . '/_frame_top.php';
?>

<?php if ($hints !== []): ?>
<div class="alert alert-warning">
    <strong>Hinweise (kein Abschlusshindernis):</strong>
    <ul style="margin:0.4rem 0 0 1.1rem">
        <?php foreach ($hints as $hint): ?><li><?= e($hint) ?></li><?php endforeach; ?>
    </ul>
</div>
<?php endif; ?>

<div class="card summary-section">
    <div class="section-head"><h2>Protokollart und Objekt</h2>
        <span><a class="edit-link" href="<?= e($base . '/wizard/type') ?>">Art bearbeiten</a> · <a class="edit-link" href="<?= e($base . '/wizard/object') ?>">Objekt bearbeiten</a></span></div>
    <dl class="kv">
        <dt>Protokollart</dt><dd><?= e(protocol_types()[$p['protocol_type']]) ?></dd>
        <dt>Objekt</dt><dd><?= e(protocol_address($p)) ?: '<span class="muted">–</span>' ?></dd>
        <dt>Einheit</dt><dd><?= e(trim(($p['unit_number'] ?? '') . ' ' . ($p['unit_position'] ?? '') . ' ' . ($p['floor'] ? 'Etage ' . $p['floor'] : ''))) ?: '–' ?></dd>
        <dt>Übergabedatum</dt><dd><?= e(fmt_date($p['handover_date'])) ?: '–' ?></dd>
        <?php if (!$p['hide_time_information']): ?>
            <dt>Zeit</dt><dd><?= e(trim(fmt_time($p['handover_start']) . ($p['handover_end'] ? ' bis ' . fmt_time($p['handover_end']) : ''))) ?: '–' ?></dd>
        <?php else: ?>
            <dt>Zeit</dt><dd class="muted">Wird im Protokoll nicht angezeigt</dd>
        <?php endif; ?>
        <dt>Ticketnummer</dt><dd><?= e($p['ticket_number']) ?: '–' ?></dd>
    </dl>
</div>

<div class="card summary-section">
    <div class="section-head"><h2>Beteiligte (<?= count($participants) ?>)</h2><a class="edit-link" href="<?= e($base . '/wizard/participants') ?>">Bearbeiten</a></div>
    <?php foreach ($participants as $pt): ?>
        <p style="margin:0.25rem 0"><strong><?= e(participant_role_label($pt['role'], $p['protocol_type'])) ?>:</strong>
            <?= e(trim(($pt['salutation'] ?? '') . ' ' . ($pt['first_name'] ?? '') . ' ' . ($pt['last_name'] ?? '') . ($pt['company'] ? ' (' . $pt['company'] . ')' : ''))) ?>
            <?php if ($pt['email']): ?><span class="muted small"><?= e($pt['email']) ?></span><?php endif; ?></p>
    <?php endforeach; ?>
    <?php if ($participants === []): ?><p class="muted">Keine Angaben.</p><?php endif; ?>
</div>

<div class="card summary-section">
    <div class="section-head"><h2>Kaution / Bankverbindung</h2><a class="edit-link" href="<?= e($base . '/wizard/deposit') ?>">Bearbeiten</a></div>
    <?php if ($bank): ?>
        <dl class="kv">
            <?php if ($bank['deposit_amount'] !== null): ?><dt>Kautionsbetrag</dt><dd><?= e(fmt_amount($bank['deposit_amount'])) ?></dd><?php endif; ?>
            <?php if ($bank['iban']): ?><dt>IBAN</dt><dd><?= e($bank['iban']) ?><?= $bank['iban'] && !iban_is_valid($bank['iban']) ? ' <span class="badge badge-rework">formal ungültig</span>' : '' ?></dd><?php endif; ?>
            <?php if ($bank['account_holder']): ?><dt>Kontoinhaber</dt><dd><?= e($bank['account_holder']) ?></dd><?php endif; ?>
            <?php if ($bank['bank_name']): ?><dt>Bank</dt><dd><?= e($bank['bank_name']) ?></dd><?php endif; ?>
        </dl>
    <?php else: ?><p class="muted">Keine Angaben.</p><?php endif; ?>
</div>

<div class="card summary-section">
    <div class="section-head"><h2>Zählerstände (<?= count($meters) ?>)</h2><a class="edit-link" href="<?= e($base . '/wizard/meters') ?>">Bearbeiten</a></div>
    <?php foreach ($meters as $m): ?>
        <p style="margin:0.25rem 0"><?= e($m['custom_type'] ?: (meter_types()[$m['meter_type']] ?? 'Zähler')) ?>
            <?= $m['meter_number'] ? '(Nr. ' . e($m['meter_number']) . ')' : '' ?>:
            <strong><?= e($m['meter_value']) ?: '–' ?> <?= e($m['unit']) ?></strong></p>
    <?php endforeach; ?>
    <?php if ($meters === []): ?><p class="muted">Keine Angaben.</p><?php endif; ?>
</div>

<div class="card summary-section">
    <div class="section-head"><h2>Räume und Mängel (<?= count($rooms) ?> / <?= count($defects) ?>)</h2><a class="edit-link" href="<?= e($base . '/wizard/rooms') ?>">Bearbeiten</a></div>
    <?php foreach ($rooms as $room): ?>
        <p style="margin:0.25rem 0"><strong><?= e($room['room_name'] ?: $room['room_type'] ?: 'Raum') ?>:</strong>
            <?= e(room_conditions()[$room['condition_status']] ?? 'Keine Angabe') ?>
            <?php $count = count(array_filter($defects, fn($d) => (int) $d['room_id'] === (int) $room['id'])); ?>
            <?= $count ? '<span class="badge badge-rework">' . $count . ' Mangel/Mängel</span>' : '' ?></p>
    <?php endforeach; ?>
    <?php if ($rooms === []): ?><p class="muted">Keine Angaben.</p><?php endif; ?>
</div>

<div class="card summary-section">
    <div class="section-head"><h2>Schlüssel (<?= count($keys) ?>) und Gegenstände (<?= count($items) ?>)</h2>
        <span><a class="edit-link" href="<?= e($base . '/wizard/keys') ?>">Schlüssel</a> · <a class="edit-link" href="<?= e($base . '/wizard/items') ?>">Gegenstände</a></span></div>
    <?php foreach ($keys as $k): ?>
        <p style="margin:0.25rem 0"><?= e($k['custom_name'] ?: $k['key_type'] ?: 'Schlüssel') ?>, Anzahl: <?= $k['quantity'] !== null ? (int) $k['quantity'] : '–' ?>
            <?= $k['status'] ? '(' . e(key_statuses()[$k['status']] ?? '') . ')' : '' ?></p>
    <?php endforeach; ?>
    <?php foreach ($items as $it): ?>
        <p style="margin:0.25rem 0"><?= e($it['name'] ?: $it['item_type'] ?: 'Gegenstand') ?><?= $it['quantity'] !== null ? ', Anzahl: ' . (int) $it['quantity'] : '' ?></p>
    <?php endforeach; ?>
    <?php if ($keys === [] && $items === []): ?><p class="muted">Keine Angaben.</p><?php endif; ?>
</div>

<div class="card summary-section">
    <div class="section-head"><h2>Vereinbarungen (<?= count($notes) ?>) und Anhänge</h2>
        <span><a class="edit-link" href="<?= e($base . '/wizard/notes') ?>">Bemerkungen</a> · <a class="edit-link" href="<?= e($base . '/wizard/attachments') ?>">Anhänge</a></span></div>
    <?php foreach ($notes as $n): ?>
        <p style="margin:0.25rem 0"><?= !empty($n['is_internal']) ? '<span class="badge badge-draft">intern</span> ' : '' ?><?= e($n['text']) ?>
            <?= $n['due_date'] ? '<span class="muted small">Frist: ' . e(fmt_date($n['due_date'])) . '</span>' : '' ?></p>
    <?php endforeach; ?>
    <?php $attachmentCount = count(array_filter($files, fn($f) => $f['file_category'] === 'attachment')); ?>
    <p class="muted small"><?= $attachmentCount ?> Anhang/Anhänge, <?= count(array_filter($files, fn($f) => str_contains((string) $f['file_category'], 'photo'))) ?> Foto(s) insgesamt.</p>
</div>

<div class="card summary-section">
    <div class="section-head"><h2>Unterschriften (<?= count($signatures) ?>)</h2><a class="edit-link" href="<?= e($base . '/wizard/signatures') ?>">Zu den Unterschriften</a></div>
    <?php foreach ($signatures as $sig): ?>
        <p style="margin:0.25rem 0"><?= e($sig['signer_name'] ?: 'Ohne Namen') ?>, <?= e(signature_roles($p['protocol_type'])[$sig['signer_role']] ?? $sig['signer_role']) ?>, <?= e(fmt_datetime($sig['signed_at'])) ?></p>
    <?php endforeach; ?>
    <?php if ($signatures === []): ?><p class="muted">Noch keine Unterschriften. Das Protokoll kann auch ohne Unterschrift abgeschlossen werden.</p><?php endif; ?>
</div>

<div class="card">
    <h2>Protokoll abschließen</h2>
    <?php if (\App\Core\Auth::isHelper()): ?>
        <p class="muted small">Beim Abschluss wird das Protokoll festgeschrieben und als PDF erzeugt. Sie und alle Beteiligten mit hinterlegter E-Mail-Adresse erhalten das PDF automatisch. Änderungen sind danach nicht mehr möglich.</p>
    <?php else: ?>
        <p class="muted small">Beim Abschluss wird das Protokoll gesperrt, als PDF erzeugt und im Dateispeicher abgelegt. Nachträgliche Änderungen sind nur über eine neue Version möglich.</p>
    <?php endif; ?>
    <div class="btn-row">
        <a class="btn btn-secondary" href="<?= e($base . '/wizard/signatures') ?>">Zurück und ergänzen</a>
        <a class="btn btn-secondary" href="<?= e($base . '/print') ?>" target="_blank" rel="noopener">Druckansicht</a>
        <button type="submit" form="wizard-form" name="_nav" value="exit" class="btn btn-secondary">Als Entwurf speichern</button>
    </div>
</div>
<?php require __DIR__ . '/_frame_bottom.php'; ?>

<?php // Wichtig: außerhalb des Wizard-Formulars (verschachtelte Formulare sind unzulässig) ?>
<?php if (\App\Core\Auth::isHelper()): ?>
    <?php // Gehilfen: serverseitige Rückfrage mit Ja/Nein auf eigener Seite ?>
    <a class="btn btn-success btn-block" style="margin-bottom:1rem" href="<?= e($base . '/confirm?from=summary') ?>">Übergabe abschließen und festschreiben</a>
<?php else: ?>
<form method="post" action="<?= e($base . '/complete') ?>" <?= $hints !== [] ? 'data-confirm="Es liegen Hinweise vor. Möchten Sie das Protokoll trotzdem verbindlich abschließen? Es wird danach gesperrt und als PDF erzeugt."' : 'data-confirm-complete' ?> style="margin-bottom:1rem">
    <?= \App\Core\Csrf::field() ?>
    <input type="hidden" name="from" value="summary">
    <?php if ($hints !== []): ?><input type="hidden" name="force" value="1"><?php endif; ?>
    <button type="submit" class="btn btn-success btn-block"><?= $hints !== [] ? 'Trotz Hinweisen verbindlich abschließen' : 'Protokoll verbindlich abschließen' ?></button>
</form>
<?php endif; ?>
