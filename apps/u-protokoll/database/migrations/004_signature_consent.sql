-- Migration 004: Bestätigungstext über den Unterschriften (administrativ änderbar).
-- Ein bereits angepasster Text wird nicht überschrieben.

INSERT INTO settings (setting_key, setting_value) VALUES
('pdf.signature_consent', 'Mit ihrer Unterschrift bestätigen die Unterzeichnenden die Richtigkeit und Vollständigkeit der in diesem Protokoll festgehaltenen Angaben. Sie erklären sich zugleich damit einverstanden, dass dieses Protokoll einschließlich der zugehörigen Fotos und Unterlagen elektronisch verarbeitet und in digitaler Form für die Dauer der gesetzlichen Aufbewahrungs- und Verjährungsfristen gespeichert wird.')
ON DUPLICATE KEY UPDATE setting_key = setting_key;
