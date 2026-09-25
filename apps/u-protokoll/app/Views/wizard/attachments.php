<?php
$base = url('/protocols/' . $protocol['id']);
$attachmentFiles = array_values(array_filter($files, fn($f) => $f['file_category'] === 'attachment'));
require __DIR__ . '/_frame_top.php';
?>

<div class="card">
    <h2>Anhänge am Gesamtprotokoll</h2>
    <p class="muted small">Fotos, PDF-Dokumente und sonstige Dateien, die dem Protokoll beigefügt werden.</p>
    <div class="grid grid-3">
        <div class="field"><label>Kategorie</label>
            <select data-attachment-type-select>
                <?php foreach (attachment_categories() as $key => $label): ?>
                    <option value="<?= e($key) ?>"><?= e($label) ?></option>
                <?php endforeach; ?>
            </select></div>
        <div class="field" style="grid-column:span 2"><label>Beschreibung (für die nächste hochgeladene Datei)</label>
            <input type="text" data-file-description placeholder="optional"></div>
    </div>
    <?php $category = 'attachment'; unset($refField, $refValue); $files_backup = $files; $files = []; include __DIR__ . '/_uploader.php'; $files = $files_backup; ?>

    <?php if (!\App\Core\Auth::isHelper()): ?>
    <h3>Interne Anhänge <span class="muted small">(nicht Bestandteil des Kunden-PDFs)</span></h3>
    <?php $category = 'attachment'; $internal = true; $files = []; include __DIR__ . '/_uploader.php'; $files = $files_backup; $internal = false; ?>
    <?php endif; ?>

    <?php if ($attachmentFiles !== []): ?>
    <h3>Vorhandene Anhänge</h3>
    <div class="table-wrap"><table class="list">
        <thead><tr><th>Datei</th><th>Kategorie</th><th>Beschreibung</th><th>Größe</th><th>Sichtbarkeit</th><th></th></tr></thead>
        <tbody>
        <?php foreach ($attachmentFiles as $f): ?>
            <tr>
                <td><a href="<?= e(url('/files/' . $f['id'])) ?>" target="_blank" rel="noopener"><?= e($f['original_filename']) ?></a></td>
                <td><?= e(attachment_categories()[$f['attachment_type']] ?? ($f['attachment_type'] ?? '')) ?></td>
                <td><?= e($f['description']) ?></td>
                <td><?= e(number_format((int) $f['file_size'] / 1024, 0, ',', '.')) ?> KB</td>
                <td><?= $f['is_internal'] ? '<span class="badge badge-draft">intern</span>' : 'Bestandteil des Protokolls' ?></td>
                <td>
                    <div class="thumb-item" data-file-id="<?= (int) $f['id'] ?>" style="width:auto">
                        <button type="button" class="thumb-del" style="position:static" title="Löschen">×</button>
                    </div>
                </td>
            </tr>
        <?php endforeach; ?>
        </tbody>
    </table></div>
    <?php endif; ?>
</div>

<?php require __DIR__ . '/_frame_bottom.php'; ?>
