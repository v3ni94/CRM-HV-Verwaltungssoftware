<?php
/** @var array $rows, $stats */
$types = protocol_types();
$statuses = protocol_statuses();
$qs = $_GET;
function sort_link(string $key, string $label): string {
    $qs = $_GET;
    $dir = (($qs['sort'] ?? 'id') === $key && ($qs['dir'] ?? 'desc') === 'desc') ? 'asc' : 'desc';
    $qs['sort'] = $key;
    $qs['dir'] = $dir;
    return '<a href="?' . e(http_build_query($qs)) . '">' . e($label) . '</a>';
}
?>
<h1>Übergabeprotokolle</h1>

<div class="card">
    <h2>+ Neues Übergabeprotokoll</h2>
    <div class="grid grid-3">
        <?php foreach ($types as $key => $label): ?>
            <form method="post" action="<?= e(url('/protocols/create')) ?>">
                <?= \App\Core\Csrf::field() ?>
                <input type="hidden" name="protocol_type" value="<?= e($key) ?>">
                <button type="submit" class="btn btn-block"><?= e($label) ?></button>
            </form>
        <?php endforeach; ?>
    </div>
</div>

<?php if (\App\Core\Auth::isStaff() && \App\Core\Auth::canWrite()): ?>
<div class="card">
    <details class="filter-box">
        <summary>Gehilfenzugang mit Protokollvorlage anlegen (Mieter, Eigentümer, Beauftragter)</summary>
        <p class="muted small" style="margin-top:0.5rem">
            Für Übergaben ohne Anwesenheit der Hausverwaltung: Es wird ein Protokoll als Vorlage angelegt und der Gehilfe erhält
            Benutzername und Passwort per E-Mail. Er sieht ausschließlich dieses Protokoll, kann es ausfüllen, unterschreiben und
            abschließen. Bestehende Protokolle erhalten einen Gehilfenzugang direkt in der Protokollansicht.
        </p>
        <form method="post" action="<?= e(url('/helpers/create')) ?>">
            <?= \App\Core\Csrf::field() ?>
            <input type="hidden" name="return_to" value="dashboard">
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
                <div class="field"><label>Protokollart</label>
                    <select name="protocol_type">
                        <?php foreach ($types as $key => $label): ?>
                            <option value="<?= e($key) ?>"><?= e($label) ?></option>
                        <?php endforeach; ?>
                    </select></div>
                <div class="field"><label>Gehilfe als Beteiligten übernehmen</label>
                    <select name="participant_side">
                        <option value="">Nicht übernehmen</option>
                        <option value="in">Einziehende bzw. übernehmende Partei</option>
                        <option value="out">Ausziehende bzw. übergebende Partei</option>
                    </select></div>
                <div class="field"><label>Übergabedatum</label><input type="date" name="handover_date"></div>
                <div class="field"><label>Einheit</label><input type="text" name="unit_number"></div>
                <div class="field"><label>Straße</label><input type="text" name="street"></div>
                <div class="field"><label>Hausnummer</label><input type="text" name="house_number"></div>
                <div class="field"><label>PLZ</label><input type="text" name="postal_code"></div>
                <div class="field"><label>Ort</label><input type="text" name="city"></div>
            </div>
            <button type="submit" class="btn">Vorlage anlegen und Zugangsdaten senden</button>
        </form>
    </details>
</div>
<?php endif; ?>

<div class="stats">
    <div class="stat"><div class="value"><?= (int) $stats['total'] ?></div><div class="label">Protokolle insgesamt</div></div>
    <div class="stat"><div class="value"><?= (int) $stats['drafts'] ?></div><div class="label">Offene Entwürfe</div></div>
    <div class="stat"><div class="value"><?= (int) $stats['today'] ?></div><div class="label">Heute erstellt</div></div>
    <div class="stat"><div class="value"><?= (int) $stats['month_done'] ?></div><div class="label">Diesen Monat abgeschlossen</div></div>
    <div class="stat"><div class="value"><?= (int) $stats['unsent'] ?></div><div class="label">Noch nicht versendet</div></div>
</div>

<div class="card">
    <form method="get" action="<?= e(url('/protocols')) ?>">
        <!-- Suchleiste: durchsucht Protokollnummer, Ticketnummer, Adresse, PLZ und Namen -->
        <div style="display:flex;gap:0.6rem;flex-wrap:wrap">
            <div class="field" style="flex:1;min-width:220px;margin-bottom:0.4rem">
                <input type="search" name="q" value="<?= e($qs['q'] ?? '') ?>" placeholder="Suchen: Name, Adresse, PLZ, Ticket- oder Protokollnummer" aria-label="Suche">
            </div>
            <button type="submit" class="btn">Suchen</button>
            <?php if (array_filter(array_intersect_key($qs, array_flip(['q','status','type','ticket','street','zip','city','name','date_from','date_to','user','show_archived'])))): ?>
                <a class="btn btn-secondary" href="<?= e(url('/protocols')) ?>">Zurücksetzen</a>
            <?php endif; ?>
        </div>

    <details class="filter-box" <?= array_filter(array_intersect_key($qs, array_flip(['status','type','ticket','street','zip','city','name','date_from','date_to','user','show_archived']))) ? 'open' : '' ?>>
    <summary>Erweiterte Filter</summary>
        <div class="grid grid-4" style="margin-top:0.5rem">
            <div class="field"><label>Status</label>
                <select name="status">
                    <option value="">Alle</option>
                    <?php foreach ($statuses as $key => $label): ?>
                        <option value="<?= e($key) ?>" <?= ($qs['status'] ?? '') === $key ? 'selected' : '' ?>><?= e($label) ?></option>
                    <?php endforeach; ?>
                </select></div>
            <div class="field"><label>Protokolltyp</label>
                <select name="type">
                    <option value="">Alle</option>
                    <?php foreach ($types as $key => $label): ?>
                        <option value="<?= e($key) ?>" <?= ($qs['type'] ?? '') === $key ? 'selected' : '' ?>><?= e($label) ?></option>
                    <?php endforeach; ?>
                </select></div>
            <div class="field"><label>Ticketnummer</label>
                <input type="text" name="ticket" value="<?= e($qs['ticket'] ?? '') ?>"></div>
            <div class="field"><label>Straße</label>
                <input type="text" name="street" value="<?= e($qs['street'] ?? '') ?>"></div>
            <div class="field"><label>PLZ</label>
                <input type="text" name="zip" value="<?= e($qs['zip'] ?? '') ?>"></div>
            <div class="field"><label>Ort</label>
                <input type="text" name="city" value="<?= e($qs['city'] ?? '') ?>"></div>
            <div class="field"><label>Name Beteiligter</label>
                <input type="text" name="name" value="<?= e($qs['name'] ?? '') ?>"></div>
            <div class="field"><label>Übergabedatum von</label>
                <input type="date" name="date_from" value="<?= e($qs['date_from'] ?? '') ?>"></div>
            <div class="field"><label>Übergabedatum bis</label>
                <input type="date" name="date_to" value="<?= e($qs['date_to'] ?? '') ?>"></div>
            <div class="field"><label>Bearbeiter</label>
                <input type="text" name="user" value="<?= e($qs['user'] ?? '') ?>"></div>
            <div class="checkbox-row">
                <input type="checkbox" id="show_archived" name="show_archived" value="1" <?= ($qs['show_archived'] ?? '') === '1' ? 'checked' : '' ?>>
                <label for="show_archived">Archivierte anzeigen</label>
            </div>
        </div>
        <div class="btn-row">
            <button type="submit" class="btn btn-secondary">Filter anwenden</button>
            <a class="btn btn-secondary" href="<?= e(url('/protocols/export.csv') . ($_SERVER['QUERY_STRING'] ? '?' . $_SERVER['QUERY_STRING'] : '')) ?>">CSV-Export</a>
        </div>
    </details>
    </form>
</div>

<div class="card">
    <p class="muted small" style="margin-top:0">
        Zeile anklicken öffnet das Protokoll im jeweiligen Bearbeitungsstand.
        Farben: <span class="dot dot-red"></span> kaum Daten
        <span class="dot dot-yellow"></span> erfasst, nicht abgeschlossen
        <span class="dot dot-green"></span> abgeschlossen
        <span class="dot dot-blue"></span> archiviert
        <span class="dot dot-gray"></span> storniert
    </p>
    <?php
    $rowTarget = fn(array $r): string => in_array($r['status'], ['draft', 'in_progress', 'signature_pending', 'rework'], true)
        ? url('/protocols/' . $r['id'] . '/wizard/' . ($r['current_step'] ?: 'object'))
        : url('/protocols/' . $r['id']);
    ?>

    <!-- Mobile: Kartenansicht -->
    <div class="protocol-cards">
        <?php if ($rows === []): ?><p class="muted">Keine Protokolle gefunden.</p><?php endif; ?>
        <?php foreach ($rows as $r): ?>
            <div class="protocol-card row-<?= e(\App\Controllers\DashboardController::rowColor($r)) ?> row-click" data-href="<?= e($rowTarget($r)) ?>">
                <div class="pc-head">
                    <span class="pc-title"><?= e($r['protocol_number'] ?: (string) $r['id']) ?><?= (int) $r['version'] > 1 ? ' V' . (int) $r['version'] : '' ?></span>
                    <?= status_badge($r['status']) ?>
                </div>
                <div class="pc-line"><?= e(protocol_address($r)) ?: '<span class="muted">Ohne Objektadresse</span>' ?></div>
                <div class="pc-line muted small">
                    <?= e(match ($r['protocol_type']) { 'rental' => 'Vermietung', 'sale' => 'Verkauf', default => 'Allgemein' }) ?>
                    <?= $r['ticket_number'] ? ' · Ticket ' . e($r['ticket_number']) : '' ?>
                    <?= $r['handover_date'] ? ' · ' . e(fmt_date($r['handover_date'])) : '' ?>
                </div>
                <?php if ($r['party_out'] || $r['party_in']): ?>
                    <div class="pc-line small"><?= e($r['party_out']) ?><?= $r['party_out'] && $r['party_in'] ? ' → ' : '' ?><?= e($r['party_in']) ?></div>
                <?php endif; ?>
            </div>
        <?php endforeach; ?>
    </div>

    <!-- Desktop: kompakte Tabellenansicht, ganze Zeile klickbar -->
    <?php $isAdmin = \App\Core\Auth::isAdmin(); ?>
    <?php if ($isAdmin): ?><form method="post" action="<?= e(url('/protocols/bulk-archive')) ?>" data-confirm="Ausgewählte Protokolle archivieren? Sie bleiben über den Filter 'Archivierte anzeigen' erreichbar."><?= \App\Core\Csrf::field() ?><?php endif; ?>
    <div class="table-wrap responsive-cards">
    <table class="list">
        <thead><tr>
            <?php if ($isAdmin): ?><th><input type="checkbox" data-check-all title="Alle auswählen"></th><?php endif; ?>
            <th><?= sort_link('id', 'Protokoll') ?></th>
            <th><?= sort_link('status', 'Status') ?></th>
            <th>Objekt</th>
            <th>Beteiligte</th>
            <th><?= sort_link('date', 'Übergabe') ?></th>
            <th><?= sort_link('updated', 'Geändert') ?></th>
        </tr></thead>
        <tbody>
        <?php if ($rows === []): ?>
            <tr><td colspan="7" class="muted">Keine Protokolle gefunden.</td></tr>
        <?php endif; ?>
        <?php foreach ($rows as $r): ?>
            <tr class="row-<?= e(\App\Controllers\DashboardController::rowColor($r)) ?> row-click" data-href="<?= e($rowTarget($r)) ?>">
                <?php if ($isAdmin): ?><td><input type="checkbox" name="ids[]" value="<?= (int) $r['id'] ?>"></td><?php endif; ?>
                <td>
                    <strong><?= e($r['protocol_number'] ?: (string) $r['id']) ?></strong><?= (int) $r['version'] > 1 ? ' <span class="muted small">V' . (int) $r['version'] . '</span>' : '' ?><br>
                    <span class="muted small"><?= e(match ($r['protocol_type']) { 'rental' => 'Vermietung', 'sale' => 'Verkauf', default => 'Allgemein' }) ?><?= $r['ticket_number'] ? ' · Ticket ' . e($r['ticket_number']) : '' ?></span>
                </td>
                <td><?= status_badge($r['status']) ?></td>
                <td>
                    <?= e(protocol_address($r)) ?: '<span class="muted">–</span>' ?>
                    <?php if (trim(($r['unit_number'] ?? '') . ($r['unit_position'] ?? '')) !== ''): ?>
                        <br><span class="muted small"><?= e(trim(($r['unit_number'] ? 'Einheit ' . $r['unit_number'] . ' ' : '') . ($r['unit_position'] ?? ''))) ?></span>
                    <?php endif; ?>
                </td>
                <td><?= e($r['party_out']) ?><?= $r['party_out'] && $r['party_in'] ? ' → ' : '' ?><?= e($r['party_in']) ?></td>
                <td style="white-space:nowrap"><?= e(fmt_date($r['handover_date'])) ?></td>
                <td style="white-space:nowrap"><?= e(fmt_date($r['updated_at'] ?: $r['created_at'])) ?><br><span class="muted small"><?= e($r['creator']) ?></span></td>
            </tr>
        <?php endforeach; ?>
        </tbody>
    </table>
    </div>
    <?php if ($isAdmin): ?>
        <div class="btn-row responsive-cards" style="margin-top:0.6rem">
            <button type="submit" class="btn btn-secondary btn-sm">Ausgewählte archivieren</button>
        </div>
    </form>
    <?php endif; ?>
    <?php $pages = (int) ceil($total / $perPage); if ($pages > 1): ?>
        <div class="btn-row">
            <?php for ($i = 1; $i <= $pages; $i++): $qp = $_GET; $qp['page'] = $i; ?>
                <a class="btn btn-sm <?= $i === $page ? '' : 'btn-secondary' ?>" href="?<?= e(http_build_query($qp)) ?>"><?= $i ?></a>
            <?php endfor; ?>
        </div>
    <?php endif; ?>
</div>
