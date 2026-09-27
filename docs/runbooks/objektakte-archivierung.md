# Archivierung und Abschaltung des objektakte-Stacks (M35 Stufe 6, Entwurf)

Stand 27.09.2026, Entwurf. Gilt für den Container-Stack `objektakte-*` (Django, MariaDB, Redis,
Worker OCR/NLP/IO, Datenverzeichnis `/data`, Domain `uebernahme.muellerhv.de`) nach Abschluss
des Parallelbetriebs (M35 Stufe 5). Aufbewahrungsfrist und Ablageort des Archivs sind
Betreiberentscheidung (`docs/OPEN_QUESTIONS.md` M35-07); dieses Runbook beschreibt den
technischen Ablauf, der unabhängig von dieser Entscheidung gleich bleibt. Jeder Schritt ist für
sich rückholbar, bis Schritt 5 ausgeführt ist.

Verantwortlich: Betreiber (Timo Müller). Freigabe der Abschaltung durch die Geschäftsführung,
da Dokumentenbestand und Aufbewahrungspflichten betroffen sind (Regel 0.1.7).

## 0. Voraussetzungen (vor Schritt 1 prüfen)

| Nr. | Prüfung | Nachweis |
|-----|---------|----------|
| V1 | Abgleichbericht objektakte gegen CRM an fünf aufeinanderfolgenden Werktagen ohne ungeklärte Differenz | CRM, Objektakte, Abschnitt "Abgleich objektakte gegen CRM" (`GET /api/v1/objektakte/reconciliation`), Berichte als JSON ablegen |
| V2 | Letzter Differenzimport erfolgreich, Wasserstand jünger als die letzte Änderung in objektakte | CRM, Einstellungen, Objektakte, Synchronisationsstand |
| V3 | Keine offenen Übernahmefälle mit laufendem `takeover_from/to`-Zeitraum, die nur in objektakte beschreibbar sind | objektakte, Objektliste; CRM Review-Center (offene Fälle) |
| V4 | Vorschaubild-Übernahme abgeschlossen oder bewusst als "Neu rendern" entschieden (M35-02) | CRM `GET /api/v1/objektakte/previews/import`, Lauf `done`, `failed = 0` |
| V5 | Schlüsselübergabe abgeschlossen oder bewusst verworfen (M35-03); Rekey-Protokoll ohne `error`/`mismatch` abgelegt | Protokolldatei des Laufs `python -m mhvp.objektakte.rekey` (ohne Klartext) |
| V6 | Alle objektakte-Benutzer im CRM eingeladen oder bewusst nicht übernommen | Importdetail `user_mapping`, Regel M35-03 |
| V7 | Google-Drive-Anbindung des CRM (`ablage@muellerhv.de`) mit eigenem oder übernommenem Token funktionsfähig | Einstellungen, DMS, Download eines migrierten Dokuments |

## 1. Einfrieren (Tag 0)

```
cd /opt/objektakte
docker compose stop worker-ocr worker-nlp worker-io beat
docker compose exec web python manage.py shell -c "from apps.config import store; store.set('sync.crm_uploads_enabled', False); store.set('security.read_only', True)"
```

Ergebnis: Oberfläche und Lese-API laufen weiter (Abgleich und Nachzügler-Import möglich), keine
Verarbeitung, keine Drive-Schreibzugriffe mehr. Falls der Schlüssel `security.read_only` in der
eingesetzten objektakte-Version nicht existiert, stattdessen den Reverse Proxy auf GET
beschränken. Die Uploads aus dem CRM (`objektakte_upload_enabled`) im CRM ausschalten.

## 2. Letzter Differenzimport und finale Prüfsumme (Tag 0)

1. Vollständigen Export erzeugen:
   `docker compose exec db mysqldump --single-transaction --hex-blob objektakte > /data/objektakte-export/final-$(date +%F).sql`
2. Export im CRM einspielen (Einstellungen, Objektakte, Synchronisationsstand, "Export
   hochladen") oder auf den hinterlegten Pfad kopieren und "Jetzt abgleichen".
3. Abgleichbericht laden; erwartet `ok = true` (keine fehlenden Dokumente, keine abweichenden
   Prüfsummen außer Platzhaltern ohne Hash).
4. Finale Kennzahlen beidseitig festhalten und als Datei zum Archiv legen: Anzahl Dokumente,
   Summe `size_bytes`, Anzahl offener Review-Fälle, Anzahl Objekte, Anzahl Einheiten,
   Anzahl Eigentümer/Mieter. objektakte: `manage.py status_report` oder SQL `SELECT COUNT(*),
   SUM(size_bytes) FROM documents_document`; CRM: Abgleichbericht `totals`.

## 3. Archiv erstellen (Tag 0 bis 1)

Das Archiv besteht aus drei Teilen; alle drei werden mit einer Prüfsummendatei versehen und
verschlüsselt abgelegt.

| Teil | Inhalt | Befehl (Beispiel) |
|------|--------|-------------------|
| A Datenbank | vollständiger Dump inkl. Audit (`audit_events`, `iban_access_logs`), KI-Protokoll, Review-Historie | `mysqldump --single-transaction --hex-blob --routines objektakte \| gzip > objektakte-db-$(date +%F).sql.gz` |
| B Datenverzeichnis | `/data/previews`, `/data/ocr-cache`, `/data/models`, `/data/imports`, `/data/exports`, `/data/backup`; **nicht** `/data/work` und `/data/transit` (Arbeitsflächen ohne Aufbewahrungswert, vor dem Packen leeren) | `tar --exclude=./work --exclude=./transit -czf objektakte-data-$(date +%F).tar.gz -C /data .` |
| C Konfiguration | Compose-Dateien, `.env` ohne Secrets, Regelwerk `db/seeds/rules`, letzte Version des Repositories (`git rev-parse HEAD`), Docker-Image-Digests | `docker compose config > compose-resolved.yml; docker images --digests` |

Prüfsummen und Verschlüsselung:

```
sha256sum objektakte-db-*.sql.gz objektakte-data-*.tar.gz compose-resolved.yml > SHA256SUMS
gpg --encrypt --recipient <Archivschlüssel der Geschäftsführung> objektakte-db-*.sql.gz
gpg --encrypt --recipient <Archivschlüssel der Geschäftsführung> objektakte-data-*.tar.gz
```

Die Feldschlüssel (`FIELD_KEYS`: `iban`, `iban_hmac`, `token`, `totp`) werden **nicht** in das
Archiv gelegt. Sie werden getrennt im Passwort-Tresor der Geschäftsführung verwahrt, solange
das Archiv aufbewahrt wird (ohne sie sind `iban_encrypted` und die OAuth-Tokens im Dump nicht
lesbar; das ist beabsichtigt, das Archiv allein gibt keinen Klartext preis). Nach Ablauf der
Aufbewahrungsfrist werden Archiv und Feldschlüssel gemeinsam gelöscht.

Die Dokumentoriginale liegen nicht im Archiv: sie bleiben in Google Drive
(`ablage@muellerhv.de`) und sind über `Document.storage_ref` aus dem CRM erreichbar. Das Archiv
sichert Metadaten, Historie, OCR-Text, Vorschauen und Modell.

## 4. Rücksicherbarkeit prüfen (Tag 1)

Stichprobe auf einem getrennten Host oder in einem temporären Compose-Projekt:

```
gpg --decrypt objektakte-db-<datum>.sql.gz.gpg | gunzip | mysql -u root objektakte_restore
mysql objektakte_restore -e "SELECT COUNT(*), SUM(size_bytes) FROM documents_document"
tar -tzf <(gpg --decrypt objektakte-data-<datum>.tar.gz.gpg) | head
```

Die Zahlen müssen mit den finalen Kennzahlen aus Schritt 2 übereinstimmen. Ergebnis mit Datum
und Prüfer im Archivprotokoll festhalten. Ohne bestandene Stichprobe kein Schritt 5.

## 5. Abschalten (nach Freigabe)

```
docker compose down          # Container entfernen, Volumes bleiben
# DNS: uebernahme.muellerhv.de auf eine Hinweisseite oder das CRM umstellen
# CRM: MHVP_OBJEKTAKTE_API_URL, _TOKEN, _TENANT, _WEBHOOK_SECRET leeren, Container neu starten
```

Danach zeigt der DMS-Reiter im CRM nur noch CRM-Dokumente (Statusanzeige "objektakte ist nicht
angebunden" ist der erwartete Zustand). Der Differenzimport wird je Mandant ausgeschaltet.

Erst nach der in M35-07 festgelegten Karenzzeit (Vorschlag: 30 Tage nach Schritt 5, in denen
das Archiv geprüft im Zugriff war und keine Rückfrage kam):

```
docker volume rm objektakte_db objektakte_redis
rm -rf /data/work /data/transit
```

`/data` selbst bleibt bis zum Ende der Aufbewahrungsfrist auf dem Server oder wandert an den
in M35-07 festgelegten Ablageort (Objektspeicher, siehe `docs/runbooks/objektspeicher-ionos-s3.md`,
Bucket mit Object Lock, oder Offline-Datenträger im Tresor).

## 6. Aufbewahrung und Löschung (offen, M35-07)

| Frage | Vorschlag (zu entscheiden) |
|-------|----------------------------|
| Frist | Orientierung an der längsten Aufbewahrungsfrist der enthaltenen Unterlagen; Einschätzung, durch Steuerberater zu bestätigen: zehn Jahre ab Ende des Kalenderjahres der Abschaltung, da das Archiv Buchungsbelege referenziert. Keine eigene Rechtsgrundlage in diesem Runbook. |
| Ort | Verschlüsselt im Objektspeicher (Object Lock, Aufbewahrungsklasse) plus eine Offline-Kopie |
| Zugriff | Zwei Personen (Geschäftsführung, Datenschutz); jeder Zugriff wird im Archivprotokoll vermerkt |
| Löschung | Nach Fristablauf Archiv und Feldschlüssel gemeinsam, Löschprotokoll mit Datum und Prüfsummen |

## Rückholung

Bis Schritt 5: `docker compose start` stellt den Stack her. Nach Schritt 5 bis zur Löschung der
Volumes: `docker compose up -d` mit den archivierten Compose-Dateien und Images. Nach Löschung
der Volumes: Wiederherstellung aus Teil A und B des Archivs nach Schritt 4, Feldschlüssel aus
dem Tresor.
