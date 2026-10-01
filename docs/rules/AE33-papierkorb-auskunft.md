# AE33-papierkorb-auskunft: Dokument-Papierkorb und Umfang der Auskunft als Mandantenschalter

- ID: AE33-papierkorb-auskunft (Befunde AC07-01, AC07-03; Ergänzung zu AC07-auskunft-loeschung)
- Geltungsbereich: alle Mandanten; Module documents (Papierkorb, Löschcheckliste, Löschjournal), contacts (Auskunftsexport), CRM (Papierkorb, Schalter).
- Spezifikation: 6.9.5 (Aufbewahrung und Löschung, Backup 30 Tage rollierend), 7.11 S05 (Löschung konsistent, Sperren vorrangig), 7.11 S06 (Auskunftsexport).
- Quellenstatus (Anhang C): R25 (DSGVO) als Prüfumfang, R17 bis R19 für Aufbewahrung. Keine Norm wird hier ausgelegt. Papierkorb und Auskunftsumfang sind Produktschutz mit Mandantenschalter; ob und wie lange personenbezogene Daten im Papierkorb bleiben dürfen (AE33-01) und welcher Auskunftsumfang zulässig ist (AC07-01) ist Offene Entscheidung. Die 30 Tage sind ein Vorschlag, keine Rechtsfrist.
- Abnahmefall: kein eigener Fall in Anhang D; Tests apps/api/tests/integration/test_ae33_trash.py, apps/api/tests/integration/test_ae33_access_export_scope.py, apps/web-crm/src/components/documents/DocumentTrash.test.tsx, TrashSettings.test.tsx, apps/web-crm/src/components/contacts/AccessExportSettings.test.tsx.
- Änderungsgrund: Prioritätenliste 01.10.2026, Punkt 26 (AC07-01, AC07-03).

## Papierkorb (AC07-03)

Schalter je Mandant (`document_trash_setting`): `enabled` (Standard aus), `retention_days` (Standard 30, Bereich 1 bis 365). GET und PUT /documents/trash-settings (Rechte tenant_settings:read und tenant_settings:update), Änderung als Ereignis `document_trash_setting.updated`. Die Frist gilt für Dokumente, die danach in den Papierkorb gelegt werden.

| Zustand | Wirkung |
| --- | --- |
| Schalter aus | Eine zulässige Löschung (DELETE /documents/{id} oder Ausführung eines Löschvorschlags) ist endgültig wie bisher. |
| Schalter an | Dieselbe Löschung legt das Dokument in den Papierkorb (`document.deleted_at`, `deleted_by`, `purge_at`; Ereignis `document.trashed`). Original, Spiegelkopien und Ableitungen bleiben unverändert. |

- Vorbedingung bleibt unverändert die Prüfung `deletion_blocker` (freigegebenes Profil, abgelaufene Frist, keine Sperre). Der Papierkorb umgeht nichts und verlängert nur die Zeit bis zur endgültigen Löschung.
- Ein Dokument im Papierkorb ist für jede ORM-Abfrage unsichtbar (Liste, Suche, Verknüpfungen, Download, Briefe, Löschvorschläge). Sichtbar ist es nur im Papierkorb und in der Löschcheckliste.
- Liste GET /documents/trash (Recht documents:delete, Geltungsbereich der Mitgliedschaft beachtet) mit Status `in_trash`, `due` (Frist vorbei) oder `held` (Sperre, Grund im Feld `blocker`).
- Wiederherstellung POST /documents/trash/{id}/restore mit Begründung (documents:delete), Ereignis `document.restored`. Immer zulässig, weil Behalten nie unzulässig ist; der monatliche Lauf kann das Dokument erneut vorschlagen. Eine Sperre am Dokument selbst wird nach der Wiederherstellung gesetzt.
- Endgültige Löschung: täglicher Auftrag `mhvp.documents.trash_purge` (05:10 UTC) und vorzeitig POST /documents/trash/{id}/purge mit Begründung (documents:delete). Jede endgültige Löschung prüft Profil, Frist und alle Sperren (Dokument, Vorgang, Verfahren, verbundenes Dokument) erneut. Bei einem Hindernis bleibt das Dokument im Papierkorb (Status `held`, API 409 MHVP-DOC-0001), die Verweigerung wird einmal je Grund als `document.deletion_refused` mit `from_trash` protokolliert. Sonst läuft `retention.delete_now` wie bisher (Index, Original, Spiegelschritte, Embeddings, KI-Auszüge) und das Ereignis `document.deleted` trägt `from_trash`, `trashed_at`, `trashed_by`, `early` und die Begründung.
- Löschcheckliste: neues Ziel `trash` (open im Papierkorb, done nach endgültiger Löschung, not_applicable ohne Papierkorb); Gesamtstatus `in_trash`; die übrigen Ziele stehen auf `pending`. Der Nachlauf lässt Dokumente im Papierkorb unberührt.
- Löschjournal und Replay (Wiederherstellung aus Backup): `document.trashed` und `document.restored` werden mitgeführt; ein Eintrag wird nur angewendet, wenn er die letzte Aussage zum Dokument im Journal ist (trashed: erneut in den Papierkorb mit der protokollierten Frist, restored: aus dem Papierkorb nehmen). Sperren und Hash gehen vor wie bei der Löschung.
- Backups: unverändert nicht bearbeitet (Runbook backup.md). Der Papierkorb ändert die Backupdauer nicht (AC07-03).

## Umfang der Auskunft (AC07-01)

Schalter je Mandant (`contact_access_export_setting`), GET und PUT /contact-access-export-settings (tenant_settings:read und tenant_settings:update), Änderung als Ereignis `contact_access_export_setting.updated`:

| Schalter | Werte | Standard | Wirkung |
| --- | --- | --- | --- |
| third_party_scope | none, names | none | none: andere Personen nur mit Rolle. names: Name und Rolle (Beziehungen, weitere Parteimitglieder, abweichender Kontoinhaber); nie Anschrift, Kontaktdaten, Kennungen oder Bankdaten. |
| include_internal_notes | ja, nein | nein | ja: Notizfeld und Kontaktnotizen (Kategorie, Titel, Text, Zeit, Wiedervorlage) ohne Verfasser und ohne Kennungen. Nein: nur die Anzahl wird genannt. |

Der Umfang wird beim Vorbereiten im Ereignis `contact.access_export.prepared` festgehalten (`options`); Prüfung, Freigabe und jeder Download bauen genau diesen Inhalt, auch wenn die Schalter inzwischen geändert wurden (Hashabgleich). Ältere Ereignisse ohne `options` gelten als Standard. Die Liste der zurückgehaltenen Kategorien im Export (`withheld`) folgt dem Umfang. Hashwerte, Fingerabdrücke, Tokens, KI-Rohdaten und Ereignisdaten bleiben in jeder Variante draußen. Prüfung und Freigabe durch eine zweite Person bleiben unverändert (AC07-auskunft-loeschung).
