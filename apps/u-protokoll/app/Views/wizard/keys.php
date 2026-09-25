<?php
$base = url('/protocols/' . $protocol['id']);
require __DIR__ . '/_frame_top.php';

$keyFields = function (array $k = []) {
    ?>
    <div class="grid grid-3">
        <div class="field"><label>Schlüsselart</label>
            <select name="key_type">
                <option value=""></option>
                <?php foreach (key_types() as $kt): ?>
                    <option <?= ($k['key_type'] ?? '') === $kt ? 'selected' : '' ?>><?= e($kt) ?></option>
                <?php endforeach; ?>
            </select></div>
        <div class="field"><label>Individuelle Bezeichnung</label><input type="text" name="custom_name" value="<?= e($k['custom_name'] ?? '') ?>" placeholder="z. B. Technikraum Keller"></div>
        <div class="field"><label>Anzahl</label><input type="number" name="quantity" min="0" value="<?= e(isset($k['quantity']) ? (string) $k['quantity'] : '') ?>"></div>
        <div class="field"><label>Schlüsselnummer</label><input type="text" name="key_number" value="<?= e($k['key_number'] ?? '') ?>"></div>
        <div class="field"><label>Status</label>
            <select name="status">
                <option value=""></option>
                <?php foreach (key_statuses() as $key => $label): ?>
                    <option value="<?= e($key) ?>" <?= ($k['status'] ?? '') === $key ? 'selected' : '' ?>><?= e($label) ?></option>
                <?php endforeach; ?>
            </select></div>
        <div class="field"><label>Bemerkung</label><input type="text" name="comment" value="<?= e($k['comment'] ?? '') ?>"></div>
    </div>
    <?php
};
?>

<div class="card">
    <h2>Schlüsselübergabe</h2>
    <div data-record-container data-entity="key" data-base="<?= e($base) ?>" data-template="tpl-key" data-sortable id="list-keys">
        <?php foreach ($keys as $k): ?>
            <div class="record-card" data-record-id="<?= (int) $k['id'] ?>" draggable="true">
                <div class="record-head">
                    <span><span class="drag-handle">⠿</span> <span class="record-title"><?= e($k['custom_name'] ?: $k['key_type'] ?: 'Schlüssel') ?><?= $k['quantity'] !== null ? ', Anzahl: ' . (int) $k['quantity'] : '' ?></span></span>
                    <button type="button" class="btn btn-sm btn-danger" data-delete-record>Entfernen</button>
                </div>
                <?php $keyFields($k); ?>
            </div>
        <?php endforeach; ?>
    </div>
    <div class="btn-row">
        <button type="button" class="btn btn-secondary" data-add-record="#list-keys">+ Weiteren Schlüssel erfassen</button>
        <button type="submit" form="wizard-form" name="_nav" value="next" class="btn">Keine weiteren Schlüssel, weiter</button>
    </div>
    <template id="tpl-key">
        <div class="record-card" data-record-id="" draggable="true">
            <div class="record-head">
                <span><span class="drag-handle">⠿</span> <span class="record-title">Neuer Schlüssel</span></span>
                <button type="button" class="btn btn-sm btn-danger" data-delete-record>Entfernen</button>
            </div>
            <?php $keyFields(); ?>
        </div>
    </template>
</div>

<?php require __DIR__ . '/_frame_bottom.php'; ?>
