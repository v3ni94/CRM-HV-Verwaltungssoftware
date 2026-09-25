<?php /** @var array $users, $branches, $invitations, $helpers; @var ?array $editUser */ ?>
<h1>Benutzerverwaltung</h1>
<p><a href="<?= e(url('/admin')) ?>">Zurück zu den Einstellungen</a></p>

<div class="card">
    <h2>Mitarbeiter einladen</h2>
    <p class="muted small">Die eingeladene Person erhält eine E-Mail mit einem Link (7 Tage gültig) und wählt Benutzername und Passwort selbst.</p>
    <form method="post" action="<?= e(url('/admin/users/invite')) ?>">
        <?= \App\Core\Csrf::field() ?>
        <div class="grid grid-3">
            <div class="field"><label>E-Mail-Adresse</label><input type="email" name="email" required></div>
            <div class="field"><label>Vorname</label><input type="text" name="first_name"></div>
            <div class="field"><label>Nachname</label><input type="text" name="last_name"></div>
            <div class="field"><label>Rolle</label>
                <select name="role">
                    <?php foreach (user_roles() as $key => $label): if ($key === 'helper') { continue; } ?>
                        <option value="<?= e($key) ?>" <?= $key === 'employee' ? 'selected' : '' ?>><?= e($label) ?></option>
                    <?php endforeach; ?>
                </select></div>
            <div class="field"><label>Niederlassung</label>
                <select name="branch_id"><option value=""></option>
                    <?php foreach ($branches as $b): ?><option value="<?= (int) $b['id'] ?>"><?= e($b['name']) ?></option><?php endforeach; ?>
                </select></div>
        </div>
        <button type="submit" class="btn">Einladung senden</button>
    </form>

    <?php if ($invitations !== []): ?>
        <h3>Offene Einladungen</h3>
        <div class="table-wrap"><table class="list">
            <thead><tr><th>E-Mail</th><th>Name</th><th>Rolle</th><th>Niederlassung</th><th>Gültig bis</th><th></th></tr></thead>
            <tbody>
            <?php foreach ($invitations as $inv): ?>
                <tr>
                    <td><?= e($inv['email']) ?></td>
                    <td><?= e(trim(($inv['first_name'] ?? '') . ' ' . ($inv['last_name'] ?? ''))) ?></td>
                    <td><?= e(user_role_label($inv['role'])) ?></td>
                    <td><?= e($inv['branch']) ?></td>
                    <td><?= e(fmt_datetime($inv['expires_at'])) ?><?= strtotime($inv['expires_at']) < time() ? ' <span class="badge badge-cancelled">abgelaufen</span>' : '' ?></td>
                    <td style="white-space:nowrap">
                        <form method="post" action="<?= e(url('/admin/users/invitations/resend')) ?>" class="inline">
                            <?= \App\Core\Csrf::field() ?>
                            <input type="hidden" name="invitation_id" value="<?= (int) $inv['id'] ?>">
                            <button type="submit" class="btn btn-sm btn-secondary">Erneut senden</button>
                        </form>
                        <form method="post" action="<?= e(url('/admin/users/invitations/delete')) ?>" class="inline" data-confirm="Einladung wirklich zurückziehen?">
                            <?= \App\Core\Csrf::field() ?>
                            <input type="hidden" name="invitation_id" value="<?= (int) $inv['id'] ?>">
                            <button type="submit" class="btn btn-sm btn-danger">Zurückziehen</button>
                        </form>
                    </td>
                </tr>
            <?php endforeach; ?>
            </tbody>
        </table></div>
        <p class="muted small">Erneut einladen: einfach dieselbe E-Mail-Adresse noch einmal einladen, die alte Einladung wird dabei ersetzt.</p>
    <?php endif; ?>
</div>

<div class="card">
    <h2>Interne Benutzer</h2>
    <div class="table-wrap"><table class="list">
        <thead><tr><th>Benutzer</th><th>Name</th><th>E-Mail</th><th>Rolle</th><th>Niederlassung</th><th>Aktiv</th><th>Letzter Login</th><th></th></tr></thead>
        <tbody>
        <?php foreach ($users as $u): ?>
            <tr>
                <td><?= e($u['username']) ?></td>
                <td><?= e(trim(($u['first_name'] ?? '') . ' ' . ($u['last_name'] ?? ''))) ?></td>
                <td><?= e($u['email']) ?></td>
                <td><?= e(user_role_label($u['role'])) ?></td>
                <td><?= e($u['branch']) ?></td>
                <td><?= $u['is_active'] ? 'Ja' : '<span class="badge badge-cancelled">Nein</span>' ?></td>
                <td><?= e(fmt_datetime($u['last_login_at'])) ?></td>
                <td><a class="btn btn-sm btn-secondary" href="<?= e(url('/admin/users?edit=' . $u['id'])) ?>#user-form">Bearbeiten</a></td>
            </tr>
        <?php endforeach; ?>
        </tbody>
    </table></div>
</div>

<div class="card">
    <h2>Gehilfenzugang anlegen (Mieter, Eigentümer, Beauftragter)</h2>
    <p class="muted small">
        Der Gehilfe erhält Benutzername und Passwort per E-Mail und sieht ausschließlich das ihm zugewiesene Protokoll.
        Er kann es ausfüllen, unterschreiben und abschließen, jedoch keine weiteren Protokolle einsehen oder anlegen.
        Ohne Angabe eines bestehenden Protokolls wird automatisch ein neues Protokoll als Vorlage erzeugt.
    </p>
    <form method="post" action="<?= e(url('/helpers/create')) ?>">
        <?= \App\Core\Csrf::field() ?>
        <input type="hidden" name="return_to" value="admin">
        <div class="grid grid-3">
            <div class="field"><label>E-Mail-Adresse</label><input type="email" name="email" required></div>
            <div class="field"><label>Vorname</label><input type="text" name="first_name"></div>
            <div class="field"><label>Nachname</label><input type="text" name="last_name"></div>
            <div class="field"><label>Art des Zugangs</label>
                <select name="helper_type">
                    <?php foreach (helper_types() as $key => $label): ?>
                        <option value="<?= e($key) ?>"><?= e($label) ?></option>
                    <?php endforeach; ?>
                </select></div>
            <div class="field"><label>Bestehendes Protokoll (ID, optional)</label><input type="number" name="protocol_id" min="1" placeholder="leer = neue Vorlage anlegen"></div>
        </div>
        <fieldset style="border:1px solid var(--color-border);border-radius:8px;padding:0.6rem 0.8rem;margin:0.4rem 0 0.8rem">
            <legend class="muted small">Nur für eine neue Vorlage (entfällt bei Angabe eines bestehenden Protokolls)</legend>
            <div class="grid grid-3">
                <div class="field"><label>Protokollart</label>
                    <select name="protocol_type">
                        <?php foreach (protocol_types() as $key => $label): ?>
                            <option value="<?= e($key) ?>"><?= e($label) ?></option>
                        <?php endforeach; ?>
                    </select></div>
                <div class="field"><label>Gehilfe als Beteiligten übernehmen</label>
                    <select name="participant_side">
                        <option value="">Nicht übernehmen</option>
                        <option value="in">Als einziehende bzw. übernehmende Partei</option>
                        <option value="out">Als ausziehende bzw. übergebende Partei</option>
                    </select></div>
                <div class="field"><label>Übergabedatum</label><input type="date" name="handover_date"></div>
                <div class="field"><label>Straße</label><input type="text" name="street"></div>
                <div class="field"><label>Hausnummer</label><input type="text" name="house_number"></div>
                <div class="field"><label>PLZ</label><input type="text" name="postal_code"></div>
                <div class="field"><label>Ort</label><input type="text" name="city"></div>
                <div class="field"><label>Einheit</label><input type="text" name="unit_number"></div>
            </div>
        </fieldset>
        <button type="submit" class="btn">Zugang anlegen und Zugangsdaten senden</button>
    </form>

    <?php if ($helpers !== []): ?>
        <h3>Bestehende Gehilfenzugänge</h3>
        <div class="table-wrap"><table class="list">
            <thead><tr><th>Benutzername</th><th>Name</th><th>E-Mail</th><th>Art</th><th>Protokolle</th><th>Aktiv</th><th>Letzter Login</th><th></th></tr></thead>
            <tbody>
            <?php foreach ($helpers as $h): ?>
                <tr>
                    <td><?= e($h['username']) ?></td>
                    <td><?= e(trim(($h['first_name'] ?? '') . ' ' . ($h['last_name'] ?? ''))) ?></td>
                    <td><?= e($h['email']) ?></td>
                    <td><?= e(helper_type_label($h['helper_type'] ?? null)) ?></td>
                    <td><?= e($h['protocols']) ?: '<span class="muted">keines</span>' ?></td>
                    <td><?= $h['is_active'] ? 'Ja' : '<span class="badge badge-cancelled">Nein</span>' ?></td>
                    <td><?= e(fmt_datetime($h['last_login_at'])) ?: '<span class="muted">nie</span>' ?></td>
                    <td style="white-space:nowrap">
                        <a class="btn btn-sm btn-secondary" href="<?= e(url('/admin/users?edit=' . $h['id'])) ?>#user-form">Bearbeiten</a>
                        <form method="post" action="<?= e(url('/admin/helpers/resend')) ?>" class="inline"
                              data-confirm="Neues Passwort erzeugen und Zugangsdaten erneut senden? Das bisherige Passwort wird ungültig.">
                            <?= \App\Core\Csrf::field() ?>
                            <input type="hidden" name="user_id" value="<?= (int) $h['id'] ?>">
                            <button type="submit" class="btn btn-sm btn-secondary">Zugangsdaten erneut senden</button>
                        </form>
                    </td>
                </tr>
            <?php endforeach; ?>
            </tbody>
        </table></div>
    <?php endif; ?>
</div>

<div class="card" id="user-form">
    <h2><?= $editUser ? 'Benutzer bearbeiten: ' . e($editUser['username']) : 'Benutzer direkt anlegen' ?></h2>
    <?php if (!$editUser): ?>
        <p class="muted small">Empfohlen ist die Einladung per E-Mail (oben). Hier kann ein interner Benutzer alternativ direkt mit Passwort angelegt werden. Gehilfenzugänge entstehen ausschließlich über das Formular "Gehilfenzugang anlegen".</p>
    <?php endif; ?>
    <form method="post" action="<?= e(url('/admin/users/save')) ?>">
        <?= \App\Core\Csrf::field() ?>
        <input type="hidden" name="user_id" value="<?= (int) ($editUser['id'] ?? 0) ?>">
        <div class="grid grid-3">
            <div class="field"><label>Benutzername</label><input type="text" name="username" required value="<?= e($editUser['username'] ?? '') ?>"></div>
            <div class="field"><label>E-Mail</label><input type="email" name="email" required value="<?= e($editUser['email'] ?? '') ?>"></div>
            <div class="field"><label>Rolle</label>
                <?php if (($editUser['role'] ?? '') === 'helper'): ?>
                    <input type="text" value="<?= e(user_role_label('helper')) ?>, <?= e(helper_type_label($editUser['helper_type'] ?? null)) ?>" readonly>
                    <input type="hidden" name="role" value="helper">
                <?php else: ?>
                    <select name="role">
                        <?php foreach (user_roles() as $key => $label): if ($key === 'helper') { continue; } ?>
                            <option value="<?= e($key) ?>" <?= ($editUser['role'] ?? 'employee') === $key ? 'selected' : '' ?>><?= e($label) ?></option>
                        <?php endforeach; ?>
                    </select>
                <?php endif; ?></div>
            <div class="field"><label>Vorname</label><input type="text" name="first_name" value="<?= e($editUser['first_name'] ?? '') ?>"></div>
            <div class="field"><label>Nachname</label><input type="text" name="last_name" value="<?= e($editUser['last_name'] ?? '') ?>"></div>
            <div class="field"><label>Niederlassung</label>
                <select name="branch_id"><option value=""></option>
                    <?php foreach ($branches as $b): ?>
                        <option value="<?= (int) $b['id'] ?>" <?= (int) ($editUser['branch_id'] ?? 0) === (int) $b['id'] ? 'selected' : '' ?>><?= e($b['name']) ?></option>
                    <?php endforeach; ?>
                </select></div>
            <div class="field"><label>Passwort <?= $editUser ? '(nur bei Änderung ausfüllen)' : '(min. 10 Zeichen)' ?></label>
                <input type="password" name="password" autocomplete="new-password"></div>
            <div class="field"><label>Aktiv</label>
                <select name="is_active">
                    <option value="1" <?= (int) ($editUser['is_active'] ?? 1) === 1 ? 'selected' : '' ?>>Ja</option>
                    <option value="0" <?= isset($editUser) && $editUser && (int) $editUser['is_active'] === 0 ? 'selected' : '' ?>>Nein (gesperrt)</option>
                </select></div>
        </div>
        <div class="btn-row">
            <button type="submit" class="btn">Speichern</button>
            <?php if ($editUser): ?>
                <a class="btn btn-secondary" href="<?= e(url('/admin/users')) ?>">Abbrechen</a>
            <?php endif; ?>
        </div>
    </form>
</div>
