<?php /** @var array $rows; @var int $open; @var callable $expired */ ?>
<h1><?= count($rows) > 1 ? 'Meine Übergaben' : 'Meine Übergabe' ?></h1>

<?php if ($rows === []): ?>
    <div class="card">
        <p>Für Ihren Zugang ist derzeit kein Protokoll freigegeben. Bitte wenden Sie sich an die Hausverwaltung Müller GmbH<?= company_contact_line() !== '' ? ' (' . e(company_contact_line()) . ')' : '' ?>.</p>
    </div>
<?php else: ?>
    <div class="card">
        <p class="muted small" style="margin-top:0">
            <?php if ($open > 1): ?>
                Sie können die folgenden Protokolle ausfüllen, die Unterschriften erfassen und die jeweilige Übergabe abschließen.
            <?php elseif ($open === 1): ?>
                Sie können das folgende Protokoll ausfüllen, die Unterschriften erfassen und die Übergabe abschließen.
            <?php else: ?>
                Für Ihren Zugang ist derzeit keine offene Übergabe vorhanden. Abgeschlossene Protokolle können Sie unten ansehen, solange Ihr Zugang gültig ist.
            <?php endif; ?>
            Nach einem Abschluss erhalten alle Beteiligten mit hinterlegter E-Mail-Adresse das Protokoll automatisch als PDF.
        </p>
    </div>

    <?php foreach ($rows as $r): ?>
        <?php
        $locked = \App\Repositories\ProtocolRepository::isLocked($r);
        $finalized = protocol_is_finalized($r);
        $isExpired = $expired($r);
        ?>
        <div class="card">
            <div class="section-head">
                <h2><?= e($r['protocol_number'] ?: (string) $r['id']) ?></h2>
                <?php if ($isExpired): ?>
                    <span class="badge badge-cancelled">Zugang abgelaufen</span>
                <?php elseif ($locked && !$finalized): ?>
                    <span class="badge badge-cancelled">Geschlossen</span>
                <?php elseif ($finalized): ?>
                    <span class="badge badge-completed">Abgeschlossen</span>
                <?php else: ?>
                    <?= status_badge($r['status']) ?>
                <?php endif; ?>
            </div>
            <dl class="kv">
                <dt>Objekt</dt><dd><?= e(protocol_address($r)) ?: '<span class="muted">Noch nicht erfasst</span>' ?></dd>
                <dt>Einheit</dt><dd><?= e(trim((string) ($r['unit_number'] ?? '') . ' ' . (string) ($r['unit_position'] ?? ''))) ?: '<span class="muted">Keine Angabe</span>' ?></dd>
                <dt>Übergabedatum</dt><dd><?= e(fmt_date($r['handover_date'])) ?: '<span class="muted">Keine Angabe</span>' ?></dd>
                <?php if (!empty($r['valid_until']) && !$isExpired): ?>
                    <dt>Zugang gültig bis</dt><dd><?= e(fmt_datetime($r['valid_until'])) ?></dd>
                <?php endif; ?>
            </dl>
            <div class="btn-row">
                <?php if ($isExpired): ?>
                    <p class="muted small" style="margin:0">Ihr Zugang zu diesem Protokoll ist abgelaufen. Bei Fragen wenden Sie sich an die Hausverwaltung.</p>
                <?php elseif ($finalized): ?>
                    <a class="btn" href="<?= e(url('/protocols/' . $r['id'] . '/done')) ?>">Abgeschlossenes Protokoll ansehen</a>
                    <a class="btn btn-secondary" href="<?= e(url('/protocols/' . $r['id'] . '/pdf')) ?>" target="_blank" rel="noopener">PDF anzeigen</a>
                <?php elseif ($locked): ?>
                    <p class="muted small" style="margin:0">Dieses Protokoll wurde von der Hausverwaltung geschlossen und kann nicht mehr bearbeitet werden.</p>
                <?php else: ?>
                    <a class="btn btn-block" href="<?= e(url('/protocols/' . $r['id'] . '/wizard/' . ($r['current_step'] ?: 'object'))) ?>">Protokoll ausfüllen</a>
                <?php endif; ?>
            </div>
        </div>
    <?php endforeach; ?>
<?php endif; ?>
