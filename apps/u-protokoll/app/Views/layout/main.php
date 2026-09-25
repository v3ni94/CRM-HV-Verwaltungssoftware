<?php /** @var string $content */ ?>
<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title><?= e($title ?? 'U-Protokoll') ?> | U-Protokoll</title>
<link rel="stylesheet" href="<?= e(url('/assets/css/app.css')) ?>">
<link rel="icon" href="<?= e(url('/favicon.ico')) ?>" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="<?= e(url('/assets/img/favicon-32.png')) ?>">
<link rel="apple-touch-icon" href="<?= e(url('/assets/img/apple-touch-icon.png')) ?>">
<meta name="theme-color" content="#1A1A1A">
<meta name="csrf-token" content="<?= e(\App\Core\Csrf::token()) ?>">
</head>
<body>
<div class="topbar-wrap">
<div class="hvm-kennlinie"></div>
<header class="topbar">
    <a class="brand" href="<?= e(url('/')) ?>">
        <img class="brand-logo" src="<?= e(url('/assets/img/logo-hvm.jpg')) ?>" alt="Hausverwaltung Müller GmbH">
        <span class="brand-text">U-Protokoll <small>Hausverwaltung Müller GmbH</small></span>
    </a>
    <nav class="topnav">
        <?php if (\App\Core\Auth::isHelper()): ?>
            <a href="<?= e(url('/meine-uebergabe')) ?>">Meine Übergabe</a>
        <?php else: ?>
            <a href="<?= e(url('/')) ?>">Übersicht</a>
        <?php endif; ?>
        <?php if (\App\Core\Auth::isAdmin()): ?>
            <a href="<?= e(url('/admin')) ?>">Administration</a>
        <?php endif; ?>
        <a href="<?= e(url('/passwort')) ?>">Passwort</a>
        <form method="post" action="<?= e(url('/logout')) ?>" class="inline">
            <?= \App\Core\Csrf::field() ?>
            <button type="submit" class="btn btn-ghost btn-sm">Abmelden (<?= e(\App\Core\Auth::user()['username'] ?? '') ?>)</button>
        </form>
    </nav>
</header>
</div>

<main class="container <?= !empty($isWizard) ? 'has-sticky-nav' : '' ?>">
<?php if (!empty($_SESSION['flash_success'])): ?>
    <div class="alert alert-success"><?= e($_SESSION['flash_success']) ?></div>
    <?php unset($_SESSION['flash_success']); ?>
<?php endif; ?>
<?php if (!empty($_SESSION['flash_error'])): ?>
    <div class="alert alert-error"><?= e($_SESSION['flash_error']) ?></div>
    <?php unset($_SESSION['flash_error']); ?>
<?php endif; ?>
<?= $content ?>
</main>

<footer class="footer">
    Hausverwaltung Müller GmbH | Eine Marke der Müller Holding Aktiengesellschaft<br>
    <span class="small">Rheinpromenade 13, 40789 Monheim am Rhein | Amtsgericht Düsseldorf, HRB 104762 | www.muellerhv.de</span><br>
    <?php $privacyUrl = trim((string) \App\Core\Config::setting('legal.privacy_url', '')); $imprintUrl = trim((string) \App\Core\Config::setting('legal.imprint_url', '')); ?>
    <?php if ($privacyUrl !== '' || $imprintUrl !== ''): ?>
        <span class="small">
            <?php if ($imprintUrl !== ''): ?><a href="<?= e($imprintUrl) ?>" target="_blank" rel="noopener">Impressum</a><?php endif; ?>
            <?php if ($imprintUrl !== '' && $privacyUrl !== ''): ?> | <?php endif; ?>
            <?php if ($privacyUrl !== ''): ?><a href="<?= e($privacyUrl) ?>" target="_blank" rel="noopener">Datenschutz</a><?php endif; ?>
        </span><br>
    <?php endif; ?>
    <span class="small" style="opacity:0.75"><?= e(special_day_note()) ?></span>
</footer>
<script src="<?= e(url('/assets/js/app.js')) ?>"></script>
<?php if (!empty($isWizard)): ?>
<script src="<?= e(url('/assets/js/signature.js')) ?>"></script>
<?php endif; ?>
</body>
</html>
