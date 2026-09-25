<?php /** @var ?string $error */ ?>
<h1>Passwort ändern</h1>

<div class="card" style="max-width:560px">
    <p class="muted small" style="margin-top:0">
        Das neue Passwort muss mindestens 10 Zeichen lang sein. Nach der Änderung gilt sofort nur noch das neue Passwort.
    </p>
    <?php if (!empty($error)): ?>
        <div class="alert alert-error"><?= e($error) ?></div>
    <?php endif; ?>
    <form method="post" action="<?= e(url('/passwort')) ?>">
        <?= \App\Core\Csrf::field() ?>
        <div class="field"><label for="current_password">Aktuelles Passwort</label>
            <input type="password" id="current_password" name="current_password" required autocomplete="current-password"></div>
        <div class="field"><label for="new_password">Neues Passwort</label>
            <input type="password" id="new_password" name="new_password" required minlength="10" autocomplete="new-password"></div>
        <div class="field"><label for="new_password_repeat">Neues Passwort wiederholen</label>
            <input type="password" id="new_password_repeat" name="new_password_repeat" required minlength="10" autocomplete="new-password"></div>
        <div class="btn-row">
            <button type="submit" class="btn">Passwort speichern</button>
            <a class="btn btn-secondary" href="<?= e(url('/')) ?>">Abbrechen</a>
        </div>
    </form>
</div>
