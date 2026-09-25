-- U-Protokoll – Beispieldaten
-- Passwort des Admin-Benutzers: bitte nach der Installation sofort ändern.
-- Hash unten entspricht dem Passwort "start1234!" (password_hash, bcrypt).

INSERT INTO branches (name) VALUES ('Zentrale'), ('NRW'), ('Berlin'), ('Bodensee');

INSERT INTO users (username, email, password_hash, first_name, last_name, role, branch_id)
VALUES
('admin', 'admin@muellerhv.de', '$2y$12$8pfrkkfcBvbf5XaXCTM3N..Ap81CmVdt6UQriTKsrk6msEjEyyuW2', 'System', 'Administrator', 'admin', 1),
('m.mustermann', 'm.mustermann@muellerhv.de', '$2y$12$8pfrkkfcBvbf5XaXCTM3N..Ap81CmVdt6UQriTKsrk6msEjEyyuW2', 'Max', 'Mustermann', 'employee', 1);

INSERT INTO settings (setting_key, setting_value) VALUES
('company.name', 'Hausverwaltung Müller GmbH'),
('company.brand_footer', 'Eine Marke der Müller Holding Aktiengesellschaft'),
('company.street', 'Rheinpromenade 13, 40789 Monheim am Rhein'),
('company.register', 'Amtsgericht Düsseldorf, HRB 104762'),
('company.ceo', 'Geschäftsführer: Timo Müller'),
('company.phone', ''),
('company.email', ''),
('company.website', 'www.muellerhv.de'),
('pdf.show_brand_footer', '1'),
('email.default_subject', 'Übergabeprotokoll {{PROTOCOL_NUMBER}}, {{OBJECT_ADDRESS}}'),
('email.default_body', "Sehr geehrte Damen und Herren,\n\nanbei erhalten Sie das Übergabeprotokoll zur Übergabe des Objekts {{OBJECT_ADDRESS}} vom {{HANDOVER_DATE}}.\n\nDie Protokollnummer lautet {{PROTOCOL_NUMBER}}.\n\nMit freundlichen Grüßen\n\nHausverwaltung Müller GmbH"),
('pdf.signature_consent', 'Mit ihrer Unterschrift bestätigen die Unterzeichnenden die Richtigkeit und Vollständigkeit der in diesem Protokoll festgehaltenen Angaben. Sie erklären sich zugleich damit einverstanden, dass dieses Protokoll einschließlich der zugehörigen Fotos und Unterlagen elektronisch verarbeitet und in digitaler Form für die Dauer der gesetzlichen Aufbewahrungs- und Verjährungsfristen gespeichert wird.'),
('upload.max_image_side', '2800'),
('upload.jpeg_quality', '82'),
('retention.archive_years', '')
ON DUPLICATE KEY UPDATE setting_key = setting_key;

INSERT INTO protocol_templates (name, definition) VALUES
('Standard Mietwohnung', '{"rooms":["Flur","Küche","Badezimmer","Wohnzimmer","Schlafzimmer","Keller"],"keys":["Haustürschlüssel","Wohnungstürschlüssel","Briefkastenschlüssel","Kellerschlüssel"],"meters":["Strom","Kaltwasser","Warmwasser","Heizungszähler"]}');
