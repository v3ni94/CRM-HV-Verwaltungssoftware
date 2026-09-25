<?php
/** Detailansicht eines Protokolls mit Aktionen, Historien und Teildaten. */
$p = $protocol;
$base = url('/protocols/' . $p['id']);
$locked = \App\Repositories\ProtocolRepository::isLocked($p);
$isAdmin = \App\Core\Auth::isAdmin();
?>
<div class="section-head">
    <div>
        <h1><?= e($p['protocol_number']) ?><?= (int) $p['version'] > 1 ? ', Version ' . (int) $p['version'] : '' ?></h1>
        <p class="muted"><?= e(protocol_address($p)) ?: 'Ohne Objektadresse' ?><?= $p['handover_date'] ? ' · ' . e(fmt_date($p['handover_date'])) : '' ?></p>
    </div>
    <div><?= status_badge($p['status']) ?></div>
</div>

<div class="card">
    <div class="btn-row">
        <?php if (!$locked): ?>
            <a class="btn" href="<?= e($base . '/wizard/' . ($p['current_step'] ?: 'object')) ?>">Fortsetzen</a>
        <?php endif; ?>
        <a class="btn btn-secondary" href="<?= e($base . '/pdf') ?>" target="_blank" rel="noopener">PDF anzeigen</a>
        <a class="btn btn-secondary" href="<?= e($base . '/pdf/download') ?>">PDF herunterladen</a>
        <a class="btn btn-secondary" href="<?= e($base . '/print') ?>" target="_blank" rel="noopener">Druckansicht</a>
        <a class="btn btn-secondary" href="<?= e($base . '/defects.pdf') ?>" target="_blank" rel="noopener">Mängelliste (PDF)</a>
        <a class="btn btn-secondary" href="<?= e($base . '/email') ?>">E-Mail senden</a>
        <a class="btn" href="<?= e($base . '/email?all=1') ?>">An alle Beteiligten senden</a>
    </div>
    <div class="btn-row">
        <?php if ($locked && $p['status'] !== 'cancelled'): ?>
            <form method="post" action="<?= e($base . '/new-version') ?>" data-confirm="Es wird eine neue, bearbeitbare Version dieses Protokolls angelegt. Fortfahren?">
                <?= \App\Core\Csrf::field() ?>
                <input type="text" name="change_reason" placeholder="Änderungsgrund" style="max-width:280px;display:inline-block">
                <button type="submit" class="btn btn-secondary">Neue Version</button>
            </form>
        <?php endif; ?>
        <form method="post" action="<?= e($base . '/duplicate') ?>" style="display:inline-flex;gap:0.5rem;flex-wrap:wrap;align-items:center">
            <?= \App\Core\Csrf::field() ?>
            <span class="small muted">Übernehmen:</span>
            <span class="checkbox-row small"><input type="checkbox" name="copy_object" value="1" id="co" checked><label for="co">Objekt</label></span>
            <span class="checkbox-row small"><input type="checkbox" name="copy_rooms" value="1" id="cr" checked><label for="cr">Räume</label></span>
            <span class="checkbox-row small"><input type="checkbox" name="copy_meters" value="1" id="cm"><label for="cm">Zählertypen</label></span>
            <span class="checkbox-row small"><input type="checkbox" name="copy_keys" value="1" id="ck"><label for="ck">Schlüsselarten</label></span>
            <button type="submit" class="btn btn-secondary">Duplizieren</button>
        </form>
        <?php if ($isAdmin && $p['status'] !== 'archived'): ?>
            <form method="post" action="<?= e($base . '/archive') ?>" data-confirm="Protokoll archivieren? Es bleibt über den Filter 'Archivierte anzeigen' erreichbar."><?= \App\Core\Csrf::field() ?><button class="btn btn-secondary">Archivieren</button></form>
        <?php endif; ?>
        <?php if ($isAdmin && $p['status'] === 'archived'): ?>
            <form method="post" action="<?= e($base . '/unarchive') ?>"><?= \App\Core\Csrf::field() ?><button class="btn btn-secondary">Aus dem Archiv zurückholen</button></form>
        <?php endif; ?>
        <?php if ($p['status'] !== 'cancelled' && (!$locked || $isAdmin)): ?>
            <form method="post" action="<?= e($base . '/cancel') ?>" data-confirm="Protokoll wirklich stornieren? Die Daten bleiben erhalten."><?= \App\Core\Csrf::field() ?><button class="btn btn-danger">Stornieren</button></form>
        <?php endif; ?>
    </div>
</div>

<div class="card">
    <h2>Stammdaten</h2>
    <dl class="kv">
        <dt>Protokollart</dt><dd><?= e(protocol_types()[$p['protocol_type']]) ?></dd>
        <dt>Ticketnummer</dt><dd><?= e($p['ticket_number']) ?: '–' ?></dd>
        <dt>Verwaltungsnummer</dt><dd><?= e($p['management_number']) ?: '–' ?></dd>
        <dt>Referenznummer</dt><dd><?= e($p['reference_number']) ?: '–' ?></dd>
        <dt>Objekt</dt><dd><?= e(protocol_address($p)) ?: '–' ?></dd>
        <dt>Einheit</dt><dd><?= e(trim(($p['unit_number'] ?? '') . ' ' . ($p['unit_position'] ?? ''))) ?: '–' ?></dd>
        <dt>Übergabedatum</dt><dd><?= e(fmt_date($p['handover_date'])) ?: '–' ?></dd>
        <dt>Gestartet am</dt><dd><?= e(fmt_datetime($p['created_at'])) ?></dd>
        <dt>Abgeschlossen am</dt><dd><?= e(fmt_datetime($p['completed_at'])) ?: '–' ?></dd>
        <dt>Zuletzt geändert</dt><dd><?= e(fmt_datetime($p['updated_at'])) ?: '–' ?></dd>
        <?php if ($p['internal_note']): ?><dt>Interne Bemerkung</dt><dd class="muted"><?= nl2br(e($p['internal_note'])) ?> <span class="badge badge-draft">intern</span></dd><?php endif; ?>
    </dl>
</div>

<div class="card">
    <h2>Beteiligte (<?= count($participants) ?>)</h2>
    <?php foreach ($participants as $pt): ?>
        <p style="margin:0.25rem 0"><strong><?= e(participant_role_label($pt['role'], $p['protocol_type'])) ?>:</strong>
            <?= e(trim(($pt['salutation'] ?? '') . ' ' . ($pt['first_name'] ?? '') . ' ' . ($pt['last_name'] ?? '') . ($pt['company'] ? ' (' . $pt['company'] . ')' : ''))) ?>
            <?php if ($pt['email']): ?> · <?= e($pt['email']) ?><?php endif; ?>
            <?php if ($pt['phone'] || $pt['mobile']): ?> · <?= e($pt['mobile'] ?: $pt['phone']) ?><?php endif; ?></p>
    <?php endforeach; ?>
</div>

<div class="grid grid-2">
    <div class="card">
        <h2>Zähler (<?= count($meters) ?>)</h2>
        <?php foreach ($meters as $m): ?>
            <p style="margin:0.25rem 0"><?= e($m['custom_type'] ?: (meter_types()[$m['meter_type']] ?? 'Zähler')) ?>: <strong><?= e($m['meter_value']) ?> <?= e($m['unit']) ?></strong> <span class="muted small"><?= e($m['meter_number']) ?></span></p>
        <?php endforeach; ?>
    </div>
    <div class="card">
        <h2>Schlüssel (<?= count($keys) ?>)</h2>
        <?php foreach ($keys as $k): ?>
            <p style="margin:0.25rem 0"><?= e($k['custom_name'] ?: $k['key_type']) ?>, Anzahl: <?= $k['quantity'] !== null ? (int) $k['quantity'] : '–' ?> <?= $k['status'] ? '(' . e(key_statuses()[$k['status']] ?? '') . ')' : '' ?></p>
        <?php endforeach; ?>
    </div>
</div>

<div class="card">
    <h2>Räume und Mängel</h2>
    <?php foreach ($rooms as $room): ?>
        <p style="margin:0.3rem 0"><strong><?= e($room['room_name'] ?: $room['room_type']) ?>:</strong> <?= e(room_conditions()[$room['condition_status']] ?? 'Keine Angabe') ?></p>
        <?php foreach ($defects as $d): if ((int) $d['room_id'] !== (int) $room['id']) continue; ?>
            <p class="small" style="margin:0.15rem 0 0.15rem 1rem">• <?= e($d['title'] ?: $d['category']) ?><?= $d['priority'] ? ' (' . e(defect_priorities()[$d['priority']] ?? '') . ')' : '' ?><?= $d['description'] ? ': ' . e($d['description']) : '' ?></p>
        <?php endforeach; ?>
    <?php endforeach; ?>
</div>

<div class="card">
    <h2>Dateien (<?= count($files) ?>)</h2>
    <div class="thumb-list">
        <?php foreach ($files as $f): if ($f['file_category'] === 'signature') continue; ?>
            <div class="thumb-item">
                <?php if (str_starts_with((string) $f['mime_type'], 'image/')): ?>
                    <a href="<?= e(url('/files/' . $f['id'])) ?>" target="_blank" rel="noopener"><img src="<?= e(url('/files/' . $f['id'] . '/thumb')) ?>" alt=""></a>
                <?php else: ?>
                    <a class="thumb-doc" href="<?= e(url('/files/' . $f['id'])) ?>" target="_blank" rel="noopener"><?= e($f['original_filename']) ?></a>
                <?php endif; ?>
                <?php if ($f['is_internal']): ?><span class="badge badge-draft">intern</span><?php endif; ?>
            </div>
        <?php endforeach; ?>
    </div>
</div>

<div class="card">
    <h2>Signaturen (<?= count($signatures) ?>)</h2>
    <?php foreach ($signatures as $sig): ?>
        <p style="margin:0.25rem 0"><?= e($sig['signer_name'] ?: 'Ohne Namen') ?>, <?= e(signature_roles($p['protocol_type'])[$sig['signer_role']] ?? $sig['signer_role']) ?>, <?= e(fmt_datetime($sig['signed_at'])) ?>
            <span class="muted small">SHA-256: <?= e(substr((string) $sig['sha256'], 0, 16)) ?>…</span></p>
    <?php endforeach; ?>
</div>

<div class="card">
    <h2>Gehilfenzugänge (Mieter, Eigentümer, Beauftragte)</h2>
    <p class="muted small" style="margin-top:0">
        Ein Gehilfe führt die Übergabe selbst durch. Er sieht ausschließlich dieses Protokoll, kann es ausfüllen,
        unterschreiben und abschließen. Interne Angaben der Hausverwaltung bleiben für ihn verborgen.
        Mitarbeiter und Administratoren können das Protokoll parallel vorbereiten und mit ausfüllen.
    </p>

    <?php if ($helpers !== []): ?>
        <div class="table-wrap"><table class="list">
            <thead><tr><th>Benutzername</th><th>Name</th><th>E-Mail</th><th>Art</th><th>Letzter Login</th><th></th></tr></thead>
            <tbody>
            <?php foreach ($helpers as $h): ?>
                <tr>
                    <td><?= e($h['username']) ?></td>
                    <td><?= e(trim(($h['first_name'] ?? '') . ' ' . ($h['last_name'] ?? ''))) ?></td>
                    <td><?= e($h['email']) ?></td>
                    <td><?= e(helper_type_label($h['helper_type'] ?? null)) ?></td>
                    <td><?= e(fmt_datetime($h['last_login_at'])) ?: '<span class="muted">nie</span>' ?></td>
                    <td style="white-space:nowrap">
                        <form method="post" action="<?= e($base . '/helper-access/resend') ?>" class="inline"
                              data-confirm="Neues Passwort erzeugen und Zugangsdaten erneut senden? Das bisherige Passwort wird ungültig.">
                            <?= \App\Core\Csrf::field() ?>
                            <input type="hidden" name="user_id" value="<?= (int) $h['id'] ?>">
                            <button type="submit" class="btn btn-sm btn-secondary">Zugangsdaten erneut senden</button>
                        </form>
                        <form method="post" action="<?= e($base . '/helper-access/revoke') ?>" class="inline"
                              data-confirm="Zugang zu diesem Protokoll wirklich entziehen?">
                            <?= \App\Core\Csrf::field() ?>
                            <input type="hidden" name="user_id" value="<?= (int) $h['id'] ?>">
                            <button type="submit" class="btn btn-sm btn-danger">Zugang entziehen</button>
                        </form>
                    </td>
                </tr>
            <?php endforeach; ?>
            </tbody>
        </table></div>
    <?php else: ?>
        <p class="muted">Für dieses Protokoll ist kein Gehilfenzugang eingerichtet.</p>
    <?php endif; ?>

    <?php if (\App\Core\Auth::isStaff() && \App\Core\Auth::canWrite()): ?>
        <h3>Zugang anlegen und Zugangsdaten senden</h3>
        <form method="post" action="<?= e($base . '/helper-access') ?>">
            <?= \App\Core\Csrf::field() ?>
            <div class="grid grid-4">
                <div class="field"><label>E-Mail-Adresse</label><input type="email" name="email" required></div>
                <div class="field"><label>Vorname</label><input type="text" name="first_name"></div>
                <div class="field"><label>Nachname</label><input type="text" name="last_name"></div>
                <div class="field"><label>Art des Zugangs</label>
                    <select name="helper_type">
                        <?php foreach (helper_types() as $key => $label): ?>
                            <option value="<?= e($key) ?>"><?= e($label) ?></option>
                        <?php endforeach; ?>
                    </select></div>
            </div>
            <button type="submit" class="btn">Zugang anlegen und Zugangsdaten senden</button>
        </form>
    <?php endif; ?>
</div>

<div class="card">
    <h2>Versionshistorie</h2>
    <div class="table-wrap"><table class="list">
        <thead><tr><th>Version</th><th>Erstellt</th><th>Änderungsgrund</th><th>SHA-256 (PDF)</th><th></th></tr></thead>
        <tbody>
        <?php foreach ($versions as $v): ?>
            <tr>
                <td><?= (int) $v['version_number'] ?></td>
                <td><?= e(fmt_datetime($v['created_at'])) ?></td>
                <td><?= e($v['change_reason']) ?></td>
                <td class="small muted"><?= e(substr((string) $v['sha256'], 0, 20)) ?>…</td>
                <td><?php if ($v['pdf_file_id']): ?><a href="<?= e(url('/files/' . $v['pdf_file_id'])) ?>" target="_blank" rel="noopener">PDF öffnen</a><?php endif; ?></td>
            </tr>
        <?php endforeach; ?>
        <?php if ($versions === []): ?><tr><td colspan="5" class="muted">Noch keine PDF-Version erzeugt.</td></tr><?php endif; ?>
        </tbody>
    </table></div>
    <?php
    $relatives = \App\Core\Database::fetchAll(
        'SELECT id, version, status, created_at FROM protocols WHERE protocol_number = ? AND id != ? ORDER BY version',
        [$p['protocol_number'], $p['id']]
    );
    if ($relatives !== []): ?>
        <p class="small muted">Weitere Versionen dieses Protokolls:
            <?php foreach ($relatives as $rel): ?>
                <a href="<?= e(url('/protocols/' . $rel['id'])) ?>">Version <?= (int) $rel['version'] ?> (<?= e(protocol_statuses()[$rel['status']] ?? '') ?>)</a>&nbsp;
            <?php endforeach; ?></p>
    <?php endif; ?>
</div>

<div class="card">
    <h2>Versandhistorie</h2>
    <div class="table-wrap"><table class="list">
        <thead><tr><th>Datum</th><th>Empfänger</th><th>Betreff</th><th>Status</th><th>Fehler</th></tr></thead>
        <tbody>
        <?php foreach ($emails as $mail): ?>
            <tr>
                <td><?= e(fmt_datetime($mail['sent_at'])) ?></td>
                <td><?= e($mail['recipients']) ?><?= $mail['cc'] ? '<br><span class="muted small">CC: ' . e($mail['cc']) . '</span>' : '' ?></td>
                <td><?= e($mail['subject']) ?></td>
                <td><?= $mail['status'] === 'sent' ? '<span class="badge badge-completed">Versendet</span>' : '<span class="badge badge-cancelled">Fehlgeschlagen</span>' ?></td>
                <td class="small muted"><?= e($mail['error_message']) ?></td>
            </tr>
        <?php endforeach; ?>
        <?php if ($emails === []): ?><tr><td colspan="5" class="muted">Noch kein Versand.</td></tr><?php endif; ?>
        </tbody>
    </table></div>
</div>

<div class="card">
    <h2>Änderungshistorie</h2>
    <p class="muted small">Jede Änderung wird mit Benutzer und Zeitpunkt festgehalten. Abgeschlossene Fassungen bleiben unverändert erhalten, die zugehörigen Original-PDFs stehen in der Versionshistorie.</p>
    <div class="table-wrap"><table class="list">
        <thead><tr><th>Zeitpunkt</th><th>Benutzer</th><th>Aktion</th></tr></thead>
        <tbody>
        <?php foreach (($changes ?? []) as $c): ?>
            <tr>
                <td style="white-space:nowrap"><?= e(fmt_datetime($c['created_at'])) ?></td>
                <td><?= e($c['username']) ?></td>
                <td><?= e(audit_action_label($c['action'])) ?></td>
            </tr>
        <?php endforeach; ?>
        <?php if (($changes ?? []) === []): ?><tr><td colspan="3" class="muted">Noch keine Änderungen erfasst.</td></tr><?php endif; ?>
        </tbody>
    </table></div>
    <?php if ($isAdmin): ?>
        <p class="small"><a href="<?= e(url('/admin/audit?protocol_id=' . $p['id'])) ?>">Vollständiges Audit-Log mit Details anzeigen (Administration)</a></p>
    <?php endif; ?>
</div>
