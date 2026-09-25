<?php
$p = $protocol;
$base = url('/protocols/' . $p['id']);
$selectAll = isset($_GET['all']);
$withEmail = array_values(array_filter($participants, fn($pt) => !empty($pt['email'])));
$attachables = array_values(array_filter($files, fn($f) => $f['file_category'] === 'attachment' && !$f['is_internal']));
?>
<h1>E-Mail-Versand: <?= e($p['protocol_number']) ?></h1>
<p class="muted"><?= e(protocol_address($p)) ?></p>

<form method="post" action="<?= e($base . '/email/send') ?>" class="card">
    <?= \App\Core\Csrf::field() ?>

    <h2>Beteiligte als Empfänger</h2>
    <?php if ($withEmail === []): ?>
        <p class="muted">Für die Beteiligten sind keine E-Mail-Adressen hinterlegt.</p>
    <?php endif; ?>
    <?php foreach ($withEmail as $i => $pt): ?>
        <div class="checkbox-row">
            <input type="checkbox" id="pt<?= $i ?>" name="participant_emails[]" value="<?= e($pt['email']) ?>" <?= $selectAll ? 'checked' : '' ?>>
            <label for="pt<?= $i ?>"><?= e(trim(($pt['first_name'] ?? '') . ' ' . ($pt['last_name'] ?? '')) ?: $pt['company']) ?>
                <span class="muted">(<?= e(participant_role_label($pt['role'], $p['protocol_type'])) ?>, <?= e($pt['email']) ?>)</span></label>
        </div>
    <?php endforeach; ?>

    <h2>Manuelle Empfänger</h2>
    <div class="grid grid-3">
        <div class="field"><label>Empfänger (mehrere mit Komma)</label><input type="text" name="to" inputmode="email"></div>
        <div class="field"><label>CC</label><input type="text" name="cc" inputmode="email"></div>
        <div class="field"><label>BCC</label><input type="text" name="bcc" inputmode="email"></div>
    </div>

    <div class="field"><label>Betreff</label><input type="text" name="subject" value="<?= e($subject) ?>"></div>
    <div class="field"><label>Nachricht</label><textarea name="body" rows="10"><?= e($body) ?></textarea></div>

    <p class="muted small">Das Protokoll-PDF wird automatisch angehängt<?= \App\Repositories\ProtocolRepository::isLocked($p) ? '' : ' (Entwurfsfassung, da das Protokoll noch nicht abgeschlossen ist)' ?>.</p>

    <?php if ($attachables !== []): ?>
        <h3>Weitere Anhänge</h3>
        <?php foreach ($attachables as $i => $f): ?>
            <div class="checkbox-row">
                <input type="checkbox" id="att<?= $i ?>" name="attach_file_ids[]" value="<?= (int) $f['id'] ?>">
                <label for="att<?= $i ?>"><?= e($f['original_filename']) ?> <span class="muted small">(<?= e(number_format((int) $f['file_size'] / 1024, 0, ',', '.')) ?> KB)</span></label>
            </div>
        <?php endforeach; ?>
    <?php endif; ?>

    <div class="btn-row">
        <a class="btn btn-secondary" href="<?= e($base) ?>">Abbrechen</a>
        <button type="submit" class="btn">E-Mail versenden</button>
    </div>
</form>
