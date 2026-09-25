<?php $p = $protocol; require __DIR__ . '/_frame_top.php';
$roHelper = \App\Core\Auth::isHelper() ? ' readonly title="Von der Hausverwaltung vorbereitet"' : ''; ?>

<div class="card">
    <h2>Objektdaten <span class="muted small">(alle Angaben optional)</span></h2>
    <div class="grid grid-3">
        <div class="field" style="grid-column:span 2"><label>Straße</label><input type="text" name="street" value="<?= e($p['street']) ?>"></div>
        <div class="grid grid-2-mobile grid-2">
            <div class="field"><label>Hausnummer</label><input type="text" name="house_number" value="<?= e($p['house_number']) ?>"></div>
            <div class="field"><label>Zusatz</label><input type="text" name="house_suffix" value="<?= e($p['house_suffix']) ?>"></div>
        </div>
        <div class="field"><label>PLZ</label><input type="text" name="postal_code" inputmode="numeric" value="<?= e($p['postal_code']) ?>"></div>
        <div class="field" style="grid-column:span 2"><label>Ort</label><input type="text" name="city" value="<?= e($p['city']) ?>"></div>
        <div class="field"><label>Objektbezeichnung</label><input type="text" name="object_label" value="<?= e($p['object_label']) ?>"></div>
        <div class="field"><label>Gebäude</label><input type="text" name="building" value="<?= e($p['building']) ?>"></div>
        <div class="field"><label>Etage</label><input type="text" name="floor" value="<?= e($p['floor']) ?>"></div>
        <div class="field"><label>Wohnungsnummer / Einheit</label><input type="text" name="unit_number" value="<?= e($p['unit_number']) ?>"></div>
        <div class="field"><label>Bezeichnung der Einheit</label><input type="text" name="unit_label" value="<?= e($p['unit_label']) ?>"></div>
        <div class="field"><label>Lage der Einheit</label><input type="text" name="unit_position" value="<?= e($p['unit_position']) ?>" placeholder="z. B. 2. OG rechts"></div>
    </div>

    <h3>Referenzen</h3>
    <div class="grid grid-3">
        <div class="field"><label>Interne Objektnummer</label><input type="text" name="internal_object_number"<?= $roHelper ?> value="<?= e($p['internal_object_number']) ?>"></div>
        <div class="field"><label>Mietvertragsnummer</label><input type="text" name="rental_contract_number"<?= $roHelper ?> value="<?= e($p['rental_contract_number']) ?>"></div>
        <div class="field"><label>Verwaltungsnummer</label><input type="text" name="management_number"<?= $roHelper ?> value="<?= e($p['management_number']) ?>"></div>
        <div class="field"><label>Sonstige Referenznummer</label><input type="text" name="reference_number" value="<?= e($p['reference_number']) ?>"></div>
        <div class="field"><label>Ticketnummer / Systemticket</label><input type="text" name="ticket_number" value="<?= e($p['ticket_number']) ?>"></div>
    </div>

    <h3>Übergabetermin</h3>
    <div class="grid grid-4">
        <div class="field"><label>Übergabedatum</label><input type="date" name="handover_date" value="<?= e($p['handover_date']) ?>"></div>
        <div class="field"><label>Beginn der Übergabe</label><input type="time" name="handover_start" value="<?= e($p['handover_start']) ?>"></div>
        <div class="field"><label>Ende der Übergabe</label><input type="time" name="handover_end" value="<?= e($p['handover_end']) ?>"></div>
        <div class="field"><label>Übergabeort</label><input type="text" name="handover_location" value="<?= e($p['handover_location']) ?>"></div>
    </div>
    <input type="hidden" name="hide_time_information_present" value="1">
    <div class="checkbox-row">
        <input type="checkbox" id="hide_time" name="hide_time_information" value="1" <?= $p['hide_time_information'] ? 'checked' : '' ?>>
        <label for="hide_time">Zeitinformationen nicht im fertigen Protokoll anzeigen (interne Speicherung bleibt erhalten)</label>
    </div>
</div>

<?php require __DIR__ . '/_frame_bottom.php'; ?>
