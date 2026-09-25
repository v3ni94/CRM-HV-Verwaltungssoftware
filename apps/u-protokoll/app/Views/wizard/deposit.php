<?php
$b = $bank ?? [];
$base = url('/protocols/' . $protocol['id']);
require __DIR__ . '/_frame_top.php';
?>

<div class="card">
    <h2>Kaution / Bankverbindung <span class="muted small">(optional)</span></h2>
    <div data-record-container data-entity="bank" data-base="<?= e($base) ?>">
        <div class="record-card" data-record-id="<?= (int) ($b['id'] ?? 0) ?: '' ?>">
            <div class="grid grid-3">
                <div class="field"><label>Kautionsbetrag (EUR)</label>
                    <input type="text" inputmode="decimal" name="deposit_amount" value="<?= e($b['deposit_amount'] ?? '') ?>" placeholder="z. B. 1.500,00"></div>
                <div class="field"><label>Kontoinhaber</label><input type="text" name="account_holder" value="<?= e($b['account_holder'] ?? '') ?>"></div>
                <div class="field"><label>IBAN für Kautionsrückzahlung</label><input type="text" name="iban" value="<?= e($b['iban'] ?? '') ?>" autocomplete="off" spellcheck="false"></div>
                <div class="field"><label>BIC</label><input type="text" name="bic" value="<?= e($b['bic'] ?? '') ?>"></div>
                <div class="field"><label>Bank</label><input type="text" name="bank_name" value="<?= e($b['bank_name'] ?? '') ?>"></div>
                <div class="field"><label>Abweichender Zahlungsempfänger</label><input type="text" name="alt_payee" value="<?= e($b['alt_payee'] ?? '') ?>"></div>
            </div>
            <div class="field"><label>Bemerkung zur Kaution</label><textarea name="comment"><?= e($b['comment'] ?? '') ?></textarea></div>
            <div class="grid grid-2">
                <div class="checkbox-row"><input type="checkbox" id="iban_by_tenant" name="iban_by_tenant" value="1" <?= !empty($b['iban_by_tenant']) ? 'checked' : '' ?>><label for="iban_by_tenant">IBAN wurde vom Mieter angegeben</label></div>
                <?php if (!\App\Core\Auth::isHelper()): ?>
                <div class="checkbox-row"><input type="checkbox" id="iban_verified" name="iban_verified" value="1" <?= !empty($b['iban_verified']) ? 'checked' : '' ?>><label for="iban_verified">IBAN wurde geprüft</label></div>
                <?php endif; ?>
                <div class="checkbox-row"><input type="checkbox" id="deposit_separate" name="deposit_separate" value="1" <?= !empty($b['deposit_separate']) ? 'checked' : '' ?>><label for="deposit_separate">Kautionsabrechnung erfolgt separat</label></div>
                <div class="checkbox-row"><input type="checkbox" id="no_bank_given" name="no_bank_given" value="1" <?= !empty($b['no_bank_given']) ? 'checked' : '' ?>><label for="no_bank_given">Keine Bankverbindung angegeben</label></div>
            </div>
            <p class="muted small">Die IBAN wird nur formal geprüft. Das Speichern ist auch ohne oder mit unvollständigen Angaben möglich.</p>
        </div>
    </div>
</div>

<?php require __DIR__ . '/_frame_bottom.php'; ?>
