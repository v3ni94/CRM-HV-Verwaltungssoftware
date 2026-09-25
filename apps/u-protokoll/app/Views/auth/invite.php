<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Zugang einrichten | U-Protokoll</title>
<link rel="stylesheet" href="<?= e(url('/assets/css/app.css')) ?>">
<link rel="icon" href="<?= e(url('/favicon.ico')) ?>" sizes="any">
<link rel="apple-touch-icon" href="<?= e(url('/assets/img/apple-touch-icon.png')) ?>">
</head>
<body>
<div class="hvm-kennlinie"></div>
<div class="login-wrap">
    <div class="login-card">
        <img class="login-logo" src="<?= e(url('/assets/img/logo-hvm.jpg')) ?>" alt="Hausverwaltung Müller GmbH">
        <h1 style="text-align:center">Zugang einrichten</h1>

        <?php if ($invitation === null): ?>
            <div class="alert alert-error">
                Diese Einladung ist ungültig, abgelaufen oder wurde bereits verwendet.
                Bitte wenden Sie sich an Ihre Administration, um eine neue Einladung zu erhalten.
            </div>
            <p style="text-align:center"><a href="<?= e(url('/login')) ?>">Zur Anmeldung</a></p>
        <?php else: ?>
            <p class="muted small" style="text-align:center">
                Einladung für <strong><?= e($invitation['email']) ?></strong><br>
                Rolle: <?= e(user_role_label($invitation['role'])) ?>
            </p>
            <?php if (!empty($error)): ?>
                <div class="alert alert-error"><?= e($error) ?></div>
            <?php endif; ?>
            <form method="post" action="<?= e(url('/invite/' . $token)) ?>">
                <?= \App\Core\Csrf::field() ?>
                <div class="field">
                    <label for="first_name">Vorname</label>
                    <input type="text" id="first_name" name="first_name" value="<?= e($_POST['first_name'] ?? $invitation['first_name'] ?? '') ?>">
                </div>
                <div class="field">
                    <label for="last_name">Nachname</label>
                    <input type="text" id="last_name" name="last_name" value="<?= e($_POST['last_name'] ?? $invitation['last_name'] ?? '') ?>">
                </div>
                <div class="field">
                    <label for="username">Benutzername</label>
                    <input type="text" id="username" name="username" autocomplete="username" required value="<?= e($_POST['username'] ?? '') ?>">
                </div>
                <div class="field">
                    <label for="password">Passwort (mindestens 10 Zeichen)</label>
                    <input type="password" id="password" name="password" autocomplete="new-password" minlength="10" required>
                </div>
                <div class="field">
                    <label for="password_repeat">Passwort wiederholen</label>
                    <input type="password" id="password_repeat" name="password_repeat" autocomplete="new-password" minlength="10" required>
                </div>
                <button type="submit" class="btn btn-block">Zugang einrichten</button>
            </form>
        <?php endif; ?>

        <p class="muted small" style="margin-top:1.5rem;text-align:center">Hausverwaltung Müller GmbH<br>Eine Marke der Müller Holding Aktiengesellschaft</p>
    </div>
</div>
</body>
</html>
