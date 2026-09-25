-- Migration 003: Einladungen für neue Benutzer (Mitarbeiter einladen)

CREATE TABLE IF NOT EXISTS user_invitations (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT,
    email       VARCHAR(190) NOT NULL,
    first_name  VARCHAR(100) NULL,
    last_name   VARCHAR(100) NULL,
    role        ENUM('admin','employee','readonly') NOT NULL DEFAULT 'employee',
    branch_id   INT UNSIGNED NULL,
    token_hash  CHAR(64) NOT NULL,
    expires_at  DATETIME NOT NULL,
    accepted_at DATETIME NULL,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by  INT UNSIGNED NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_invitations_token (token_hash),
    KEY idx_invitations_email (email),
    CONSTRAINT fk_invitations_branch FOREIGN KEY (branch_id) REFERENCES branches (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
