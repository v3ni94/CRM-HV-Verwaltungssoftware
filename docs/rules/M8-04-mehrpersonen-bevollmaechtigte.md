# M8-04 Mehrpersonen-Parteien aus dem Adressbuch und Bevollmächtigte mit Zustellregel

| Field | Content |
| --- | --- |
| ID | `M8-04` |
| Title | Mehrpersonen-Parteien (Eheleute, Gemeinschaften) aus den Immoware24-Kontaktlisten als eine Partei mit Mitgliedern; Bevollmächtigte am Kontakt mit Zustellregel |
| Scope | Kontaktimport `mhvp.imports.kontakte` und Zuordnung `mhvp.imports.zuordnung` (alle Mandanten, alle Kontaktlisten); Beziehung `representative` in `contact_relation` mit `delivery_mode`; Empfängerauflösung für Serienversand (`POST /dispatches/serial`), Serienbriefe (`POST /letters/serial`), WEG-Einladungsempfänger (`GET /hoa/meetings/{id}/invitation-recipients`) sowie seit 27.09.2026 Mahnschreiben, Abrechnungsschreiben Miete, Einzelbriefe (`POST /letters`) und Einzelzustellungen (`POST /dispatches`) |
| Source status | Keine Rechtsnorm im Quellenregister (annex C); Fachliche Umsetzung nach Betreiberentscheidung vom 26.09.2026 (Chat, Timo Müller). Ob eine Zustellung an den Bevollmächtigten im Einzelfall rechtlich als Zugang beim Eigentümer gilt (zum Beispiel Einladung nach WEG), ist nicht Gegenstand dieser Regel und bleibt Prüfung durch Rechtsanwalt; die Regel steuert nur, wer ein Schreiben erhält |
| Acceptance case | keine in annex D; Tests `apps/api/tests/unit/test_kontakte_multi_person.py` (positive, negative und unklare Namensformen), `apps/api/tests/unit/test_kontakte_import.py`, `apps/api/tests/integration/test_kontakte_import.py` (Partei mit Mitgliedern, Wiederholung, Mandantentrennung), `apps/api/tests/integration/test_zuordnung_import.py` (Zuordnung findet die gemeinsame Partei), `apps/api/tests/integration/test_contact_representatives.py` (Zustellregel in Versand, Serienbrief und Einladung, Audit, Mandantentrennung), `apps/web-crm/src/components/contacts/RepresentativesPanel.test.tsx` |
| Implementation | `mhvp.imports.kontakte.detect_multi_person`, `_prepare_members`, `apply_prepared`; `mhvp.imports.zuordnung.import_party`; `mhvp.contacts.models.DeliveryMode`, `ContactRelation.delivery_mode` (Migration 0140); `mhvp.contacts.recipients.resolve_recipients`; Endpunkte `GET/PATCH/DELETE /contacts/{id}/contact-relations`; `mhvp.communication.dispatch.expand_items`; `mhvp.documents.routers.serial_letter`; `mhvp.hoa.meetings.invitation_recipients`; UI `RepresentativesPanel` auf der Kontaktseite |
| Change reason | Nachtrag 27.09.2026: Betreiberentscheidung M23-07 (Ausdehnung auf Mahn-, Abrechnungs-, Einzelschreiben und Einzelzustellungen mit Rechtsvorbehalt). Betreiberentscheidung 26.09.2026 zu M8-04 (bisher je Kontakt eine Partei) und neue Anforderung Bevollmächtigter (Beispiel: Eigentümer Timo Müller lässt Jan Müller die Sondereigentumsverwaltung abwickeln) |

## Regeln

### Mehrpersonen-Namen im Kontaktimport

- Erkannt werden "Nachname, Vorname1 & Vorname2" (auch "und", "u."), "Vorname1 und Vorname2
  Nachname" (jeder Vorname ein Wort, das letzte Glied trägt den Nachnamen), die Vorsätze
  "Eheleute", "Ehepaar", "Herr und Frau", "Familie" vor einer dieser Formen sowie "Vorname
  Nachname und Vorname Nachname" mit gleichem Nachnamen. Mehrteilige Vornamen ("Hans Peter
  und Erika Müller") nur, wenn die Briefanrede den Familiennamen bestätigt ("Sehr geehrte
  Eheleute Müller").
- Ergebnis ist eine Partei mit dem exportierten Namen (zum Beispiel "Goritzka, Janina &
  Jacek") und je Person ein Kontakt in der Rolle primary. Jedes Mitglied trägt die
  Immoware24-id, den exportierten Namen und `immoware24_member` (1, 2, ...). Die Anschrift
  gilt für alle Mitglieder; Telefon und E-Mail des Exports stehen nur beim ersten Mitglied,
  weil nicht bekannt ist, wem sie gehören.
- Nicht ableitbare Fälle bleiben ein Kontakt mit Namen wie exportiert und stehen im Bericht
  unter `pruefung` (Zähler `review`): Erbengemeinschaften (die Erben stehen nicht im Namen),
  fehlende Vornamen ("Eheleute Müller", "Herr und Frau Mustermann"), fehlender Nachname ("Max
  und Erika"), zwei vollständige Namen mit verschiedenen Nachnamen, Doppelvornamen ohne
  Bestätigung, mehrere Kommas. Es wird nichts geraten; die Mitglieder werden manuell ergänzt.
- Firmenbezeichnungen mit "und" oder "&" ("Schmidt und Partner", "Müller & Söhne") sind
  keine Mehrpersonen-Namen.
- Die Zuordnung der Objektliste (`mhvp.imports.zuordnung`) führt den exportierten Namen auf
  das erste Mitglied und nutzt die gemeinsame Partei (alle Mitglieder mit derselben
  Immoware24-id); es entsteht keine zweite Partei.

### Bevollmächtigte und Zustellregel

- Ein Bevollmächtigter ist eine Beziehung der Art `representative` vom vertretenen Kontakt
  zum Bevollmächtigten, mit optionaler Gültigkeit (`valid_from`, `valid_to`) und Zustellregel
  `delivery_mode`: `both` (Vorgabe: Vollmachtgeber und Bevollmächtigter erhalten alles),
  `representative_only`, `owner_only`. Andere Beziehungsarten tragen immer `both`.
- `mhvp.contacts.recipients.resolve_recipients` ist die einzige Stelle, die die Regel
  auswertet: Serienversand (E-Mail, Post, Portal), Serienbriefe und die Empfängerliste einer
  WEG-Einladung rufen sie auf. Abgelaufene Vollmachten und gelöschte Bevollmächtigte zählen
  nicht; ohne wirksame Vollmacht erhält der Kontakt selbst. Ein Kontakt, der mehrfach
  erreicht wird, erhält ein Schreiben einmal.
- Ein Serienbrief an den Bevollmächtigten nennt unter dem Empfänger "für <Vollmachtgeber>"
  und ist mit beiden Kontakten verknüpft.
- Anlegen, Ändern der Regel oder Gültigkeit und Beenden brauchen `contacts:update` und
  werden im Audit-Log des vertretenen Kontakts protokolliert (alt und neu).
- Einzelbriefe (`POST /letters`), Einzelzustellungen (`POST /dispatches`), Mahnschreiben und
  Abrechnungsschreiben Miete folgen seit dem 27.09.2026 ebenfalls der Regel (Nachtrag unten).

### Nachtrag 27.09.2026: Mahnschreiben, Abrechnungsschreiben, Einzelbriefe, Einzelzustellungen

Betreiberentscheidung vom 27.09.2026 (M23-07, `docs/OPEN_QUESTIONS.md`), Fachliche
Umsetzung mit Rechtsvorbehalt:

- Die Zustellregel gilt auch für Mahnschreiben (`mhvp.accounting.dunning_letters`, Fälle
  eines Mahnlaufs), Abrechnungsschreiben Miete (`mhvp.billing.letters`, `POST
  /statements/{id}/letters` und `/letters/preview`), Einzelbriefe (`POST /letters`,
  `/letters/preview`) und Einzelzustellungen (`POST /dispatches`). Vorgabe bleibt `both`.
  Ausgangspunkt ist wie bisher das erste Parteimitglied des Vertrags
  (`mhvp.contacts.recipients.debtor_contact_id`).
- Erhält nur der Bevollmächtigte, nennt das Schreiben unter dem Empfänger "für
  <Vollmachtgeber>" und ist mit beiden Kontakten verknüpft. Bei `both` entsteht je Empfänger
  ein Schreiben: beim Mahnschreiben als Kopien in einem PDF (ein Dokument am Fall, mit beiden
  Kontakten verknüpft), bei Abrechnungsschreiben und Einzelbriefen als eigene Dokumente
  (`POST /letters` liefert das erste Dokument und die weiteren unter `further_documents`,
  `POST /dispatches` die erste Zustellung und die weiteren unter `further_dispatches`).
- Mahnschreiben, die nur den Bevollmächtigten erreichen, tragen die Warnung
  `mhvp.contacts.recipients.REPRESENTATIVE_ONLY_WARNING`. Sie wird in der Vorschau des
  Mahnlaufs je Fall angezeigt (`warnings`, CRM-Kennzeichen), in der Fallbegründung und im
  Zähler `representative_only` des Laufs protokolliert und beim Ablegen des Schreibens
  zurückgegeben (`letter_warnings`). Sie entfällt erst, wenn ein Rechtsanwalt bestätigt,
  dass die Zustellung an den Bevollmächtigten als Zugang beim Vollmachtgeber gilt.
- WEG-Jahresabrechnungen haben keinen eigenen Empfängerversand je Eigentümer; sobald ein
  solcher entsteht, ist dieselbe Regel anzuwenden. WEG-Einladungen sind bereits erfasst.
- Tests: `apps/api/tests/integration/test_m16_dunning_letters.py`
  (`test_letter_follows_delivery_rule_of_representatives`),
  `apps/api/tests/integration/test_m17_operating_costs.py` (Abschnitt M23-07 in
  `test_a07_tenant_letters_from_snapshot`),
  `apps/api/tests/integration/test_contact_representatives.py` (Einzelbrief, Einzelzustellung).
