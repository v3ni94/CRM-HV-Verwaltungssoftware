-- U-Protokoll – Hausverwaltung Müller GmbH
-- Migration 006: Gültigkeitsende für Gehilfenzugänge, Datenschutzhinweis,
-- rechtliche Links, Korrektur des Standardbetreffs

SET NAMES utf8mb4;

-- Zugriff eines Gehilfen endet nach Abschluss automatisch (Frist in Tagen einstellbar)
ALTER TABLE protocol_access
    ADD COLUMN IF NOT EXISTS valid_until DATETIME NULL AFTER granted_by;

INSERT INTO settings (setting_key, setting_value) VALUES
('helper.access_days', '30'),
('email.helper_privacy', 'Hinweis zum Datenschutz: Ihre Angaben werden ausschließlich zur Durchführung und Dokumentation der Übergabe verarbeitet und für die Dauer der gesetzlichen Aufbewahrungsfristen gespeichert. Verantwortlich ist die Hausverwaltung Müller GmbH. Ihr Zugang wird nach Abschluss der Übergabe zeitlich begrenzt.'),
('legal.privacy_url', ''),
('legal.imprint_url', '')
ON DUPLICATE KEY UPDATE setting_key = setting_key;

-- Standardbetreff ohne Gedankenstrich, nur wenn er noch unverändert ist
UPDATE settings SET setting_value = 'Übergabeprotokoll {{PROTOCOL_NUMBER}}, {{OBJECT_ADDRESS}}'
WHERE setting_key = 'email.default_subject'
  AND setting_value = 'Übergabeprotokoll {{PROTOCOL_NUMBER}} – {{OBJECT_ADDRESS}}';
