-- U-Protokoll – Hausverwaltung Müller GmbH
-- Migration 005: Gehilfenzugänge (Mieter, Eigentümer, Gehilfe) und Objektbetreuer
--
-- Ein Gehilfe ist ein externer Benutzer, der ausschließlich die ihm
-- zugewiesenen Protokolle sehen, ausfüllen, unterschreiben und abschließen
-- kann. Die Zuweisung erfolgt über protocol_access.

SET NAMES utf8mb4;

ALTER TABLE users
    MODIFY COLUMN IF EXISTS role ENUM('admin','employee','caretaker','readonly','helper') NOT NULL DEFAULT 'employee';

ALTER TABLE user_invitations
    MODIFY COLUMN IF EXISTS role ENUM('admin','employee','caretaker','readonly') NOT NULL DEFAULT 'employee';

-- Art des Gehilfenzugangs (nur informativ, steuert Anrede und Anzeige)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS helper_type ENUM('helper','tenant','owner') NULL AFTER role;

CREATE TABLE IF NOT EXISTS protocol_access (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    protocol_id INT UNSIGNED NOT NULL,
    user_id     INT UNSIGNED NOT NULL,
    granted_by  INT UNSIGNED NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_protocol_access (protocol_id, user_id),
    KEY idx_protocol_access_user (user_id),
    CONSTRAINT fk_protocol_access_protocol FOREIGN KEY (protocol_id) REFERENCES protocols (id) ON DELETE CASCADE,
    CONSTRAINT fk_protocol_access_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Standardtexte für die Zugangs-E-Mail an Gehilfen
INSERT INTO settings (setting_key, setting_value) VALUES
('email.helper_subject', 'Ihr Zugang zum Übergabeprotokoll {{PROTOCOL_NUMBER}}'),
('email.helper_intro', 'Sie führen die Übergabe des Objektes {{OBJECT_ADDRESS}} eigenständig durch. Über den folgenden Zugang können Sie das Übergabeprotokoll digital ausfüllen, unterschreiben und abschließen.'),
('email.completion_subject', 'Übergabeprotokoll {{PROTOCOL_NUMBER}}, {{OBJECT_ADDRESS}}'),
('email.completion_body', 'Guten Tag,\n\nanbei erhalten Sie das abgeschlossene Übergabeprotokoll zum Objekt {{OBJECT_ADDRESS}} vom {{HANDOVER_DATE}} als PDF.\n\nMit freundlichen Grüßen\n\nHausverwaltung Müller GmbH')
ON DUPLICATE KEY UPDATE setting_key = setting_key;
