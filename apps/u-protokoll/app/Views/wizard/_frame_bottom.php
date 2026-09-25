<?php
/**
 * Gemeinsamer Wizard-Fuß: Sticky-Navigation Zurück | Speichern | Weiter.
 * Erwartet: $protocol, $step, $steps; optional $nextLabel
 */
$stepKeys = array_keys($steps);
$index = (int) array_search($step, $stepKeys, true);
?>
</form>

<div class="wizard-nav">
    <?php if ($index > 0): ?>
        <button type="submit" form="wizard-form" name="_nav" value="back" class="btn btn-secondary">Zurück</button>
    <?php else: ?>
        <a class="btn btn-secondary" href="<?= e(url('/')) ?>">Übersicht</a>
    <?php endif; ?>
    <button type="submit" form="wizard-form" name="_nav" value="exit" class="btn btn-secondary">Speichern &amp; später</button>
    <?php if ($index < count($stepKeys) - 1): ?>
        <button type="submit" form="wizard-form" name="_nav" value="next" class="btn"><?= e($nextLabel ?? 'Weiter') ?></button>
    <?php else: ?>
        <button type="submit" form="wizard-form" name="_nav" value="goto:summary" class="btn">Zur Prüfung</button>
    <?php endif; ?>
</div>
