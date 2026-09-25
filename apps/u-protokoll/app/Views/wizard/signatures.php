<?php
/**
 * Unterschriften: mehrere Felder gleichzeitig. Für jede Hauptpartei wird
 * automatisch ein Feld angezeigt (mindestens zwei), weitere Felder können
 * beliebig ergänzt werden (Verwaltung, Makler, Zeuge, ...).
 */
$p = $protocol;
$base = url('/protocols/' . $p['id']);
$roles = signature_roles($p['protocol_type']);
[$outRole, $inRole, $outLabel, $inLabel] = party_roles($p['protocol_type']);

// Vorbelegung: ein Feld je Person der beiden Hauptrollen, mindestens je eines.
// Wer bereits unterschrieben hat, bekommt kein neues leeres Feld (keine Dubletten).
$signedParticipantIds = [];
$signedRoles = [];
foreach ($signatures as $sig) {
    if (!empty($sig['participant_id'])) {
        $signedParticipantIds[(int) $sig['participant_id']] = true;
    }
    if (!empty($sig['signer_role'])) {
        $signedRoles[$sig['signer_role']] = true;
    }
}
$pads = [];
foreach ($participants as $pt) {
    if (in_array($pt['role'], [$outRole, $inRole], true) && !isset($signedParticipantIds[(int) $pt['id']])) {
        $pads[] = [
            'role'           => $pt['role'],
            'name'           => trim(($pt['first_name'] ?? '') . ' ' . ($pt['last_name'] ?? '')) ?: ($pt['company'] ?? ''),
            'participant_id' => (int) $pt['id'],
        ];
    }
}
$roleCovered = fn(string $role) => isset($signedRoles[$role])
    || (bool) array_filter($pads, fn($pad) => $pad['role'] === $role);
if (!$roleCovered($outRole)) { array_unshift($pads, ['role' => $outRole, 'name' => '', 'participant_id' => null]); }
if (!$roleCovered($inRole)) { $pads[] = ['role' => $inRole, 'name' => '', 'participant_id' => null]; }

require __DIR__ . '/_frame_top.php';

/** Rendert ein Signatur-Widget. */
$renderPad = function (array $pad) use ($base, $roles, $participants, $p) {
    ?>
    <div class="signature-widget" data-signature-widget="<?= e($base . '/signatures/save') ?>">
        <div class="sig-role-title"><?= e($roles[$pad['role']] ?? 'Unterschrift') ?></div>
        <div class="field"><label>Name</label>
            <input type="text" name="signer_name" value="<?= e($pad['name']) ?>" data-no-recordsave></div>
        <div class="grid grid-2">
            <div class="field"><label>Rolle</label>
                <select name="signer_role" data-no-recordsave>
                    <?php foreach ($roles as $key => $label): ?>
                        <option value="<?= e($key) ?>" <?= $pad['role'] === $key ? 'selected' : '' ?>><?= e($label) ?></option>
                    <?php endforeach; ?>
                </select></div>
            <div class="field"><label>Ort</label>
                <input type="text" name="signed_location" value="<?= e($p['city'] ?? '') ?>" data-no-recordsave></div>
        </div>
        <input type="hidden" name="participant_id" value="<?= e((string) ($pad['participant_id'] ?? '')) ?>">
        <div class="field"><label>Bemerkung (optional)</label>
            <input type="text" name="sig_comment" data-no-recordsave></div>
        <label>Unterschrift (Finger, Stift oder Maus)</label>
        <canvas class="signature-pad"></canvas>
        <div class="btn-row">
            <button type="button" class="btn btn-secondary btn-sm" data-sig-clear>Leeren</button>
            <button type="button" class="btn btn-sm" data-sig-save>Unterschrift speichern</button>
        </div>
        <p class="sig-message muted small" aria-live="polite"></p>
    </div>
    <?php
};
?>

<div class="card">
    <h2>Unterschriften <span class="muted small">(alle optional, beliebig viele)</span></h2>
    <div class="alert alert-info small"><?= e(signature_consent_text()) ?></div>

    <?php if ($signatures !== []): ?>
        <h3>Bereits erfasste Unterschriften (<span id="sig-count"><?= count($signatures) ?></span>)</h3>
        <div class="signature-grid">
        <?php foreach ($signatures as $sig): ?>
            <div class="signature-widget saved">
                <div class="record-head">
                    <span class="sig-role-title"><?= e($sig['signer_name'] ?: 'Ohne Namen') ?>, <?= e($roles[$sig['signer_role']] ?? $sig['signer_role']) ?></span>
                    <button type="button" class="btn btn-sm btn-danger" data-sig-delete="<?= e($base . '/signatures/' . $sig['id'] . '/delete') ?>">Löschen</button>
                </div>
                <p class="muted small"><?= e(fmt_datetime($sig['signed_at'])) ?><?= $sig['signed_location'] ? ', ' . e($sig['signed_location']) : '' ?></p>
                <?php if ($sig['signature_file_id']): ?>
                    <img src="<?= e(url('/files/' . $sig['signature_file_id'])) ?>" alt="Unterschrift" style="max-height:80px;max-width:100%;background:#fff;border:1px solid var(--color-border);border-radius:8px">
                <?php endif; ?>
            </div>
        <?php endforeach; ?>
        </div>
    <?php endif; ?>

    <h3>Unterschriftenfelder</h3>
    <div class="signature-grid" id="signature-grid">
        <?php foreach ($pads as $pad): ?>
            <?php $renderPad($pad); ?>
        <?php endforeach; ?>
    </div>

    <div class="btn-row">
        <button type="button" class="btn btn-secondary" id="add-signature-pad">+ Weiteres Unterschriftsfeld</button>
    </div>
    <template id="tpl-signature-pad">
        <?php $renderPad(['role' => 'other', 'name' => '', 'participant_id' => null]); ?>
    </template>
    <p class="muted small">Datum und Uhrzeit werden beim Speichern automatisch erfasst. Das Protokoll kann auch ohne Unterschrift abgeschlossen werden.</p>
</div>

<div class="card">
    <div class="btn-row">
        <a class="btn btn-secondary" href="<?= e($base . '/wizard/summary') ?>">Zurück zur Prüfung</a>
    </div>
</div>

<?php require __DIR__ . '/_frame_bottom.php'; ?>

<?php // Wichtig: außerhalb des Wizard-Formulars (verschachtelte Formulare sind unzulässig) ?>
<?php
$isHelper = \App\Core\Auth::isHelper();
// Liegen Hinweise vor, zeigt der erste Klick zunächst die Hinweise (kein Dialog),
// erst die Bestätigung im Hinweisbanner fragt nach
$hasHints = completion_hints([
    'protocol' => $p, 'participants' => $participants, 'meters' => $meters,
    'rooms' => $rooms, 'keys' => $keys, 'signatures' => $signatures,
]) !== [];
?>
<?php if ($isHelper): ?>
    <a class="btn btn-success btn-block" style="margin-bottom:0.5rem" href="<?= e($base . '/confirm?from=signatures') ?>">Übergabe abschließen und festschreiben</a>
    <p class="muted small" style="margin-top:0">
        Vor dem Abschluss werden Sie noch einmal gefragt. Danach erhalten Sie und alle Beteiligten mit hinterlegter
        E-Mail-Adresse das Protokoll automatisch als PDF. Änderungen sind dann nicht mehr möglich.
    </p>
<?php else: ?>
<form method="post" action="<?= e($base . '/complete') ?>" <?= $hasHints ? '' : 'data-confirm-complete' ?> style="margin-bottom:1rem">
    <?= \App\Core\Csrf::field() ?>
    <input type="hidden" name="from" value="signatures">
    <button type="submit" class="btn btn-success btn-block">Protokoll verbindlich abschließen</button>
</form>
<?php endif; ?>
