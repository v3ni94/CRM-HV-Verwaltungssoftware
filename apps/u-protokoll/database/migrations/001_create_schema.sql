-- U-Protokoll – Hausverwaltung Müller GmbH
-- Migration 001: Vollständiges Basisschema
-- MariaDB 10.x, utf8mb4

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ---------------------------------------------------------------------------
-- Benutzer, Rollen, Niederlassungen
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS branches (
    id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name          VARCHAR(100) NOT NULL,
    is_active     TINYINT(1) NOT NULL DEFAULT 1,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS users (
    id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
    username      VARCHAR(80) NOT NULL,
    email         VARCHAR(190) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name    VARCHAR(100) NULL,
    last_name     VARCHAR(100) NULL,
    role          ENUM('admin','employee','readonly') NOT NULL DEFAULT 'employee',
    branch_id     INT UNSIGNED NULL,
    is_active     TINYINT(1) NOT NULL DEFAULT 1,
    failed_logins INT UNSIGNED NOT NULL DEFAULT 0,
    locked_until  DATETIME NULL,
    last_login_at DATETIME NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NULL ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_username (username),
    UNIQUE KEY uq_users_email (email),
    KEY idx_users_branch (branch_id),
    CONSTRAINT fk_users_branch FOREIGN KEY (branch_id) REFERENCES branches (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- Objekte / Einheiten (Objekt-Historie)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS properties (
    id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
    street         VARCHAR(190) NULL,
    house_number   VARCHAR(20) NULL,
    house_suffix   VARCHAR(20) NULL,
    postal_code    VARCHAR(10) NULL,
    city           VARCHAR(120) NULL,
    label          VARCHAR(190) NULL,
    internal_number VARCHAR(80) NULL,
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_properties_addr (postal_code, street(80), house_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS units (
    id           INT UNSIGNED NOT NULL AUTO_INCREMENT,
    property_id  INT UNSIGNED NOT NULL,
    label        VARCHAR(190) NULL,
    building     VARCHAR(80) NULL,
    floor        VARCHAR(40) NULL,
    unit_number  VARCHAR(40) NULL,
    position     VARCHAR(80) NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_units_property (property_id),
    CONSTRAINT fk_units_property FOREIGN KEY (property_id) REFERENCES properties (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- Protokolle
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS protocols (
    id                    INT UNSIGNED NOT NULL AUTO_INCREMENT,
    protocol_number       VARCHAR(20) NULL,             -- z. B. UP-000001, gesetzt nach INSERT
    protocol_type         ENUM('rental','sale','general') NOT NULL DEFAULT 'rental',
    status                ENUM('draft','in_progress','signature_pending','completed','sent','archived','cancelled','rework') NOT NULL DEFAULT 'draft',
    version               INT UNSIGNED NOT NULL DEFAULT 1,
    parent_protocol_id    INT UNSIGNED NULL,            -- bei neuer Version: Verweis auf Ursprung
    ticket_number         VARCHAR(80) NULL,
    case_number           VARCHAR(80) NULL,
    branch_id             INT UNSIGNED NULL,
    property_id           INT UNSIGNED NULL,
    unit_id               INT UNSIGNED NULL,
    -- Objektdaten denormalisiert am Protokoll (Stand zum Übergabezeitpunkt)
    street                VARCHAR(190) NULL,
    house_number          VARCHAR(20) NULL,
    house_suffix          VARCHAR(20) NULL,
    postal_code           VARCHAR(10) NULL,
    city                  VARCHAR(120) NULL,
    object_label          VARCHAR(190) NULL,
    building              VARCHAR(80) NULL,
    floor                 VARCHAR(40) NULL,
    unit_number           VARCHAR(40) NULL,
    unit_label            VARCHAR(190) NULL,
    unit_position         VARCHAR(80) NULL,
    internal_object_number VARCHAR(80) NULL,
    rental_contract_number VARCHAR(80) NULL,
    management_number     VARCHAR(80) NULL,
    reference_number      VARCHAR(80) NULL,
    handover_date         DATE NULL,
    handover_start        TIME NULL,
    handover_end          TIME NULL,
    handover_location     VARCHAR(190) NULL,
    hide_time_information TINYINT(1) NOT NULL DEFAULT 0,
    internal_contact      VARCHAR(190) NULL,
    internal_note         TEXT NULL,                    -- nie im Kunden-PDF
    general_note          TEXT NULL,
    current_step          VARCHAR(40) NOT NULL DEFAULT 'type',
    assigned_user_id      INT UNSIGNED NULL,
    created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by            INT UNSIGNED NULL,
    updated_at            DATETIME NULL ON UPDATE CURRENT_TIMESTAMP,
    updated_by            INT UNSIGNED NULL,
    completed_at          DATETIME NULL,
    completed_by          INT UNSIGNED NULL,
    archived_at           DATETIME NULL,
    change_reason         VARCHAR(255) NULL,            -- bei Folgeversionen
    PRIMARY KEY (id),
    UNIQUE KEY uq_protocols_number_version (protocol_number, version),
    KEY idx_protocols_status (status),
    KEY idx_protocols_type (protocol_type),
    KEY idx_protocols_ticket (ticket_number),
    KEY idx_protocols_handover_date (handover_date),
    KEY idx_protocols_postal (postal_code),
    KEY idx_protocols_created (created_at),
    KEY idx_protocols_property (property_id),
    KEY idx_protocols_parent (parent_protocol_id),
    CONSTRAINT fk_protocols_property FOREIGN KEY (property_id) REFERENCES properties (id) ON DELETE SET NULL,
    CONSTRAINT fk_protocols_unit FOREIGN KEY (unit_id) REFERENCES units (id) ON DELETE SET NULL,
    CONSTRAINT fk_protocols_branch FOREIGN KEY (branch_id) REFERENCES branches (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS protocol_participants (
    id           INT UNSIGNED NOT NULL AUTO_INCREMENT,
    protocol_id  INT UNSIGNED NOT NULL,
    role         VARCHAR(60) NOT NULL,        -- moving_out, moving_in, seller, buyer, handing_over, taking_over, management, broker, caretaker, proxy, witness, relative, expert, craftsman, other
    salutation   VARCHAR(30) NULL,
    first_name   VARCHAR(100) NULL,
    last_name    VARCHAR(100) NULL,
    company      VARCHAR(190) NULL,
    street       VARCHAR(190) NULL,
    house_number VARCHAR(20) NULL,
    postal_code  VARCHAR(10) NULL,
    city         VARCHAR(120) NULL,
    email        VARCHAR(190) NULL,
    phone        VARCHAR(60) NULL,
    mobile       VARCHAR(60) NULL,
    comment      VARCHAR(255) NULL,
    sort_order   INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_participants_protocol (protocol_id),
    KEY idx_participants_last_name (last_name),
    KEY idx_participants_email (email),
    CONSTRAINT fk_participants_protocol FOREIGN KEY (protocol_id) REFERENCES protocols (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS protocol_bank_details (
    id                INT UNSIGNED NOT NULL AUTO_INCREMENT,
    protocol_id       INT UNSIGNED NOT NULL,
    participant_id    INT UNSIGNED NULL,
    deposit_amount    DECIMAL(12,2) NULL,
    account_holder    VARCHAR(190) NULL,
    iban              VARCHAR(42) NULL,
    bic               VARCHAR(20) NULL,
    bank_name         VARCHAR(190) NULL,
    alt_payee         VARCHAR(190) NULL,
    comment           TEXT NULL,
    iban_by_tenant    TINYINT(1) NOT NULL DEFAULT 0,
    iban_verified     TINYINT(1) NOT NULL DEFAULT 0,
    deposit_separate  TINYINT(1) NOT NULL DEFAULT 0,
    no_bank_given     TINYINT(1) NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_bank_protocol (protocol_id),
    CONSTRAINT fk_bank_protocol FOREIGN KEY (protocol_id) REFERENCES protocols (id) ON DELETE CASCADE,
    CONSTRAINT fk_bank_participant FOREIGN KEY (participant_id) REFERENCES protocol_participants (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS protocol_meters (
    id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
    protocol_id   INT UNSIGNED NOT NULL,
    meter_type    VARCHAR(60) NULL,     -- electricity, gas, water, cold_water, hot_water, heating, heat_quantity, common_electricity, sub_meter, photovoltaic, other
    custom_type   VARCHAR(120) NULL,
    meter_number  VARCHAR(80) NULL,
    meter_value   VARCHAR(40) NULL,
    unit          VARCHAR(30) NULL,
    location      VARCHAR(190) NULL,
    reading_date  DATE NULL,
    reading_time  TIME NULL,
    comment       TEXT NULL,
    sort_order    INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_meters_protocol (protocol_id),
    CONSTRAINT fk_meters_protocol FOREIGN KEY (protocol_id) REFERENCES protocols (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS protocol_rooms (
    id               INT UNSIGNED NOT NULL AUTO_INCREMENT,
    protocol_id      INT UNSIGNED NOT NULL,
    room_type        VARCHAR(60) NULL,
    room_name        VARCHAR(190) NULL,
    condition_status ENUM('ok','defective','not_checked','not_accessible','not_included') NULL,
    comment          TEXT NULL,
    sort_order       INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_rooms_protocol (protocol_id),
    CONSTRAINT fk_rooms_protocol FOREIGN KEY (protocol_id) REFERENCES protocols (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS protocol_defects (
    id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
    protocol_id    INT UNSIGNED NOT NULL,
    room_id        INT UNSIGNED NULL,
    category       VARCHAR(60) NULL,
    title          VARCHAR(190) NULL,
    description    TEXT NULL,
    location       VARCHAR(190) NULL,
    priority       ENUM('info','low','medium','high','urgent') NULL,
    responsibility VARCHAR(190) NULL,
    defect_status  VARCHAR(60) NULL,   -- pre_existing, new, acknowledged, rejected, unclear
    comment        TEXT NULL,
    sort_order     INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_defects_protocol (protocol_id),
    KEY idx_defects_room (room_id),
    CONSTRAINT fk_defects_protocol FOREIGN KEY (protocol_id) REFERENCES protocols (id) ON DELETE CASCADE,
    CONSTRAINT fk_defects_room FOREIGN KEY (room_id) REFERENCES protocol_rooms (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS protocol_keys (
    id           INT UNSIGNED NOT NULL AUTO_INCREMENT,
    protocol_id  INT UNSIGNED NOT NULL,
    key_type     VARCHAR(60) NULL,
    custom_name  VARCHAR(190) NULL,
    quantity     INT NULL,
    key_number   VARCHAR(80) NULL,
    status       ENUM('handed_over','not_handed_over','to_follow') NULL,
    comment      TEXT NULL,
    sort_order   INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_keys_protocol (protocol_id),
    CONSTRAINT fk_keys_protocol FOREIGN KEY (protocol_id) REFERENCES protocols (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS protocol_items (
    id               INT UNSIGNED NOT NULL AUTO_INCREMENT,
    protocol_id      INT UNSIGNED NOT NULL,
    item_type        VARCHAR(60) NULL,
    name             VARCHAR(190) NULL,
    quantity         INT NULL,
    condition_status VARCHAR(120) NULL,
    comment          TEXT NULL,
    sort_order       INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_items_protocol (protocol_id),
    CONSTRAINT fk_items_protocol FOREIGN KEY (protocol_id) REFERENCES protocols (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS protocol_notes (
    id                INT UNSIGNED NOT NULL AUTO_INCREMENT,
    protocol_id       INT UNSIGNED NOT NULL,
    category          VARCHAR(60) NULL,    -- agreement, hint, defect, open_task, follow_up, payment, other
    text              TEXT NULL,
    responsible_party VARCHAR(190) NULL,
    due_date          DATE NULL,
    status            VARCHAR(60) NULL,
    comment           TEXT NULL,
    is_internal       TINYINT(1) NOT NULL DEFAULT 0,
    sort_order        INT NOT NULL DEFAULT 0,
    PRIMARY KEY (id),
    KEY idx_notes_protocol (protocol_id),
    CONSTRAINT fk_notes_protocol FOREIGN KEY (protocol_id) REFERENCES protocols (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS protocol_files (
    id                INT UNSIGNED NOT NULL AUTO_INCREMENT,
    protocol_id       INT UNSIGNED NOT NULL,
    room_id           INT UNSIGNED NULL,
    defect_id         INT UNSIGNED NULL,
    meter_id          INT UNSIGNED NULL,
    note_id           INT UNSIGNED NULL,
    item_id           INT UNSIGNED NULL,
    file_category     VARCHAR(60) NULL,    -- photo, meter_photo, room_photo, defect_photo, signature, pdf, attachment, document
    attachment_type   VARCHAR(60) NULL,    -- misc_photo, power_of_attorney, rental_contract, purchase_contract, key_receipt, invoice, damage_proof, other
    original_filename VARCHAR(255) NULL,
    stored_filename   VARCHAR(255) NOT NULL,
    storage_path      VARCHAR(500) NOT NULL,
    thumb_path        VARCHAR(500) NULL,
    mime_type         VARCHAR(120) NULL,
    file_size         BIGINT UNSIGNED NULL,
    sha256            CHAR(64) NULL,
    description       VARCHAR(255) NULL,
    is_internal       TINYINT(1) NOT NULL DEFAULT 0,
    sort_order        INT NOT NULL DEFAULT 0,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by        INT UNSIGNED NULL,
    PRIMARY KEY (id),
    KEY idx_files_protocol (protocol_id),
    KEY idx_files_room (room_id),
    KEY idx_files_defect (defect_id),
    KEY idx_files_meter (meter_id),
    CONSTRAINT fk_files_protocol FOREIGN KEY (protocol_id) REFERENCES protocols (id) ON DELETE CASCADE,
    CONSTRAINT fk_files_room FOREIGN KEY (room_id) REFERENCES protocol_rooms (id) ON DELETE SET NULL,
    CONSTRAINT fk_files_defect FOREIGN KEY (defect_id) REFERENCES protocol_defects (id) ON DELETE SET NULL,
    CONSTRAINT fk_files_meter FOREIGN KEY (meter_id) REFERENCES protocol_meters (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS protocol_signatures (
    id                INT UNSIGNED NOT NULL AUTO_INCREMENT,
    protocol_id       INT UNSIGNED NOT NULL,
    participant_id    INT UNSIGNED NULL,
    signer_name       VARCHAR(190) NULL,
    signer_role       VARCHAR(60) NULL,
    signature_file_id INT UNSIGNED NULL,
    sha256            CHAR(64) NULL,
    signed_at         DATETIME NULL,
    signed_location   VARCHAR(190) NULL,
    comment           VARCHAR(255) NULL,
    PRIMARY KEY (id),
    KEY idx_signatures_protocol (protocol_id),
    CONSTRAINT fk_signatures_protocol FOREIGN KEY (protocol_id) REFERENCES protocols (id) ON DELETE CASCADE,
    CONSTRAINT fk_signatures_file FOREIGN KEY (signature_file_id) REFERENCES protocol_files (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS protocol_versions (
    id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
    protocol_id    INT UNSIGNED NOT NULL,
    version_number INT UNSIGNED NOT NULL,
    pdf_file_id    INT UNSIGNED NULL,
    sha256         CHAR(64) NULL,
    change_reason  VARCHAR(255) NULL,
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by     INT UNSIGNED NULL,
    PRIMARY KEY (id),
    KEY idx_versions_protocol (protocol_id),
    CONSTRAINT fk_versions_protocol FOREIGN KEY (protocol_id) REFERENCES protocols (id) ON DELETE CASCADE,
    CONSTRAINT fk_versions_file FOREIGN KEY (pdf_file_id) REFERENCES protocol_files (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS protocol_emails (
    id                  INT UNSIGNED NOT NULL AUTO_INCREMENT,
    protocol_id         INT UNSIGNED NOT NULL,
    protocol_version_id INT UNSIGNED NULL,
    sender              VARCHAR(190) NULL,
    recipients          TEXT NULL,
    cc                  TEXT NULL,
    bcc                 TEXT NULL,
    subject             VARCHAR(255) NULL,
    body                TEXT NULL,
    status              ENUM('sent','failed') NOT NULL DEFAULT 'sent',
    smtp_response       TEXT NULL,
    error_message       TEXT NULL,
    sent_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_by             INT UNSIGNED NULL,
    PRIMARY KEY (id),
    KEY idx_emails_protocol (protocol_id),
    CONSTRAINT fk_emails_protocol FOREIGN KEY (protocol_id) REFERENCES protocols (id) ON DELETE CASCADE,
    CONSTRAINT fk_emails_version FOREIGN KEY (protocol_version_id) REFERENCES protocol_versions (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- Audit-Log und Einstellungen
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id     INT UNSIGNED NULL,
    username    VARCHAR(80) NULL,
    action      VARCHAR(80) NOT NULL,
    entity      VARCHAR(60) NULL,
    entity_id   INT UNSIGNED NULL,
    protocol_id INT UNSIGNED NULL,
    old_value   TEXT NULL,
    new_value   TEXT NULL,
    ip_address  VARCHAR(45) NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_audit_protocol (protocol_id),
    KEY idx_audit_created (created_at),
    KEY idx_audit_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS settings (
    setting_key   VARCHAR(120) NOT NULL,
    setting_value TEXT NULL,
    updated_at    DATETIME NULL ON UPDATE CURRENT_TIMESTAMP,
    updated_by    INT UNSIGNED NULL,
    PRIMARY KEY (setting_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS login_attempts (
    id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    ip_address VARCHAR(45) NOT NULL,
    username   VARCHAR(80) NULL,
    success    TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_login_ip_time (ip_address, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Vorlagen (architektonische Vorbereitung, Abschnitt 52)
CREATE TABLE IF NOT EXISTS protocol_templates (
    id         INT UNSIGNED NOT NULL AUTO_INCREMENT,
    name       VARCHAR(190) NOT NULL,
    definition TEXT NULL,     -- JSON: Räume, Schlüssel, Zählertypen
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INT UNSIGNED NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
