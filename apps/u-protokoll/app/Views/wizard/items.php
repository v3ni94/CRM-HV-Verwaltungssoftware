<?php
$base = url('/protocols/' . $protocol['id']);
$filesByItem = [];
foreach ($files as $f) {
    if (!empty($f['item_id'])) { $filesByItem[(int) $f['item_id']][] = $f; }
}
require __DIR__ . '/_frame_top.php';

$itemFields = function (array $it = []) {
    ?>
    <div class="grid grid-3">
        <div class="field"><label>Art</label>
            <select name="item_type">
                <option value=""></option>
                <?php foreach (item_types() as $t): ?>
                    <option <?= ($it['item_type'] ?? '') === $t ? 'selected' : '' ?>><?= e($t) ?></option>
                <?php endforeach; ?>
            </select></div>
        <div class="field"><label>Bezeichnung</label><input type="text" name="name" value="<?= e($it['name'] ?? '') ?>"></div>
        <div class="field"><label>Anzahl</label><input type="number" name="quantity" min="0" value="<?= e(isset($it['quantity']) ? (string) $it['quantity'] : '') ?>"></div>
        <div class="field"><label>Zustand</label><input type="text" name="condition_status" value="<?= e($it['condition_status'] ?? '') ?>"></div>
        <div class="field" style="grid-column:span 2"><label>Bemerkung</label><input type="text" name="comment" value="<?= e($it['comment'] ?? '') ?>"></div>
    </div>
    <?php
};
?>

<div class="card">
    <h2>Weitere Übergabegegenstände</h2>
    <p class="muted small">Fernbedienungen, Zugangskarten, Unterlagen, Energieausweis, Geräte, Möbel und sonstige Gegenstände.</p>
    <div data-record-container data-entity="item" data-base="<?= e($base) ?>" data-template="tpl-item" data-sortable id="list-items">
        <?php foreach ($items as $it): ?>
            <div class="record-card" data-record-id="<?= (int) $it['id'] ?>" draggable="true">
                <div class="record-head">
                    <span><span class="drag-handle">⠿</span> <span class="record-title"><?= e($it['name'] ?: $it['item_type'] ?: 'Gegenstand') ?></span></span>
                    <button type="button" class="btn btn-sm btn-danger" data-delete-record>Entfernen</button>
                </div>
                <?php $itemFields($it); ?>
                <label>Foto</label>
                <?php $category = 'item_photo'; $refField = 'item_id'; $refValue = (int) $it['id']; $files_backup = $files; $files = $filesByItem[(int) $it['id']] ?? []; include __DIR__ . '/_uploader.php'; $files = $files_backup; ?>
            </div>
        <?php endforeach; ?>
    </div>
    <div class="btn-row">
        <button type="button" class="btn btn-secondary" data-add-record="#list-items">+ Weiteren Gegenstand erfassen</button>
        <button type="submit" form="wizard-form" name="_nav" value="next" class="btn">Keine weiteren Gegenstände, weiter</button>
    </div>
    <template id="tpl-item">
        <div class="record-card" data-record-id="" draggable="true">
            <div class="record-head">
                <span><span class="drag-handle">⠿</span> <span class="record-title">Neuer Gegenstand</span></span>
                <button type="button" class="btn btn-sm btn-danger" data-delete-record>Entfernen</button>
            </div>
            <?php $itemFields(); ?>
            <p class="muted small">Ein Foto kann nach dem ersten Speichern hochgeladen werden.</p>
        </div>
    </template>
</div>

<?php require __DIR__ . '/_frame_bottom.php'; ?>
