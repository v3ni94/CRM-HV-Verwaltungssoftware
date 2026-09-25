# M30 Übergabeprotokoll: U-Protokoll in den Bereich Makler überführen

Stand 25.09.2026, Entscheidung des Betreibers: Die eigenständige Anwendung U-Protokoll
(PHP, MariaDB, produktiv unter uprotokoll.muellerhv.de, Repository v3ni94/UProtkoll) wird als
Unterpunkt "Übergabeprotokoll" des Bereichs Makler in das CRM überführt. Alle Daten liegen
zentral in der CRM-Datenbank (PostgreSQL, Mandantentrennung per RLS), Dateien im
Objektspeicher der Dokumentenverwaltung (M6), Versand über die Zustellung (M23) und den
Postausgang mit Vier-Augen-Freigabe (M20).

## Zielbild

- Reiter Makler, Unterpunkt Übergabeprotokoll (Recht `contracts:read`, Schreiben mit
  `contracts:create`/`contracts:update`, wie die Anzeigen aus M28).
- Ein Protokoll entsteht aus Objekt und Einheit (Adresse, Etage und Einheit werden
  vorbelegt und bleiben als Momentaufnahme editierbar) oder ohne Objektbezug
  (Allgemeines Übergabeprotokoll). Optional wird eine Anzeige (Makler) verknüpft.
- Beteiligte sind Kontakte des CRM (Mieter, Eigentümer, Verwaltung, Zeugen); ein
  Beteiligter ohne Kontakt kann als Name erfasst werden.
- Zähler kommen aus den Zählerstammdaten des Objekts (Zählernummer, Art), die
  Ablesung im Protokoll ist ein eigener Stand mit Foto; freie Zähler bleiben möglich.
- Fotos, Anhänge, Unterschriften (PNG mit SHA-256) und das abgeschlossene PDF sind
  Dokumente der Dokumentenverwaltung, verknüpft mit Protokoll, Objekt und Einheit.
- Abschluss sperrt das Protokoll, erzeugt das PDF auf dem Briefbogen des Mandanten und
  bereitet die Zustellung an die Beteiligten vor. Nachträgliche Änderungen nur als neue
  Version mit Änderungsgrund; das Original bleibt unverändert.
- Kein inhaltliches Pflichtfeld; der Abschluss zeigt Hinweise (fehlende Adresse, keine
  Zähler, keine Unterschrift) und verlangt eine ausdrückliche Bestätigung.

## Abweichungen gegenüber der Einzelanwendung

| Thema | U-Protokoll (PHP) | CRM |
| --- | --- | --- |
| Versand nach Abschluss | automatisch per SMTP an alle Beteiligten | Zustellung wird vorbereitet (Dispatch mit E-Mail-Entwurf je Beteiligtem); Versand nur über den Postausgang mit Vier-Augen-Freigabe (M20-01, Regel 0.1.7 sinngemäß: keine unbeaufsichtigte Außenkommunikation) |
| Gehilfenzugang (Mieter füllt selbst aus) | eigene Benutzerrolle mit Passwort per E-Mail | Portalzugang (M21) mit Zugriffsrecht auf genau ein Protokoll. Die Portal-Oberfläche existiert noch nicht (apps/web-portal enthält nur den Health-Endpunkt); die Gehilfenfunktion ist deshalb Stufe 3 |
| Protokollnummer | UP-JJJJMMTT-NNN aus MAX+1 | UP-JJJJMMTT-NNN aus der Nummernfolge je Mandant und Tag (`number_sequence`, lückenlos innerhalb der Transaktion) |
| Dateiablage | lokal oder SFTP | Objektspeicher (S3, ADR 0005) über `documents.services.store_document` |
| Ortsermittlung per GPS | Browser-Geolocation mit Nominatim | nicht übernommen (externer Dienst, Datenschutz offen, M30-02) |
| Rollen | Admin, Mitarbeiter, Objektbetreuer, Nur Lesen, Gehilfe | Rechte-Matrix des CRM (Abschnitt 3.4) |

## Stufen

1. **Datenmodell und API** (umgesetzt 25.09.2026): Domäne `handover`, Tabellen
   `handover_protocol`, `handover_participant`, `handover_meter`, `handover_room`,
   `handover_defect`, `handover_key`, `handover_item`, `handover_note`,
   `handover_signature` (Migration 0043 mit RLS). Endpunkte unter `/api/v1/handover`:
   Liste, Anlage mit Vorbelegung, Feldänderung, Teildatensätze je Abschnitt, Fotos,
   Unterschriften, Hinweise, Abschluss mit PDF, neue Version, Stornierung, Archivierung,
   Zustellung vorbereiten.
2. **Oberfläche im CRM** (umgesetzt 25.09.2026): `/makler/uebergabe` (Liste mit Suche,
   Status, Archiv), `/makler/uebergabe/neu`, `/makler/uebergabe/[id]` (Abschnitte als
   Reiter, Speichern je Abschnitt, Fotos, Unterschriften per Canvas, Abschluss mit
   Hinweisen und Rückfrage, PDF, Versionen, Zustellung).
3. **Gehilfenzugang über das Portal** (offen, M30-01): Portalkonto für den Beteiligten,
   Zugriffsrecht `handover_protocol` mit Recht `edit` bis zum Abschluss, Portalseite zum
   Ausfüllen und Abschließen, Ablauf des Zugriffs nach Abschluss. Voraussetzung ist die
   Portal-Oberfläche (M21).
4. **Datenübernahme** aus U-Protokoll (offen, M30-03): Export der MariaDB und der Dateien,
   Import mit Testlauf wie M8 und M28 Stufe 4; Zuordnung zu Objekt, Einheit und Kontakt
   manuell im Erfassungsbogen. Danach Ablösung von uprotokoll.muellerhv.de.

## Dateien (Stufe 1 und 2)

- `apps/api/src/mhvp/handover/{models,routers,services,pdf,README}.py|md`
- `apps/api/alembic/versions/0043_handover.py`
- `apps/api/src/mhvp/documents/services.py` (verknüpfbare Entitäten `handover_*`)
- `apps/api/src/mhvp/models.py`, `apps/api/src/mhvp/main.py`
- `apps/api/tests/integration/test_m30_handover.py`
- `apps/web-crm/src/app/(app)/makler/uebergabe/**`, `apps/web-crm/src/components/handover/**`,
  BFF-Positivliste, `messages/de.json`, `messages/en.json`
- `docs/rules/M30-01.md`, `docs/OPEN_QUESTIONS.md`

## Gates

Keine Geldflüsse. Die Kautionsangaben (Betrag, IBAN) werden nur erfasst und im PDF
ausgegeben; sie erzeugen keine Forderung und keine Zahlung (G1, G2 unberührt). Die IBAN
wird formal geprüft (Mod 97), ein Prüfkennzeichen "IBAN geprüft" setzt nur die Verwaltung.
