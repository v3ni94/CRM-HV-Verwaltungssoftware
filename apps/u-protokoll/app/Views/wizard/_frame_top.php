<?php
/**
 * Gemeinsamer Wizard-Kopf: Fortschrittsanzeige und Formularbeginn.
 * Erwartet: $protocol, $step, $steps
 */
$base = url('/protocols/' . $protocol['id']);
?>
<div data-protocol-base="<?= e($base) ?>"></div>
<div class="section-head">
    <h1><?= e($protocol['protocol_number'] ?? '') ?> <span class="muted small"><?= e(protocol_types()[$protocol['protocol_type']] ?? '') ?><?= (int) $protocol['version'] > 1 ? ', Version ' . (int) $protocol['version'] : '' ?></span></h1>
    <div><?= status_badge($protocol['status']) ?></div>
</div>

<nav class="progress-steps" aria-label="Schritte (alle Angaben optional)">
    <?php foreach ($steps as $key => $label): ?>
        <a href="<?= e($base . '/wizard/' . $key) ?>" class="<?= $key === $step ? 'active' : '' ?>"><?= e($label) ?></a>
    <?php endforeach; ?>
</nav>
<div class="autosave-status" aria-live="polite"></div>

<?php if (!empty($_SESSION['completion_hints'])): ?>
    <div class="alert alert-warning">
        <strong>Das Protokoll wurde noch nicht abgeschlossen. Bitte prüfen Sie folgende Hinweise:</strong>
        <ul style="margin:0.4rem 0 0.6rem 1.1rem">
            <?php foreach ($_SESSION['completion_hints'] as $hint): ?><li><?= e($hint) ?></li><?php endforeach; ?>
        </ul>
        <div class="btn-row">
            <a class="btn btn-secondary" href="<?= e($base . '/wizard/summary') ?>">Zurück und ergänzen</a>
            <?php $hintHelper = \App\Core\Auth::isHelper(); ?>
            <form method="post" action="<?= e($base . '/complete') ?>" class="inline"
                  <?= $hintHelper ? '' : 'data-confirm="Es liegen Hinweise vor. Möchten Sie das Protokoll trotzdem verbindlich abschließen? Es wird danach gesperrt und als PDF erzeugt."' ?>>
                <?= \App\Core\Csrf::field() ?>
                <input type="hidden" name="force" value="1">
                <button type="submit" class="btn btn-success"><?= $hintHelper ? 'Trotz Hinweisen abschließen und festschreiben' : 'Trotz Hinweisen verbindlich abschließen' ?></button>
            </form>
        </div>
    </div>
    <?php unset($_SESSION['completion_hints']); ?>
<?php endif; ?>

<form method="post" action="<?= e($base . '/wizard/' . $step) ?>" data-autosave="<?= e($base . '/autosave') ?>" id="wizard-form">
<?= \App\Core\Csrf::field() ?>
