<?php
/** Raum-für-Raum-Abnahme inkl. Mängelerfassung und Fotos. */
$base = url('/protocols/' . $protocol['id']);
$defectsByRoom = [];
foreach ($defects as $d) {
    $defectsByRoom[(int) ($d['room_id'] ?? 0)][] = $d;
}
$filesByRoom = [];
$filesByDefect = [];
foreach ($files as $f) {
    if ($f['defect_id']) { $filesByDefect[(int) $f['defect_id']][] = $f; }
    elseif ($f['room_id']) { $filesByRoom[(int) $f['room_id']][] = $f; }
}
require __DIR__ . '/_frame_top.php';

$defectFields = function (array $d = []) {
    ?>
    <div class="grid grid-3">
        <div class="field"><label>Kategorie</label>
            <select name="category">
                <option value=""></option>
                <?php foreach (defect_categories() as $c): ?>
                    <option <?= ($d['category'] ?? '') === $c ? 'selected' : '' ?>><?= e($c) ?></option>
                <?php endforeach; ?>
            </select></div>
        <div class="field"><label>Kurzbezeichnung</label><input type="text" name="title" value="<?= e($d['title'] ?? '') ?>"></div>
        <div class="field"><label>Position im Raum</label><input type="text" name="location" value="<?= e($d['location'] ?? '') ?>"></div>
        <div class="field"><label>Priorität</label>
            <select name="priority">
                <option value=""></option>
                <?php foreach (defect_priorities() as $key => $label): ?>
                    <option value="<?= e($key) ?>" <?= ($d['priority'] ?? '') === $key ? 'selected' : '' ?>><?= e($label) ?></option>
                <?php endforeach; ?>
            </select></div>
        <div class="field"><label>Zustand / Feststellung</label>
            <select name="defect_status">
                <option value=""></option>
                <?php foreach (defect_statuses() as $key => $label): ?>
                    <option value="<?= e($key) ?>" <?= ($d['defect_status'] ?? '') === $key ? 'selected' : '' ?>><?= e($label) ?></option>
                <?php endforeach; ?>
            </select></div>
        <div class="field"><label>Verantwortlichkeit</label><input type="text" name="responsibility" value="<?= e($d['responsibility'] ?? '') ?>"></div>
    </div>
    <div class="field"><label>Detaillierte Beschreibung</label><textarea name="description"><?= e($d['description'] ?? '') ?></textarea></div>
    <div class="field"><label>Bemerkung</label><input type="text" name="comment" value="<?= e($d['comment'] ?? '') ?>"></div>
    <?php
};
?>

<div class="card">
    <h2>Raum-für-Raum-Abnahme</h2>
    <div data-record-container data-entity="room" data-base="<?= e($base) ?>" data-template="tpl-room" data-sortable id="list-rooms">
        <?php foreach ($rooms as $room): $roomId = (int) $room['id']; ?>
        <div class="record-card" data-record-id="<?= $roomId ?>" draggable="true">
            <div class="record-head">
                <span><span class="drag-handle">⠿</span> <span class="record-title"><?= e($room['room_name'] ?: $room['room_type'] ?: 'Raum') ?></span></span>
                <span>
                    <button type="button" class="btn btn-sm btn-secondary" data-duplicate-room="<?= e($base) ?>">Duplizieren</button>
                    <button type="button" class="btn btn-sm btn-danger" data-delete-record>Entfernen</button>
                </span>
            </div>
            <div class="grid grid-3">
                <div class="field"><label>Raumart</label>
                    <select name="room_type">
                        <option value=""></option>
                        <?php foreach (room_types() as $rt): ?>
                            <option <?= ($room['room_type'] ?? '') === $rt ? 'selected' : '' ?>><?= e($rt) ?></option>
                        <?php endforeach; ?>
                    </select></div>
                <div class="field"><label>Eigene Raumbezeichnung</label><input type="text" name="room_name" value="<?= e($room['room_name'] ?? '') ?>"></div>
                <div class="field"><label>Zustand</label>
                    <select name="condition_status">
                        <option value=""></option>
                        <?php foreach (room_conditions() as $key => $label): ?>
                            <option value="<?= e($key) ?>" <?= ($room['condition_status'] ?? '') === $key ? 'selected' : '' ?>><?= e($label) ?></option>
                        <?php endforeach; ?>
                    </select></div>
            </div>
            <div class="field"><label>Bemerkung zum Raum</label><input type="text" name="comment" value="<?= e($room['comment'] ?? '') ?>"></div>

            <label>Allgemeine Raumfotos</label>
            <?php $category = 'room_photo'; $refField = 'room_id'; $refValue = $roomId; $files_backup = $files; $files = $filesByRoom[$roomId] ?? []; include __DIR__ . '/_uploader.php'; $files = $files_backup; ?>

            <div class="defects-area" <?= ($room['condition_status'] ?? '') === 'defective' || !empty($defectsByRoom[$roomId]) ? '' : 'hidden' ?>>
                <h3>Mängel in diesem Raum</h3>
                <div data-record-container data-entity="defect" data-base="<?= e($base) ?>" data-template="tpl-defect" id="list-defects-<?= $roomId ?>">
                    <?php foreach ($defectsByRoom[$roomId] ?? [] as $d): ?>
                        <div class="record-card" data-record-id="<?= (int) $d['id'] ?>">
                            <div class="record-head">
                                <span class="record-title"><?= e($d['title'] ?: $d['category'] ?: 'Mangel') ?></span>
                                <button type="button" class="btn btn-sm btn-danger" data-delete-record>Entfernen</button>
                            </div>
                            <input type="hidden" name="room_id" value="<?= $roomId ?>">
                            <?php $defectFields($d); ?>
                            <label>Fotos / Dokumente zum Mangel</label>
                            <?php $category = 'defect_photo'; $refField = 'defect_id'; $refValue = (int) $d['id']; $files_backup = $files; $files = $filesByDefect[(int) $d['id']] ?? []; include __DIR__ . '/_uploader.php'; $files = $files_backup; ?>
                        </div>
                    <?php endforeach; ?>
                </div>
                <button type="button" class="btn btn-secondary btn-sm" data-add-record="#list-defects-<?= $roomId ?>" data-preset='{"room_id":"<?= $roomId ?>"}'>+ Mangel erfassen</button>
            </div>
        </div>
        <?php endforeach; ?>
    </div>

    <div class="btn-row">
        <?php foreach (['Flur', 'Wohnzimmer', 'Schlafzimmer', 'Küche', 'Badezimmer', 'Keller'] as $suggestion): ?>
            <button type="button" class="btn btn-secondary btn-sm" data-add-record="#list-rooms" data-preset='{"room_type":"<?= e($suggestion) ?>"}'>+ <?= e($suggestion) ?></button>
        <?php endforeach; ?>
        <button type="button" class="btn btn-secondary" data-add-record="#list-rooms">+ Raum hinzufügen</button>
        <button type="submit" form="wizard-form" name="_nav" value="next" class="btn">Weiter zur Schlüsselübergabe</button>
    </div>

    <template id="tpl-room">
        <div class="record-card" data-record-id="" draggable="true">
            <div class="record-head">
                <span><span class="drag-handle">⠿</span> <span class="record-title">Neuer Raum</span></span>
                <button type="button" class="btn btn-sm btn-danger" data-delete-record>Entfernen</button>
            </div>
            <div class="grid grid-3">
                <div class="field"><label>Raumart</label>
                    <select name="room_type">
                        <option value=""></option>
                        <?php foreach (room_types() as $rt): ?>
                            <option><?= e($rt) ?></option>
                        <?php endforeach; ?>
                    </select></div>
                <div class="field"><label>Eigene Raumbezeichnung</label><input type="text" name="room_name" value=""></div>
                <div class="field"><label>Zustand</label>
                    <select name="condition_status">
                        <option value=""></option>
                        <?php foreach (room_conditions() as $key => $label): ?>
                            <option value="<?= e($key) ?>"><?= e($label) ?></option>
                        <?php endforeach; ?>
                    </select></div>
            </div>
            <div class="field"><label>Bemerkung zum Raum</label><input type="text" name="comment" value=""></div>
            <p class="muted small">Nach dem Speichern des Raums können Fotos und Mängel erfasst werden (Seite wird beim Wechsel aktualisiert).</p>
        </div>
    </template>
    <template id="tpl-defect">
        <div class="record-card" data-record-id="">
            <div class="record-head">
                <span class="record-title">Neuer Mangel</span>
                <button type="button" class="btn btn-sm btn-danger" data-delete-record>Entfernen</button>
            </div>
            <input type="hidden" name="room_id" value="">
            <?php $defectFields(); ?>
            <p class="muted small">Fotos zum Mangel können nach dem ersten Speichern hochgeladen werden.</p>
        </div>
    </template>
</div>

<?php $nextLabel = 'Weiter zur Schlüsselübergabe'; require __DIR__ . '/_frame_bottom.php'; ?>
