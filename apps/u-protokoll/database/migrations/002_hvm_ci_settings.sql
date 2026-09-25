-- Migration 002: HVM-CI-Firmendaten in den Einstellungen nachziehen
-- (für Installationen, die bereits mit Seed 001 eingerichtet wurden)

INSERT INTO settings (setting_key, setting_value) VALUES
('company.name', 'Hausverwaltung Müller GmbH'),
('company.brand_footer', 'Eine Marke der Müller Holding Aktiengesellschaft'),
('company.street', 'Rheinpromenade 13, 40789 Monheim am Rhein'),
('company.register', 'Amtsgericht Düsseldorf, HRB 104762'),
('company.ceo', 'Geschäftsführer: Timo Müller'),
('company.website', 'www.muellerhv.de')
ON DUPLICATE KEY UPDATE setting_key = setting_key;
