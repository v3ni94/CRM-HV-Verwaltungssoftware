<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Anmeldung | U-Protokoll</title>
<link rel="stylesheet" href="<?= e(url('/assets/css/app.css')) ?>">
<link rel="icon" href="<?= e(url('/favicon.ico')) ?>" sizes="any">
<link rel="apple-touch-icon" href="<?= e(url('/assets/img/apple-touch-icon.png')) ?>">
</head>
<body>
<div class="hvm-kennlinie"></div>
<div class="login-wrap">
    <div class="login-card">
        <img class="login-logo" src="<?= e(url('/assets/img/logo-hvm.jpg')) ?>" alt="Hausverwaltung Müller GmbH">
        <h1 style="text-align:center">U-Protokoll</h1>
        <p class="muted small" style="text-align:center">Digitales Übergabe- und Abnahmeprotokoll</p>
        <?php if (!empty($_SESSION['flash_success'])): ?>
            <div class="alert alert-success"><?= e($_SESSION['flash_success']) ?></div>
            <?php unset($_SESSION['flash_success']); ?>
        <?php endif; ?>
        <?php if (!empty($error)): ?>
            <div class="alert alert-error"><?= e($error) ?></div>
        <?php endif; ?>
        <form method="post" action="<?= e(url('/login')) ?>">
            <?= \App\Core\Csrf::field() ?>
            <div class="field">
                <label for="username">Benutzername oder E-Mail</label>
                <input type="text" id="username" name="username" autocomplete="username" autofocus required>
            </div>
            <div class="field">
                <label for="password">Passwort</label>
                <input type="password" id="password" name="password" autocomplete="current-password" required>
            </div>
            <button type="submit" class="btn btn-block">Anmelden</button>
        </form>
        <p class="muted small" style="margin-top:1.5rem;text-align:center">Hausverwaltung Müller GmbH<br>Eine Marke der Müller Holding Aktiengesellschaft</p>
    </div>
</div>
</body>
</html>
