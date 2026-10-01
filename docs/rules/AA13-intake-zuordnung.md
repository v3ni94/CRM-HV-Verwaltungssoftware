# AA13 Dokumenteingang: Zuordnung, Folgevorschläge, Direktablage, DocumentStore

| Field | Content |
| --- | --- |
| ID | `AA13` (GA10-01 bis GA10-05) |
| Title | Zuordnung über Einheit, Vertrag, IBAN und Kundennummer; Folgevorschläge nach der Ablage; Direktablage hinter Mandantenschalter; vollständiges DocumentStore-Protokoll; Rolle und Feldübernahme in der Kontaktvorschau |
| Scope | `mhvp.documents.intake`, `intake_followup`, `intake_routers`, `dms`; `mhvp.ai.imports.apply_contacts`; CRM `ContactProposal`; alle Mandanten; keine Migration (0315 ist ein Platzhalter) |
| Source status | Fachliche Umsetzung nach 11.2, 11.4 und 10.1 Schritt 4. Keine Rechtsnorm zitiert |
| Acceptance case | `tests/integration/test_aa13_intake_match.py`, `tests/unit/test_aa13_document_store.py`, `ContactProposal.test.tsx` |
| Change reason | Lückenliste 01.10.2026, Welle 12, Paket AA13 |

## Regeln

- Einheit: Hinweiswort (Einheit, WE, Whg, Wohnung, Top) mit Nummer im Text, nur innerhalb der
  Objektkandidaten ab Konfidenz 0,7. Ohne Objekt gibt es keine Einheit.
- Vertrag: Verträge der erkannten Einheit, die am Dokumentdatum (Anlagedatum) gültig sind
  (Beginn bis Ende, offenes Ende erlaubt). Mehrere gültige Verträge werden alle angeboten.
- Kontakt: IBAN über den Fingerabdruck (keine Entschlüsselung, Konfidenz 0,95), Kundennummer
  aus den Kennungen des Kontakts (Konfidenz 0,9). Alles bleibt ein Vorschlag.
- Bestätigen verknüpft zusätzlich Einheit und Vertrag. Folgevorschläge (Rechnung an Belegeingang,
  Schadensfoto an Ticket, Vertrag an Vertragsakte, Protokoll an Versammlung) stehen im Feld
  `final.followups` mit Zustand `proposed`. Die Bestätigung eines Folgevorschlags verknüpft nur
  Ticket oder Vertrag; Rechnung und Versammlung bleiben Hinweise, Buchung und Freigabe liegen in
  den eigenen Abläufen.
- Direktablage: Schalter `document_intake_auto_file` (Standard aus). Bei genau einem
  Objektkandidaten über der Schwelle und vorhandenem Text wird nur die Objektverknüpfung angelegt,
  der Vorschlag gilt als angenommen (`final.auto_filed`, ohne Person) und wird gemeldet. Keine
  Kategorie, kein Kontakt, keine Sichtbarkeit. Rücknahme mit `POST .../revert-auto`.
  Entscheidung offen: AA13-01.
- DocumentStore: `get`, `search`, `list_changes` im Protokoll. Paperless: Download, Suche über
  Objekt-Tag und Text, Änderungen über `modified__gt` (keine Löschungen). Drive: bestehende
  Methoden, Cursor `None` startet neu. `MinioStore` kapselt den S3-Objektspeicher (Suche leer,
  keine Änderungen, weil der Index der Plattform führt).
- Kontaktvorschau: Rolle je Zeile (kommt zur Rolle des Laufs hinzu) und optionale Übernahme leerer
  Felder beim Verknüpfen; vorhandene Werte werden nie überschrieben.

## Ergänzung AB11 (01.10.2026)

Die Direktablage ist in `tests/integration/test_ab11_jobs_intake.py` für beide Schalterzustände getestet: aus (Vorschlag), an unter der Schwelle (Vorschlag), an bei zwei Objekten über der Schwelle (Vorschlag), an bei einem eindeutigen Objekt (Ablage mit Ereignis `document.intake_auto_filed`). Der Schalter eines Mandanten wirkt nie auf einen anderen Mandanten. Die Entscheidung AA13-01 bleibt offen, der Schalter bleibt Standard aus.
