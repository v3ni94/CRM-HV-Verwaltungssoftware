<?php /** @var string $heading, $message, $backUrl */ ?>
<h1><?= e($heading) ?></h1>
<div class="card">
    <div class="alert alert-error"><?= e($message) ?></div>
    <p class="muted small">
        Wenn Sie der Ansicht sind, dass Sie Zugriff haben sollten, wenden Sie sich an die Hausverwaltung Müller GmbH<?= company_contact_line() !== '' ? ' (' . e(company_contact_line()) . ')' : '' ?>.
    </p>
    <div class="btn-row">
        <a class="btn" href="<?= e($backUrl) ?>">Zur Startseite</a>
    </div>
</div>
