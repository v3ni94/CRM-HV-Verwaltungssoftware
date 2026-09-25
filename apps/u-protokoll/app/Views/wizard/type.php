<?php require __DIR__ . '/_frame_top.php'; ?>

<div class="card">
    <h2>Art der Übergabe</h2>
    <p class="muted small">Die Beschriftungen der folgenden Schritte richten sich nach dieser Auswahl.</p>
    <?php foreach (protocol_types() as $key => $label): ?>
        <div class="checkbox-row">
            <input type="radio" id="type_<?= e($key) ?>" name="protocol_type" value="<?= e($key) ?>" <?= $protocol['protocol_type'] === $key ? 'checked' : '' ?>>
            <label for="type_<?= e($key) ?>"><?= e($label) ?></label>
        </div>
    <?php endforeach; ?>
    <?php [$o, $i, $outLabel, $inLabel] = party_roles($protocol['protocol_type']); ?>
    <p class="muted small">Aktuelle Rollenbezeichnungen: <?= e($outLabel) ?> / <?= e($inLabel) ?></p>
</div>

<?php require __DIR__ . '/_frame_bottom.php'; ?>
