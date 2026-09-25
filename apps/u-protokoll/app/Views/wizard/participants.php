<?php
/** Beteiligte Personen: Hauptrollen je Typ plus weitere Beteiligte. */
[$outRole, $inRole, $outLabel, $inLabel] = party_roles($protocol['protocol_type']);
$base = url('/protocols/' . $protocol['id']);
$byRole = ['out' => [], 'in' => [], 'extra' => []];
foreach ($participants as $pt) {
    if ($pt['role'] === $outRole) { $byRole['out'][] = $pt; }
    elseif ($pt['role'] === $inRole) { $byRole['in'][] = $pt; }
    else { $byRole['extra'][] = $pt; }
}
require __DIR__ . '/_frame_top.php';

$renderPersonFields = function (array $pt = []) {
    ?>
    <div class="grid grid-3">
        <div class="field"><label>Anrede</label>
            <select name="salutation">
                <option value=""></option>
                <?php foreach (['Herr', 'Frau', 'Divers', 'Firma', 'Eheleute'] as $s): ?>
                    <option <?= ($pt['salutation'] ?? '') === $s ? 'selected' : '' ?>><?= e($s) ?></option>
                <?php endforeach; ?>
            </select></div>
        <div class="field"><label>Vorname</label><input type="text" name="first_name" value="<?= e($pt['first_name'] ?? '') ?>"></div>
        <div class="field"><label>Nachname</label><input type="text" name="last_name" value="<?= e($pt['last_name'] ?? '') ?>"></div>
        <div class="field"><label>Firma</label><input type="text" name="company" value="<?= e($pt['company'] ?? '') ?>"></div>
        <div class="field"><label>Straße</label><input type="text" name="street" value="<?= e($pt['street'] ?? '') ?>"></div>
        <div class="field"><label>Hausnummer</label><input type="text" name="house_number" value="<?= e($pt['house_number'] ?? '') ?>"></div>
        <div class="field"><label>PLZ</label><input type="text" name="postal_code" value="<?= e($pt['postal_code'] ?? '') ?>"></div>
        <div class="field"><label>Ort</label><input type="text" name="city" value="<?= e($pt['city'] ?? '') ?>"></div>
        <div class="field"><label>Telefon</label><input type="tel" name="phone" value="<?= e($pt['phone'] ?? '') ?>"></div>
        <div class="field"><label>Mobil</label><input type="tel" name="mobile" value="<?= e($pt['mobile'] ?? '') ?>"></div>
        <div class="field"><label>E-Mail</label><input type="email" name="email" value="<?= e($pt['email'] ?? '') ?>"></div>
    </div>
    <?php
};
?>

<?php foreach ([['out', $outRole, $outLabel], ['in', $inRole, $inLabel]] as [$slot, $role, $label]): ?>
<div class="card">
    <h2><?= e($label) ?></h2>
    <div data-record-container data-entity="participant" data-base="<?= e($base) ?>" data-template="tpl-participant-<?= e($slot) ?>" id="list-<?= e($slot) ?>">
        <?php foreach ($byRole[$slot] as $pt): ?>
            <div class="record-card" data-record-id="<?= (int) $pt['id'] ?>">
                <div class="record-head">
                    <span class="record-title"><?= e(trim(($pt['first_name'] ?? '') . ' ' . ($pt['last_name'] ?? '')) ?: $label) ?></span>
                    <button type="button" class="btn btn-sm btn-danger" data-delete-record>Entfernen</button>
                </div>
                <input type="hidden" name="role" value="<?= e($role) ?>">
                <?php $renderPersonFields($pt); ?>
            </div>
        <?php endforeach; ?>
    </div>
    <button type="button" class="btn btn-secondary" data-add-record="#list-<?= e($slot) ?>">+ Weitere Person (<?= e($label) ?>) hinzufügen</button>
    <template id="tpl-participant-<?= e($slot) ?>">
        <div class="record-card" data-record-id="">
            <div class="record-head">
                <span class="record-title"><?= e($label) ?></span>
                <button type="button" class="btn btn-sm btn-danger" data-delete-record>Entfernen</button>
            </div>
            <input type="hidden" name="role" value="<?= e($role) ?>">
            <?php $renderPersonFields(); ?>
        </div>
    </template>
</div>
<?php endforeach; ?>

<div class="card">
    <h2>Weitere Beteiligte</h2>
    <p class="muted small">Verwaltung, Makler, Hausmeister, Bevollmächtigte, Zeugen, Sachverständige und weitere Personen.</p>
    <div data-record-container data-entity="participant" data-base="<?= e($base) ?>" data-template="tpl-participant-extra" id="list-extra">
        <?php foreach ($byRole['extra'] as $pt): ?>
            <div class="record-card" data-record-id="<?= (int) $pt['id'] ?>">
                <div class="record-head">
                    <span class="record-title"><?= e(participant_role_label($pt['role'], $protocol['protocol_type'])) ?></span>
                    <button type="button" class="btn btn-sm btn-danger" data-delete-record>Entfernen</button>
                </div>
                <div class="field"><label>Rolle</label>
                    <select name="role">
                        <?php foreach (extra_roles() as $key => $rl): ?>
                            <option value="<?= e($key) ?>" <?= $pt['role'] === $key ? 'selected' : '' ?>><?= e($rl) ?></option>
                        <?php endforeach; ?>
                    </select></div>
                <?php $renderPersonFields($pt); ?>
                <div class="field"><label>Bemerkung</label><input type="text" name="comment" value="<?= e($pt['comment'] ?? '') ?>"></div>
            </div>
        <?php endforeach; ?>
    </div>
    <button type="button" class="btn btn-secondary" data-add-record="#list-extra">+ Weiteren Beteiligten hinzufügen</button>
    <template id="tpl-participant-extra">
        <div class="record-card" data-record-id="">
            <div class="record-head">
                <span class="record-title">Weiterer Beteiligter</span>
                <button type="button" class="btn btn-sm btn-danger" data-delete-record>Entfernen</button>
            </div>
            <div class="field"><label>Rolle</label>
                <select name="role">
                    <?php foreach (extra_roles() as $key => $rl): ?>
                        <option value="<?= e($key) ?>"><?= e($rl) ?></option>
                    <?php endforeach; ?>
                </select></div>
            <?php $renderPersonFields(); ?>
            <div class="field"><label>Bemerkung</label><input type="text" name="comment" value=""></div>
        </div>
    </template>
</div>

<?php require __DIR__ . '/_frame_bottom.php'; ?>
