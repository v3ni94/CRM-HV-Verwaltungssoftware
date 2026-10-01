# AC07-auskunft-loeschung: Auskunftsexport mit Prüfschritt, Löschung je Ziel

- ID: AC07-auskunft-loeschung (Befunde GA08-06, GA08-08)
- Geltungsbereich: alle Mandanten; Module contacts (Auskunftsexport), documents (Löschung, Spiegel, Journal, Nachlauf), ai (Embeddings und KI-Auszüge als Ableitungen, nur Datenbereinigung).
- Spezifikation: 7.11 S06 Satz 3 (Auskunftsexport ohne ungeprüfte Geheimnisse oder Daten anderer Personen), 7.11 S05 Satz 4 (Löschung in Index, DMS-Spiegel, Ableitungen und Wiederherstellungsabläufen konsistent), 6.9.5.
- Quellenstatus (Anhang C): R25 (DSGVO) als Prüfumfang, R17 bis R19 für Aufbewahrung. Keine Norm wird hier ausgelegt. Allowlist, Fremdpersonenprüfung und Vier-Augen-Freigabe sind Produktschutz; die rechtliche Einordnung zurückgehaltener Kategorien und der Backupdauer ist Offene Entscheidung (AC07-01 bis AC07-03).
- Abnahmefall: kein eigener Fall in Anhang D; Tests apps/api/tests/integration/test_ac07_access_export.py, apps/api/tests/integration/test_ac07_deletion_checklist.py, apps/web-crm/src/components/contacts/AccessExportPanel.test.tsx, apps/web-crm/src/components/documents/DeletionChecklist.test.tsx.
- Änderungsgrund: Lückenliste 01.10.2026, GA08-06 und GA08-08 offen; Vorfrage P10-05.

## Auskunftsexport (GA08-06)

| Schritt | Route | Recht | Bedingung | Ereignis |
| --- | --- | --- | --- | --- |
| vorbereiten | POST /contacts/{id}/access-exports | contacts:export | Person (kein API-Schlüssel) | contact.access_export.prepared (Hash, Erstellzeit, kein Inhalt) |
| ansehen | GET .../{export_id}/preview | contacts:approve | nicht verworfen | keins, interne Vorschau |
| prüfen | POST .../{export_id}/review | contacts:approve | Status prepared, nicht die vorbereitende Person, Inhalt unverändert | contact.access_export.reviewed |
| freigeben | POST .../{export_id}/approve | contacts:approve | Status reviewed, nicht die vorbereitende Person, Inhalt unverändert | contact.access_export.released |
| verwerfen | POST .../{export_id}/reject | contacts:approve | Status prepared oder reviewed, Grund | contact.access_export.rejected |
| herunterladen | GET .../{export_id}/download | contacts:export | Status released, Inhalt gleich dem geprüften Hash | contact.access_export.downloaded |

Der frühere direkte Abruf GET /contacts/{id}/export liefert 409 (MHVP-CONT-0030). Fehler: MHVP-CONT-0030 Status, MHVP-CONT-0031 zweite Person, MHVP-CONT-0032 Inhalt geändert (neu vorbereiten).

Inhalt: nur Felder der Allowlist in `mhvp.contacts.access_export` (Kontakt, Anschriften, Telefon, E-Mail, Kennungen, Daten, Bankverbindungen mit IBAN, Einwilligungen). Zusätzlich entfernt eine zweite Sperre jeden Schlüssel, der nach Geheimnis, Hash oder Fingerabdruck aussieht. Nicht enthalten: iban_fingerprint, Tokens, externe Kennungen, Notizfeld und Kontaktnotizen (nur Anzahl), KI-Rohdaten, Nutzdaten des Verarbeitungsprotokolls. Andere Personen: Beziehungen nur mit Art, Parteien nur mit eigener Rolle und Anzahl weiterer Mitglieder, ein abweichender Kontoinhaber als Platzhalter. Die Liste der zurückgehaltenen Kategorien steht im Export (`withheld`).

## Löschung je Ziel (GA08-08)

Checkliste GET /documents/deletions/{id}/checklist (documents:read), Nachlauf POST /documents/deletions/{id}/follow-up (documents:delete), täglicher Auftrag mhvp.documents.deletion_follow_up. Ziele und Status: index, original, mirror_paperless, mirror_google_drive, embeddings, ai_extracts (done, open, held), thumbnails (not_applicable, nicht gespeichert), backup (out_of_scope).

- Die Prüfung von Profil, Frist und Sperre bleibt vor jeder Löschung unverändert (6.9.5, D46); Löschungssperren haben Vorrang, auch nach einer Wiederherstellung (Status held).
- Embeddings werden in derselben Transaktion gelöscht, KI-Auszüge (Laufausgabe, Vorschlag, Lernbeispiel) inhaltlich durch einen Platzhalter ersetzt; Kennung, Entscheidung und Person bleiben (AC07-02).
- Das Löschereignis vermerkt den Speicherort des Originals, damit die Checkliste ihn prüfen kann. Altbestand ohne Vermerk gilt als erledigt mit Hinweis.
- Der Nachlauf löscht nie ein wieder vorhandenes Dokument; dafür gilt nur das Replay mit Sperr- und Hashprüfung.
- Wiederherstellung: Das Replay setzt erledigte Spiegelschritte auf open zurück und löscht Ableitungen erneut. Einen Papierkorb für Dokumente gibt es in der Plattform nicht; die Löschung ist nach Vier-Augen-Prüfung endgültig, Wiederherstellung erfolgt nur aus dem Backup.
- Backups werden nicht bearbeitet; es wird keine Löschung in Backups behauptet (Runbook backup.md, AC07-03).
