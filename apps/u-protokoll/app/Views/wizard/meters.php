<?php
$base = url('/protocols/' . $protocol['id']);
$filesByMeter = [];
foreach ($files as $f) {
    if ($f['meter_id']) { $filesByMeter[(int) $f['meter_id']][] = $f; }
}
require __DIR__ . '/_frame_top.php';

$meterFields = function (array $m = []) {
    ?>
    <div class="grid grid-3">
        <div class="field"><label>Zählertyp</label>
            <select name="meter_type">
                <option value=""></option>
                <?php foreach (meter_types() as $key => $label): ?>
                    <option value="<?= e($key) ?>" <?= ($m['meter_type'] ?? '') === $key ? 'selected' : '' ?>><?= e($label) ?></option>
                <?php endforeach; ?>
            </select></div>
        <div class="field"><label>Individuelle Bezeichnung</label><input type="text" name="custom_type" value="<?= e($m['custom_type'] ?? '') ?>"></div>
        <div class="field"><label>Zählernummer</label><input type="text" name="meter_number" value="<?= e($m['meter_number'] ?? '') ?>"></div>
        <div class="field"><label>Zählerstand</label><input type="text" inputmode="decimal" name="meter_value" value="<?= e($m['meter_value'] ?? '') ?>"></div>
        <div class="field"><label>Einheit</label>
            <select name="unit">
                <option value=""></option>
                <?php foreach (meter_units() as $u): ?>
                    <option <?= ($m['unit'] ?? '') === $u ? 'selected' : '' ?>><?= e($u) ?></option>
                <?php endforeach; ?>
                <option value="custom" <?= isset($m['unit']) && $m['unit'] !== '' && !in_array($m['unit'], meter_units(), true) && $m['unit'] !== null ? 'selected' : '' ?>>Frei definiert (Bemerkung nutzen)</option>
            </select></div>
        <div class="field"><label>Standort</label><input type="text" name="location" value="<?= e($m['location'] ?? '') ?>"></div>
        <div class="field"><label>Ablesedatum</label><input type="date" name="reading_date" value="<?= e($m['reading_date'] ?? '') ?>"></div>
        <div class="field"><label>Ableseuhrzeit</label><input type="time" name="reading_time" value="<?= e($m['reading_time'] ?? '') ?>"></div>
        <div class="field"><label>Bemerkung</label><input type="text" name="comment" value="<?= e($m['comment'] ?? '') ?>"></div>
    </div>
    <?php
};
?>

<div class="card">
    <h2>Zählerstände</h2>
    <div data-record-container data-entity="meter" data-base="<?= e($base) ?>" data-template="tpl-meter" data-sortable id="list-meters">
        <?php foreach ($meters as $m): ?>
            <div class="record-card" data-record-id="<?= (int) $m['id'] ?>" draggable="true">
                <div class="record-head">
                    <span><span class="drag-handle">⠿</span> <span class="record-title"><?= e(meter_types()[$m['meter_type']] ?? $m['custom_type'] ?? 'Zähler') ?></span></span>
                    <button type="button" class="btn btn-sm btn-danger" data-delete-record>Entfernen</button>
                </div>
                <?php $meterFields($m); ?>
                <label>Foto des Zählers</label>
                <?php $category = 'meter_photo'; $refField = 'meter_id'; $refValue = (int) $m['id']; $filesForZone = $filesByMeter[(int) $m['id']] ?? []; ?>
                <?php $files_backup = $files; $files = $filesForZone; include __DIR__ . '/_uploader.php'; $files = $files_backup; ?>
            </div>
        <?php endforeach; ?>
    </div>
    <div class="btn-row">
        <button type="button" class="btn btn-secondary" data-add-record="#list-meters">+ Weiteren Zähler hinzufügen</button>
        <button type="submit" form="wizard-form" name="_nav" value="next" class="btn">Keine weiteren Zähler, weiter</button>
    </div>
    <template id="tpl-meter">
        <div class="record-card" data-record-id="" draggable="true">
            <div class="record-head">
                <span><span class="drag-handle">⠿</span> <span class="record-title">Neuer Zähler</span></span>
                <button type="button" class="btn btn-sm btn-danger" data-delete-record>Entfernen</button>
            </div>
            <?php $meterFields(); ?>
            <label>Foto des Zählers</label>
            <?php $category = 'meter_photo'; $refField = 'meter_id'; $refValue = null; $files_backup = $files; $files = []; include __DIR__ . '/_uploader.php'; $files = $files_backup; ?>
        </div>
    </template>
</div>

<?php require __DIR__ . '/_frame_bottom.php'; ?>
