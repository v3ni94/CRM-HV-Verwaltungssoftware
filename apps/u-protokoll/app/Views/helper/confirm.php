<?php
/** @var array $protocol; @var array $hints; @var string $from */
$base = url('/protocols/' . $protocol['id']);
$steps = visible_wizard_steps();
$backStep = isset($steps[$from]) ? $from : 'signatures';
?>
<h1>Übergabe abschließen</h1>

<div class="card">
    <p style="margin-top:0">
        Protokoll <strong><?= e($protocol['protocol_number'] ?: (string) $protocol['id']) ?></strong>
        <?= protocol_address($protocol) !== '' ? ', Objekt ' . e(protocol_address($protocol)) : '' ?>
    </p>

    <?php if ($hints !== []): ?>
        <div class="alert alert-warning">
            <strong>Bitte beachten Sie folgende Hinweise (kein Abschlusshindernis):</strong>
            <ul style="margin:0.4rem 0 0 1.1rem">
                <?php foreach ($hints as $hint): ?><li><?= e($hint) ?></li><?php endforeach; ?>
            </ul>
        </div>
    <?php endif; ?>

    <div class="alert alert-info">
        <strong>Sind Sie sicher, dass Sie mit der Übergabe komplett fertig sind?</strong><br>
        Das Protokoll wird unwiderruflich geschlossen und festgeschrieben. Sie erhalten sofort eine Durchschrift per E-Mail
        und können das PDF anschließend hier herunterladen. Danach sind keine Änderungen mehr möglich.
    </div>

    <form method="post" action="<?= e($base . '/complete') ?>">
        <?= \App\Core\Csrf::field() ?>
        <input type="hidden" name="confirmed" value="1">
        <input type="hidden" name="from" value="<?= e($backStep) ?>">
        <?php if ($hints !== []): ?><input type="hidden" name="force" value="1"><?php endif; ?>
        <div class="btn-row">
            <button type="submit" class="btn btn-success"><?= $hints !== [] ? 'Ja, trotz Hinweisen abschließen und festschreiben' : 'Ja, Übergabe abschließen und festschreiben' ?></button>
            <a class="btn btn-secondary" href="<?= e($base . '/wizard/' . $backStep) ?>">Nein, zurück zur Bearbeitung</a>
        </div>
    </form>
</div>
