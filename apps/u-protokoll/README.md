# U-Protokoll

Digitales Übergabe- und Abnahmeprotokoll der **Hausverwaltung Müller GmbH**
(Eine Marke der Müller Holding Aktiengesellschaft).

Webanwendung für Wohnungsübergaben (Vermietung, Verkauf) und allgemeine
Übergabeprotokolle, optimiert für Smartphone und Tablet direkt vor Ort.
Geplante Subdomain: `u-protokoll.muellerhv.de` (bei einer IDN-Hauptdomain mit
Umlaut die Punycode-Schreibweise, z. B. `xn--…`, im DNS und im vHost verwenden).

## Funktionsumfang

- Mehrstufiger Wizard ohne inhaltliche Pflichtfelder, Bereiche überspringbar
- Autosave (Feldwechsel, Schrittwechsel, periodisch, Offline-Zwischenspeicher im Browser)
- Drei Protokollarten mit dynamischen Rollenbezeichnungen
- Beliebig viele Beteiligte, Zähler (mit Foto), Räume, Mängel (mit Fotos), Schlüssel, Gegenstände, Bemerkungen, Anhänge
- Kaution/IBAN mit rein formaler IBAN-Prüfung (Mod 97), niemals Pflicht
- Digitale Unterschriften (Canvas, Finger/Stift/Maus) als PNG mit SHA-256 und Zeitstempel
- Abschluss mit PDF-Erzeugung (Dompdf), Ablage im Dateispeicher, Versionierung; abgeschlossene Protokolle sind schreibgeschützt, Änderungen nur als neue Version mit Änderungsgrund
- E-Mail-Versand (PHPMailer/SMTP) an ausgewählte Beteiligte oder manuell, mit vollständiger Versandhistorie
- Trennung intern/extern: interne Notizen, interne Anhänge und Zeitinformationen erscheinen nie bzw. steuerbar im Kunden-PDF
- Dateispeicher lokal oder SFTP (phpseclib); MariaDB hält nur Metadaten (2-GB-Limit der DB)
- Bildpipeline: MIME-Prüfung, EXIF-Rotation, Skalierung, Neukodierung (entfernt GPS-/EXIF-Daten), Thumbnails
- Suche/Filter/Sortierung, CSV-Export, Kennzahlen, Duplizieren, Mängellisten-PDF, Druckansicht
- Benutzerverwaltung (Administrator, Mitarbeiter, Objektbetreuer, Nur Lesen, Gehilfe), Niederlassungen, Audit-Log, Login-Rate-Limiting
- Gehilfenzugänge für Mieter, Eigentümer und Beauftragte: eigenes Konto mit Passwort per E-Mail, Zugriff ausschließlich auf das zugewiesene Protokoll, Abschluss mit Rückfrage und automatischer Durchschrift an alle Beteiligten

### Gehilfenzugänge

Kann die Hausverwaltung bei einer Übergabe nicht anwesend sein, wird ein
Gehilfenzugang angelegt, in der Regel für den Mieter oder Eigentümer.

1. Anlage über die Protokollansicht (Abschnitt "Gehilfenzugänge") für ein
   bestehendes Protokoll oder über die Übersicht bzw. die Benutzerverwaltung
   mit automatisch erzeugtem Protokoll als Vorlage. Adresse, Einheit und
   Übergabedatum können dabei mitgegeben werden; optional wird der Gehilfe
   direkt als Beteiligter (einziehend oder ausziehend) eingetragen.
2. Der Gehilfe erhält eine E-Mail mit Login-Link, Benutzername, Passwort,
   kurzer Anleitung, Kontaktdaten der Verwaltung und Datenschutzhinweis.
   Scheitert der SMTP-Versand, werden die Zugangsdaten einmalig im
   Verwaltungsbereich angezeigt. Nach der Anmeldung kann jeder Benutzer sein
   Passwort über den Menüpunkt "Passwort" ändern.
3. Der Gehilfe sieht ausschließlich das zugewiesene Protokoll. Er kann es
   ausfüllen, Fotos hochladen, Unterschriften erfassen und abschließen. Nicht
   sichtbar oder gesperrt sind: Protokollübersicht, Anlage, Duplizieren,
   Versionen, Stornieren, Archivieren, CSV-Export, manueller E-Mail-Versand,
   Administration, die Schritte "Art" und "Intern", interne Notizen und
   Anhänge, das IBAN-Prüfkennzeichen sowie die von der Verwaltung vorbereiteten
   Nummern (Vorgang, Objekt, Mietvertrag, Verwaltung).
4. Abschluss: Der Gehilfe gelangt auf eine Bestätigungsseite mit den Hinweisen
   und der Frage, ob die Übergabe komplett fertig ist (Ja/Nein, unabhängig von
   JavaScript). Nach "Ja" wird das Protokoll festgeschrieben, das PDF erzeugt
   und automatisch an alle Beteiligten mit gültiger E-Mail-Adresse sowie an den
   Gehilfen versendet, jeder Empfänger in einer eigenen E-Mail. Fehlversuche
   stehen in der Versandhistorie. Die Hausverwaltung erhält eine interne
   Benachrichtigung (an den anlegenden Mitarbeiter, sonst an den Ersteller,
   sonst an die zentrale Adresse aus den Einstellungen). Der Gehilfe sieht eine
   Abschlussseite mit Versandnachweis, PDF-Ansicht und Download.
5. Schließt ein Mitarbeiter ein Protokoll mit zugewiesenen Gehilfen ab, wird
   die Durchschrift ebenfalls automatisch versendet.
6. Nach dem Abschluss endet der Zugriff des Gehilfen automatisch nach der in
   den Einstellungen hinterlegten Frist (Standard 30 Tage). Über "Zugang
   entziehen" endet der Zugriff sofort, das Benutzerkonto bleibt bestehen.
   Gesperrte Gehilfen (Aktiv = Nein) können sich nicht anmelden und erhalten
   keine Durchschrift.

Die Texte der Zugangs-E-Mail, des Datenschutzhinweises und der Durchschrift,
die Zugriffsfrist sowie Links zu Impressum und Datenschutzerklärung werden
unter Administration, Einstellungen gepflegt.

Die Rolle "Objektbetreuer" hat derzeit dieselben Rechte wie "Mitarbeiter" und
dient der Kennzeichnung; eine Einschränkung auf Niederlassungen oder Objekte
ist fachlich noch nicht festgelegt.

## Systemvoraussetzungen

- PHP 8.2 oder neuer mit `pdo_mysql`, `gd`, `fileinfo`, `mbstring`, empfohlen `exif`
- MariaDB 10.x
- Apache (mod_rewrite) oder nginx
- Composer (einmalig für die Installation der Bibliotheken)

## Installation

1. Dateien hochladen; der Document Root zeigt auf **`public/`**.
   `app/`, `config/`, `database/`, `storage/`, `vendor/` und `.env` liegen außerhalb des Webroots
   (bei klassischem Webhosting schützt zusätzlich die mitgelieferte `.htaccess` je Verzeichnis).
2. Abhängigkeiten installieren:
   ```bash
   composer install --no-dev
   ```
3. Konfiguration anlegen:
   ```bash
   cp .env.example .env
   # DB-, SMTP- und Storage-Zugangsdaten eintragen
   chmod 600 .env
   ```
   Zugangsdaten stehen ausschließlich in der `.env` (bzw. echten Environment-Variablen), nie im Code oder Repository.
4. Datenbank anlegen (utf8mb4) und Migrationen ausführen:
   ```bash
   php bin/migrate.php --seed
   ```
   Der Seed legt die Benutzer `admin` und `m.mustermann` mit dem Passwort `start1234!` an.
   **Beide Passwörter sofort nach dem ersten Login über die Benutzerverwaltung ändern.**
5. Schreibrechte für `storage/` (Logs, Cache, lokale Uploads) setzen.
6. Aufruf im Browser, Anmeldung, unter „Administration" Firmendaten und E-Mail-Vorlage prüfen.

### nginx-Beispiel

```nginx
server {
    server_name u-protokoll.muellerhv.de;
    root /var/www/u-protokoll/public;
    index index.php;
    location / { try_files $uri /index.php$is_args$args; }
    location ~ \.php$ {
        include fastcgi_params;
        fastcgi_pass unix:/run/php/php8.2-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
    }
    client_max_body_size 30m;
}
```

PHP-Einstellungen: `upload_max_filesize` und `post_max_size` mindestens 30M.

### Alternative ohne SSH (phpMyAdmin)

Auf Shared Hosting ohne Konsole werden die Dateien unter
`database/migrations/` in numerischer Reihenfolge (001 bis 006) über
phpMyAdmin importiert, anschließend einmalig `database/seeds/001_seed.sql`
(legt die ersten Benutzer und Einstellungen an, bestehende Einstellungen
bleiben unverändert). Bei späteren Updates nur die neuen Migrationsdateien
importieren. `php bin/migrate.php --seed` darf ebenfalls nur einmal auf einer
leeren Datenbank laufen; für Updates lautet der Aufruf `php bin/migrate.php`
ohne `--seed`. Die Migrationen verwenden MariaDB-Syntax
(`ADD COLUMN IF NOT EXISTS`), MySQL wird nicht unterstützt.

## Dateispeicher

- `STORAGE_DRIVER=local`: Ablage unter `STORAGE_BASE_PATH` (außerhalb des Webroots).
- `STORAGE_DRIVER=sftp`: Ablage auf dem konfigurierten SFTP-Server unter `SFTP_BASE_PATH`.

Struktur je Protokoll (ID mit führenden Nullen):

```
<basis>/2026/000001/photos|meters|rooms|defects|signatures|attachments|pdf/
```

Dateinamen sind zufällige Hex-Namen; Originalnamen stehen nur in der Datenbank.
Auslieferung erfolgt ausschließlich über die Anwendung nach Login (kein Direktzugriff).

## Backup und Wiederherstellung

Datenbank und Dateispeicher werden unabhängig gesichert:

```bash
# MariaDB
mysqldump --single-transaction --routines u_protokoll | gzip > backup/u_protokoll_$(date +%F).sql.gz

# Dateispeicher (lokal)
tar czf backup/uploads_$(date +%F).tar.gz -C /var/www/u-protokoll/storage uploads

# Dateispeicher (SFTP) – vom Storage-Server aus oder per rsync/sftp spiegeln
rsync -a sftpuser@storage:/u-protokoll/ backup/u-protokoll-files/
```

Zusätzlich sichern: `.env` (enthält alle Zugangsdaten) und ggf. vHost-Konfiguration.

Wiederherstellung: Datenbank einspielen (`gunzip -c … | mysql u_protokoll`),
Dateien an den in `protocol_files.storage_path` erwarteten Ort zurücklegen,
`.env` wiederherstellen, `composer install --no-dev` ausführen.

## Sicherheit

- PDO Prepared Statements durchgehend, keine dynamische SQL-Interpolation von Nutzereingaben
- CSRF-Token auf allen POST-Routen, XSS-Schutz über konsequentes `e()`-Escaping
- Sessions: HTTPOnly, Secure (bei HTTPS), SameSite=Lax, Session-Fixation-Schutz
- `password_hash()`/`password_verify()` mit automatischem Rehash
- Login-Rate-Limiting je IP und temporäre Kontosperre nach Fehlversuchen
- Uploads: serverseitige MIME-Prüfung (finfo), Whitelist (JPG/PNG/WEBP/HEIC/PDF), Größenlimit,
  zufällige Dateinamen, keine ausführbaren Dateien, Ablage außerhalb des Webroots,
  Neukodierung von Bildern entfernt EXIF-/GPS-Metadaten
- Fehler werden nie öffentlich ausgegeben; Details stehen in `storage/logs/`
- Audit-Log ist aus der Anwendung heraus nicht änderbar (nur INSERT)

## Fehler- und Logging-Konzept

- Öffentliche Ausgabe bei Fehlern: „Es ist ein technischer Fehler aufgetreten."
- Technische Details: `storage/logs/app-JJJJ-MM-TT.log` und `storage/logs/php-error.log`
- Fehlgeschlagene E-Mail-Versände stehen zusätzlich mit SMTP-Fehlertext in der Versandhistorie
- Fehlgeschlagene Uploads werden je Datei gemeldet („erneut versuchen"), ohne Datenverlust im Protokoll

## Datenschutz

- Interne Felder (`is_internal`, interne Bemerkungen) erscheinen nie im Kunden-PDF
- Zeitinformationen können je Protokoll aus der Ausgabe ausgeblendet werden (interne Speicherung bleibt)
- Archivierung und Aufbewahrung administrativ konfigurierbar; keine automatische endgültige Löschung
- GPS-/EXIF-Metadaten werden bei der Bildverarbeitung entfernt

## Architektur

```
/app
    /Controllers     HTTP-Endpunkte (Auth, Dashboard, Protocol, Wizard, Records, Files, Signaturen, PDF, E-Mail, Helper, Invite, Admin)
    /Core            Router, DB (PDO), Auth, CSRF, Views, Config/.env, Logger, Audit
    /Repositories    ProtocolRepository (Whitelists, Versionierung, Duplizieren)
    /Services        FileService, ImageService, PdfService, MailService, HelperService, Storage (local/SFTP)
    /Views           PHP-Templates (Layout, Wizard, PDF)
/bin                 migrate.php
/config              (reserviert; Laufzeitkonfiguration kommt aus .env und Tabelle settings)
/database            /migrations, /seeds
/public              index.php (Front Controller), /assets
/storage             /logs, /cache, /uploads (lokaler Storage)
```

Geschäftslogik liegt in Services/Repositories, nicht in Templates; interne IDs
sind sauber getrennt (sichtbare Protokollnummer `UP-JJJJMMTT-NNN` (laufende Nummer je Tag, z. B. `UP-20260903-001`; Altbestand `UP-000001`) neben der DB-ID).
Eine spätere REST-API kann auf den Repositories/Services aufsetzen; Vorlagen
(`protocol_templates`), Niederlassungen und `properties`/`units` (Objekt-Historie)
sind im Schema bereits vorbereitet, ebenso eine spätere PWA-Erweiterung
(Autosave arbeitet bereits mit lokalem Browser-Zwischenspeicher bei Netzausfall).
