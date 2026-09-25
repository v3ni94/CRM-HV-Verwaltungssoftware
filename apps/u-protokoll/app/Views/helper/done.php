<?php
/** @var array $protocol; @var bool $finalized; @var ?array $dispatch; @var array $emails */
$base = url('/protocols/' . $protocol['id']);
$contact = company_contact_line();
?>
<?php if (!$finalized): ?>
    <h1>Protokoll geschlossen</h1>
    <div class="card">
        <div class="alert alert-warning">
            <?php if ($protocol['status'] === 'cancelled'): ?>
                Dieses Protokoll wurde von der Hausverwaltung storniert. Es ist nicht wirksam abgeschlossen.
            <?php else: ?>
                Dieses Protokoll wurde von der Hausverwaltung geschlossen und kann nicht mehr bearbeitet werden.
            <?php endif; ?>
        </div>
        <p class="muted small" style="margin:0">
            Bei Fragen wenden Sie sich an die Hausverwaltung Müller GmbH<?= $contact !== '' ? ' (' . e($contact) . ')' : '' ?>.
        </p>
    </div>
<?php else: ?>
    <h1>Übergabe abgeschlossen</h1>

    <div class="card">
        <div class="alert alert-success">
            Das Protokoll <strong><?= e($protocol['protocol_number'] ?: (string) $protocol['id']) ?></strong> ist abgeschlossen
            und festgeschrieben. Änderungen sind nicht mehr möglich.
        </div>
        <dl class="kv">
            <dt>Objekt</dt><dd><?= e(protocol_address($protocol)) ?: '<span class="muted">Keine Angabe</span>' ?></dd>
            <dt>Übergabedatum</dt><dd><?= e(fmt_date($protocol['handover_date'])) ?: '<span class="muted">Keine Angabe</span>' ?></dd>
            <dt>Abgeschlossen am</dt><dd><?= e(fmt_datetime($protocol['completed_at'])) ?></dd>
        </dl>
        <div class="btn-row">
            <a class="btn" href="<?= e($base . '/pdf') ?>" target="_blank" rel="noopener">PDF anzeigen</a>
            <a class="btn btn-secondary" href="<?= e($base . '/pdf/download') ?>">PDF herunterladen</a>
        </div>
    </div>

    <?php if ($dispatch !== null): ?>
        <div class="card">
            <h2>Automatischer Versand</h2>
            <?php if (!empty($dispatch['error'])): ?>
                <div class="alert alert-error">
                    Der automatische Versand konnte aus technischen Gründen nicht durchgeführt werden. Der Fehlversuch ist in der
                    Versandhistorie vermerkt. Bitte laden Sie das PDF oben herunter; die Hausverwaltung holt den Versand nach.
                </div>
            <?php else: ?>
                <?php if (!empty($dispatch['sent'])): ?>
                    <p>Das Protokoll wurde als PDF an folgende Empfänger versendet:</p>
                    <ul><?php foreach ($dispatch['sent'] as $mail): ?><li><?= e($mail) ?></li><?php endforeach; ?></ul>
                <?php endif; ?>
                <?php if (!empty($dispatch['failed'])): ?>
                    <div class="alert alert-warning">
                        An folgende Adressen konnte die Durchschrift nicht zugestellt werden. Der Fehlversuch ist in der Versandhistorie
                        des Protokolls vermerkt. Bitte laden Sie das PDF oben herunter und wenden Sie sich an die Hausverwaltung,
                        falls Sie keine Durchschrift per E-Mail erhalten:
                        <ul style="margin:0.4rem 0 0 1.1rem"><?php foreach ($dispatch['failed'] as $mail): ?><li><?= e($mail) ?></li><?php endforeach; ?></ul>
                    </div>
                <?php endif; ?>
                <?php if (!empty($dispatch['skipped'])): ?>
                    <p class="muted small">Folgende Adressen sind formal ungültig und wurden übersprungen: <?= e(implode(', ', $dispatch['skipped'])) ?></p>
                <?php endif; ?>
                <?php if (empty($dispatch['sent']) && empty($dispatch['failed'])): ?>
                    <p class="muted">Es war keine gültige E-Mail-Adresse eines Beteiligten hinterlegt, daher konnte keine Durchschrift
                        versendet werden. Sie können das PDF oben herunterladen.</p>
                <?php endif; ?>
            <?php endif; ?>
        </div>
    <?php elseif ($emails !== []): ?>
        <div class="card">
            <h2>Versand</h2>
            <div class="table-wrap"><table class="list">
                <thead><tr><th>Empfänger</th><th>Status</th><th>Zeitpunkt</th></tr></thead>
                <tbody>
                <?php foreach ($emails as $mail): ?>
                    <tr>
                        <td><?= e($mail['recipients']) ?></td>
                        <td><?= $mail['status'] === 'sent' ? 'Versendet' : 'Fehlgeschlagen' ?></td>
                        <td><?= e(fmt_datetime($mail['sent_at'])) ?></td>
                    </tr>
                <?php endforeach; ?>
                </tbody>
            </table></div>
        </div>
    <?php endif; ?>

    <div class="card">
        <p class="muted small" style="margin:0">
            Bei Rückfragen zur Übergabe wenden Sie sich an die Hausverwaltung Müller GmbH<?= $contact !== '' ? ' (' . e($contact) . ')' : '' ?>.
        </p>
    </div>
<?php endif; ?>
