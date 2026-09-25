<?php
$base = url('/protocols/' . $protocol['id']);
require __DIR__ . '/_frame_top.php';

$noteFields = function (array $n = []) {
    ?>
    <div class="field"><label>Text</label>
        <textarea name="text" placeholder="z. B. Der Mieter reicht den zweiten Kellerschlüssel bis zum 05.09.2026 nach."><?= e($n['text'] ?? '') ?></textarea></div>
    <div class="grid grid-4">
        <div class="field"><label>Kategorie</label>
            <select name="category">
                <option value=""></option>
                <?php foreach (note_categories() as $key => $label): ?>
                    <option value="<?= e($key) ?>" <?= ($n['category'] ?? '') === $key ? 'selected' : '' ?>><?= e($label) ?></option>
                <?php endforeach; ?>
            </select></div>
        <div class="field"><label>Verantwortlich</label><input type="text" name="responsible_party" value="<?= e($n['responsible_party'] ?? '') ?>"></div>
        <div class="field"><label>Frist</label><input type="date" name="due_date" value="<?= e($n['due_date'] ?? '') ?>"></div>
        <div class="field"><label>Status</label><input type="text" name="status" value="<?= e($n['status'] ?? '') ?>"></div>
    </div>
    <div class="field"><label>Kommentar</label><input type="text" name="comment" value="<?= e($n['comment'] ?? '') ?>"></div>
    <?php if (!\App\Core\Auth::isHelper()): ?>
    <div class="checkbox-row">
        <input type="checkbox" name="is_internal" value="1" id="int_<?= e((string) ($n['id'] ?? 'new')) ?>" <?= !empty($n['is_internal']) ? 'checked' : '' ?>>
        <label for="int_<?= e((string) ($n['id'] ?? 'new')) ?>">Intern, nicht im Kunden-PDF anzeigen</label>
    </div>
    <?php endif; ?>
    <?php
};
?>

<div class="card">
    <h2>Sonstige Vereinbarungen und Bemerkungen</h2>
    <div data-record-container data-entity="note" data-base="<?= e($base) ?>" data-template="tpl-note" data-sortable id="list-notes">
        <?php foreach ($notes as $n): ?>
            <div class="record-card" data-record-id="<?= (int) $n['id'] ?>" draggable="true">
                <div class="record-head">
                    <span><span class="drag-handle">⠿</span> <span class="record-title"><?= e(note_categories()[$n['category']] ?? 'Bemerkung') ?><?= !empty($n['is_internal']) ? ' (intern)' : '' ?></span></span>
                    <button type="button" class="btn btn-sm btn-danger" data-delete-record>Entfernen</button>
                </div>
                <?php $noteFields($n); ?>
            </div>
        <?php endforeach; ?>
    </div>
    <button type="button" class="btn btn-secondary" data-add-record="#list-notes">+ Weiteren Punkt hinzufügen</button>
    <template id="tpl-note">
        <div class="record-card" data-record-id="" draggable="true">
            <div class="record-head">
                <span><span class="drag-handle">⠿</span> <span class="record-title">Neuer Punkt</span></span>
                <button type="button" class="btn btn-sm btn-danger" data-delete-record>Entfernen</button>
            </div>
            <?php $noteFields(); ?>
        </div>
    </template>
</div>

<?php require __DIR__ . '/_frame_bottom.php'; ?>
