<?php $p = $protocol; require __DIR__ . '/_frame_top.php'; ?>

<div class="card">
    <h2>Ticket / interne Informationen</h2>
    <div class="grid grid-3">
        <div class="field"><label>Systemticketnummer</label><input type="text" name="ticket_number" value="<?= e($p['ticket_number']) ?>"></div>
        <div class="field"><label>Vorgangsnummer</label><input type="text" name="case_number" value="<?= e($p['case_number']) ?>"></div>
        <div class="field"><label>Zuständige Niederlassung</label>
            <select name="branch_id">
                <option value=""></option>
                <?php foreach (\App\Core\Database::fetchAll('SELECT * FROM branches WHERE is_active = 1 ORDER BY name') as $branch): ?>
                    <option value="<?= (int) $branch['id'] ?>" <?= (int) ($p['branch_id'] ?? 0) === (int) $branch['id'] ? 'selected' : '' ?>><?= e($branch['name']) ?></option>
                <?php endforeach; ?>
            </select></div>
        <div class="field"><label>Interner Ansprechpartner</label><input type="text" name="internal_contact" value="<?= e($p['internal_contact']) ?>"></div>
    </div>
    <div class="field">
        <label>Interne Bemerkung</label>
        <textarea name="internal_note" placeholder="Nur für interne Zwecke"><?= e($p['internal_note']) ?></textarea>
        <p class="alert alert-info small" style="margin-top:0.4rem">Interne Bemerkungen werden <strong>nicht</strong> in das Kunden-PDF übernommen.</p>
    </div>
</div>

<?php require __DIR__ . '/_frame_bottom.php'; ?>
