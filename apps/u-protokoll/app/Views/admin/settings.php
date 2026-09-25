<?php $s = fn(string $key, string $default = '') => e($settings[$key] ?? $default); ?>
<h1>Administration</h1>
<p><a href="<?= e(url('/admin/users')) ?>">Benutzerverwaltung</a> · <a href="<?= e(url('/admin/audit')) ?>">Audit-Log</a></p>

<form method="post" action="<?= e(url('/admin/settings')) ?>">
    <?= \App\Core\Csrf::field() ?>

    <div class="card">
        <h2>Allgemein</h2>
        <div class="grid grid-2">
            <div class="field"><label>Firmenname</label><input type="text" name="company_name" value="<?= $s('company.name') ?>"></div>
            <div class="field"><label>Markenhinweis / Footer</label><input type="text" name="company_brand_footer" value="<?= $s('company.brand_footer') ?>"></div>
            <div class="field"><label>Anschrift</label><input type="text" name="company_street" value="<?= $s('company.street') ?>"></div>
            <div class="field"><label>Telefon</label><input type="text" name="company_phone" value="<?= $s('company.phone') ?>"></div>
            <div class="field"><label>E-Mail</label><input type="text" name="company_email" value="<?= $s('company.email') ?>"></div>
            <div class="field"><label>Website</label><input type="text" name="company_website" value="<?= $s('company.website') ?>"></div>
            <div class="field"><label>Registerangaben (Fußzeile PDF)</label><input type="text" name="company_register" value="<?= $s('company.register') ?>"></div>
            <div class="field"><label>Geschäftsführung (Fußzeile PDF)</label><input type="text" name="company_ceo" value="<?= $s('company.ceo') ?>"></div>
            <div class="field"><label>Markenhinweis im PDF anzeigen (1/0)</label><input type="text" name="pdf_show_brand_footer" value="<?= $s('pdf.show_brand_footer', '1') ?>"></div>
        </div>
        <div class="field"><label>Bestätigungstext über den Unterschriften (Wizard und PDF)</label>
            <textarea name="pdf_signature_consent" rows="4"><?= $s('pdf.signature_consent') ?></textarea>
            <p class="muted small">Rechtlich relevanter Text. Änderungen bitte mit Rechtsanwalt oder Geschäftsführung abstimmen.</p></div>
    </div>

    <div class="card">
        <h2>E-Mail-Vorlage</h2>
        <div class="field"><label>Standard-Betreff</label><input type="text" name="email_default_subject" value="<?= $s('email.default_subject') ?>"></div>
        <div class="field"><label>Standard-Text</label><textarea name="email_default_body" rows="10"><?= $s('email.default_body') ?></textarea></div>
        <p class="muted small">Platzhalter: {{OBJECT_ADDRESS}}, {{HANDOVER_DATE}}, {{PROTOCOL_NUMBER}}</p>
    </div>

    <div class="card">
        <h2>Gehilfenzugänge und automatischer Versand</h2>
        <p class="muted small">
            Texte für die Zugangs-E-Mail an Gehilfen (Mieter, Eigentümer, Beauftragte) sowie für die
            Durchschrift, die nach dem Abschluss durch einen Gehilfen automatisch an alle Beteiligten
            mit hinterlegter E-Mail-Adresse versendet wird. Benutzername und Passwort werden vom System
            ergänzt und sind nicht Teil dieser Texte.
        </p>
        <?php $d = mail_text_defaults(); ?>
        <div class="field"><label>Betreff der Zugangs-E-Mail</label><input type="text" name="email_helper_subject" value="<?= $s('email.helper_subject', $d['email.helper_subject']) ?>"></div>
        <div class="field"><label>Einleitungstext der Zugangs-E-Mail</label><textarea name="email_helper_intro" rows="4"><?= $s('email.helper_intro', $d['email.helper_intro']) ?></textarea></div>
        <div class="field"><label>Datenschutzhinweis am Ende der Zugangs-E-Mail</label><textarea name="email_helper_privacy" rows="4"><?= $s('email.helper_privacy', $d['email.helper_privacy']) ?></textarea>
            <p class="muted small">Vorbelegter Text, bitte mit Datenschutzbeauftragtem oder Rechtsanwalt abstimmen. Leer lassen, um keinen Hinweis anzuhängen.</p></div>
        <div class="field"><label>Betreff der Durchschrift</label><input type="text" name="email_completion_subject" value="<?= $s('email.completion_subject', $d['email.completion_subject']) ?>"></div>
        <div class="field"><label>Text der Durchschrift</label><textarea name="email_completion_body" rows="8"><?= $s('email.completion_body', $d['email.completion_body']) ?></textarea></div>
        <p class="muted small">Platzhalter: {{OBJECT_ADDRESS}}, {{HANDOVER_DATE}}, {{PROTOCOL_NUMBER}}</p>
        <div class="grid grid-3">
            <div class="field"><label>Zugang des Gehilfen nach Abschluss gültig (Tage)</label>
                <input type="number" min="0" name="helper_access_days" value="<?= $s('helper.access_days', '30') ?>">
                <p class="muted small">0 = sofort beenden, leer = unbegrenzt. Betrifft Ansicht und PDF-Download nach dem Abschluss.</p></div>
            <div class="field"><label>Link Impressum (optional)</label><input type="url" name="legal_imprint_url" value="<?= $s('legal.imprint_url') ?>" placeholder="https://..."></div>
            <div class="field"><label>Link Datenschutzerklärung (optional)</label><input type="url" name="legal_privacy_url" value="<?= $s('legal.privacy_url') ?>" placeholder="https://..."></div>
        </div>
        <p class="muted small">Die Links erscheinen im Seitenfuß für alle Benutzer, insbesondere für externe Gehilfen.</p>
    </div>

    <div class="card">
        <h2>Uploads und Aufbewahrung</h2>
        <div class="grid grid-3">
            <div class="field"><label>Max. Bildkante (Pixel)</label><input type="number" name="upload_max_image_side" value="<?= $s('upload.max_image_side', '2800') ?>"></div>
            <div class="field"><label>JPEG-Qualität (1 bis 100)</label><input type="number" name="upload_jpeg_quality" value="<?= $s('upload.jpeg_quality', '82') ?>"></div>
            <div class="field"><label>Aufbewahrung vor Archivierung (Jahre, leer = keine Automatik)</label><input type="text" name="retention_archive_years" value="<?= $s('retention.archive_years') ?>"></div>
        </div>
        <p class="muted small">Eine automatische endgültige Löschung findet nicht statt; Löschungen erfolgen ausschließlich manuell nach definiertem Verfahren.</p>
    </div>

    <div class="card">
        <h2>SMTP / SFTP</h2>
        <p class="muted">Zugangsdaten für SMTP und SFTP werden aus Sicherheitsgründen ausschließlich in der Datei <code>.env</code> außerhalb des Webroots gepflegt (siehe Installationsanleitung), nicht in der Datenbank oder Oberfläche.</p>
    </div>

    <button type="submit" class="btn">Einstellungen speichern</button>
</form>
