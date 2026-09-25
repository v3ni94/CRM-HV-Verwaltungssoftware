<?php
/**
 * Upload-Baustein. Erwartet:
 * $protocol, $category; optional $refField, $refValue, $files (vorhandene Dateien),
 * $internal (bool), $uploadLabel (eigene Beschriftung).
 * Bewusst eigene Variable $uploadLabel (nicht $label), da $label in den
 * Views als Schleifenvariable verwendet wird und sonst durchsickert.
 */
$base = url('/protocols/' . $protocol['id']);
$needsRecord = isset($refField) && empty($refValue);
$isPhotoContext = $category !== 'attachment';
$buttonText = $uploadLabel ?? ($isPhotoContext ? '📷 Foto aufnehmen / Datei wählen' : '📎 Datei auswählen (Foto oder PDF)');
?>
<div>
    <div class="upload-zone"
         data-upload-url="<?= e($base . '/files/upload') ?>"
         data-category="<?= e($category) ?>"
         <?= isset($refField) ? 'data-ref-field="' . e($refField) . '"' : '' ?>
         <?= isset($refValue) && $refValue ? 'data-ref-value="' . e((string) $refValue) . '"' : '' ?>
         <?= $needsRecord ? 'data-needs-record="1"' : '' ?>
         <?= !empty($internal) ? 'data-internal="1"' : '' ?>>
        <label class="btn btn-secondary btn-sm" style="cursor:pointer">
            <?= e($buttonText) ?>
            <input type="file" accept="image/*,.pdf,.heic" <?= $isPhotoContext ? 'capture="environment"' : '' ?> multiple hidden>
        </label>
        <div class="small muted">Mehrfachauswahl möglich, auf dem Desktop auch per Drag &amp; Drop.</div>
        <div class="upload-status"></div>
    </div>
    <div class="thumb-list">
        <?php foreach (($files ?? []) as $f): ?>
            <div class="thumb-item" data-file-id="<?= (int) $f['id'] ?>">
                <?php if (str_starts_with((string) $f['mime_type'], 'image/')): ?>
                    <a href="<?= e(url('/files/' . $f['id'])) ?>" target="_blank" rel="noopener"><img src="<?= e(url('/files/' . $f['id'] . '/thumb')) ?>" alt="<?= e($f['description'] ?? '') ?>"></a>
                <?php else: ?>
                    <a class="thumb-doc" href="<?= e(url('/files/' . $f['id'])) ?>" target="_blank" rel="noopener"><?= e($f['original_filename']) ?></a>
                <?php endif; ?>
                <button type="button" class="thumb-del" title="Löschen">×</button>
            </div>
        <?php endforeach; ?>
    </div>
</div>
<?php unset($uploadLabel); ?>
