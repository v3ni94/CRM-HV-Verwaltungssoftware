<h1>Audit-Log</h1>
<p><a href="<?= e(url('/admin')) ?>">Zurück zu den Einstellungen</a></p>

<div class="card">
    <div class="table-wrap"><table class="list">
        <thead><tr><th>Zeitpunkt</th><th>Benutzer</th><th>Aktion</th><th>Datensatz</th><th>Protokoll</th><th>Alt</th><th>Neu</th><th>IP</th></tr></thead>
        <tbody>
        <?php foreach ($rows as $r): ?>
            <tr>
                <td style="white-space:nowrap"><?= e(fmt_datetime($r['created_at'])) ?></td>
                <td><?= e($r['username']) ?></td>
                <td><?= e($r['action']) ?></td>
                <td><?= e(trim(($r['entity'] ?? '') . ' #' . ($r['entity_id'] ?? ''))) ?></td>
                <td><?php if ($r['protocol_id']): ?><a href="<?= e(url('/protocols/' . $r['protocol_id'])) ?>">#<?= (int) $r['protocol_id'] ?></a><?php endif; ?></td>
                <td class="small muted"><?= e(mb_substr((string) $r['old_value'], 0, 80)) ?></td>
                <td class="small muted"><?= e(mb_substr((string) $r['new_value'], 0, 80)) ?></td>
                <td class="small muted"><?= e($r['ip_address']) ?></td>
            </tr>
        <?php endforeach; ?>
        </tbody>
    </table></div>
    <div class="btn-row">
        <?php $qp = $_GET; ?>
        <?php if ($page > 1): $qp['page'] = $page - 1; ?><a class="btn btn-sm btn-secondary" href="?<?= e(http_build_query($qp)) ?>">Neuere</a><?php endif; ?>
        <?php $qp['page'] = $page + 1; ?><a class="btn btn-sm btn-secondary" href="?<?= e(http_build_query($qp)) ?>">Ältere</a>
    </div>
</div>
