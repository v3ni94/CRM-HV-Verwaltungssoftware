# M9-11: Lern-Workflow, Regelvorschläge aus wiederholten manuellen Entscheidungen

| Feld | Inhalt |
| --- | --- |
| ID | M9-11 |
| Titel | Lern-Workflow: Regelvorschlag nach wiederholter gleicher manueller Entscheidung je Absender, Aktivierung nur durch ausdrückliche Annahme |
| Geltungsbereich | Alle Mandanten. Zuordnung von Mails (Kontakt, Objekt) und Tickets (Kontakt, Objekt, Einheit) sowie Ticketthema und Bearbeiter, jeweils je Absenderadresse und je Absenderdomain. Ausgeschlossen: Zahlungsempfänger, IBAN, WEG-Beschlüsse, Gebühren, steuerliche Einordnung, jede Buchung und Zahlung; kein Bezug zu den Freigabestufen G1 bis G5 |
| Quellenstatus | Produktschutz (strengerer interner Standard nach Regel 0.1.6, keine Rechtsgrundlage); Betreiberwunsch vom 27.09.2026. Keine Norm aus Anhang C einschlägig |
| Akzeptanzfall | Kein Fall aus Anhang D; interne Testfälle (siehe Tests unten). Abnahme durch den Betreiber offen |
| Umsetzung | `mhvp.automation.learning` (Erkennung, Annahme, Ablehnung, API), `mhvp.automation.models.AutomationRuleProposal`, Aktion `assign_record` und Ticketfeld `topic` in `mhvp.automation.schemas` und `services`, `mhvp.communication.assignment_review.apply_rule_assignment` mit sicherer Kette `_rule_contact_chain` (A80-01 Regel 6), Ereignis `ticket.topic_changed` in `PATCH /tickets/{id}`, Mandanteneinstellung `rule_proposal_threshold`, Migrationen 0218 und 0220 (Absenderspalte `message.from_address_norm` mit Index); CRM `/einstellungen/regelvorschlaege` (`RuleProposals.tsx`) und Hinweis im Mailbereich |
| Änderungsgrund | Betreiber: Wiederholt ein Nutzer etwa fünfmal dieselbe manuelle Entscheidung, soll das System eine Regel vorschlagen (27.09.2026). Nacharbeit 28.09.2026: eine angenommene Kontaktregel ergänzt Objekt und Einheit über die sichere Kette der Zuordnungsprüfung; die Nachweissuche je Absender läuft über einen Index statt über alle Mails des Mandanten |

## Regel

- Grundlage ist das vorhandene Entscheidungsprotokoll, es wird nichts doppelt gespeichert:
  `assignment_review.decided` (Ja oder manuelle Wahl eines Kontakts, Objekts oder einer
  Einheit; ein Nein zum vorgeschlagenen Datensatz widerspricht genau diesem Datensatz),
  `ticket.assigned` mit Grund `manuell` und `ticket.topic_changed` (Themenwechsel per PATCH).
  Nur Entscheidungen eines Mitglieds zählen; automatische Zuordnungen und Wirkungen von Regeln
  (Kennzeichen `automation` im Ereignis) zählen weder dafür noch dagegen.
- Absender einer Mail ist `from_address`, Absender eines Tickets die Adresse seiner ersten
  eingehenden Mail. Tickets ohne eingehende Mail lernen nichts. Verglichen wird die von der
  Datenbank erzeugte Spalte `message.from_address_norm` (`lower(btrim(from_address))`,
  Migration 0220, 28.09.2026) über den Index `ix_message_tenant_from_address_norm`
  `(tenant_id, from_address_norm)`. Ein Funktionsindex auf `lower(from_address)` wäre unter
  der Zeilensicherheit (RLS) für die Laufzeitrolle nicht nutzbar, weil `lower` nicht
  leakproof ist; die Spalte liefert denselben Vergleichswert wie bisher. Domainmuster
  (`split_part`) nutzen den Index nicht und bleiben ein Filter über die eingehenden Mails.
- Muster je Vorgangsart, Feld und Absender: immer je Absenderadresse; zusätzlich je
  Absenderdomain, wenn die Domain kein öffentlicher Maildienst (Liste `SHARED_MAIL_DOMAINS`)
  und keine Domain eines eigenen Postfachs ist und die Entscheidungen von mindestens zwei
  verschiedenen Adressen stammen.
- Gezählt wird die jüngste ununterbrochene Folge gleicher Entscheidungen. Eine Entscheidung
  für einen anderen Wert oder ein Nein zum Wert der Folge beendet sie; ein Nein zu einem
  anderen Wert ist neutral. Erreicht die Folge die Schwelle (Mandanteneinstellung
  `rule_proposal_threshold`, Standard 5, zulässig 2 bis 50, Annahme A-071), entsteht ein
  Vorschlag mit Status `proposed` und Nachweis (Ereignis-IDs, Anzahl, Adressen, Zeitraum).
- Widerspricht eine spätere Entscheidung, wird ein offener Vorschlag `withdrawn` und bei
  erneutem Erreichen der Schwelle wieder `proposed`.
- Ein Vorschlag handelt nie selbst. Annehmen (`POST /automation/rule-proposals/{id}/accept`,
  Recht `tenant_settings:update`, nur angemeldetes Mitglied, kein API-Schlüssel allein) prüft
  die Grundlage erneut aus dem Protokoll und das Ziel (Kontakt nicht gelöscht, Mitglied aktiv,
  Thema bekannt); nur dann entsteht eine aktive Regel der vorhandenen Regel-Engine
  (`automation_rule`, Auslöser `message.received`, Bedingung `entity.from_address` oder
  `entity.from_domain`, Aktion `assign_record` oder `set_ticket_field`). Sonst 409
  `MHVP-AUTO-0002`, nichts wird geschrieben. Wer und wann angenommen hat, steht am Vorschlag
  (`decided_by`, `decided_at`, `rule_id`) und im Ereignis `rule_proposal.accepted`.
- `assign_record` füllt nur ein leeres Feld und nur, wenn kein Mitglied über diese Dimension
  entschieden hat; die Zuordnungsprüfung vermerkt `auto` mit Entscheidung `rule` und dem
  Regelnamen als Grund, ein Mitglied kann mit Ja korrigieren. Setzt die Regel den Kontakt,
  ergänzt dieselbe Aktion Objekt und Einheit über die sichere Kette der Zuordnungsprüfung
  (A80-01 Regel 6, seit 28.09.2026), ohne zweiten Regelschritt. Themen und Bearbeiter setzt die
  Regel nur am Ticket, das die Mail eröffnet hat (`entity.opens_ticket`), nie an einem
  bestehenden Ticket, dem eine Antwort zugeordnet wird.
- Ablehnen (`POST .../reject`, optionaler Grund) speichert die Anzahl der Entscheidungen zum
  Zeitpunkt der Ablehnung; derselbe Vorschlag erscheint erst wieder, wenn die Folge das
  Doppelte erreicht.
- Die Regel bleibt in der Automatisierung sichtbar, prüfbar (Testlauf) und abschaltbar; ihre
  Läufe stehen im Regelprotokoll.

## Tests

- `apps/api/tests/unit/test_rule_proposal_learning.py`: Folge, Widerspruch, Neutralität eines
  Nein zu anderem Wert, Schwelle, Domainmuster mit zwei Adressen, Ausschluss öffentlicher und
  eigener Domains, Verdopplung nach Ablehnung, nur manuelle Entscheidungen, geschlossene Liste
  der lernbaren Felder, gültige Regeldefinition.
- `apps/api/tests/integration/test_m9_rule_proposals.py`: vier Entscheidungen ohne Vorschlag,
  fünfte mit Vorschlag; Widerspruch setzt zurück und zieht zurück; Ablehnung mit Grund und
  Wiedervorlage erst bei doppeltem Nachweis; Annahme legt aktive Regel an und ordnet die
  nächste Mail zu; Ticketthema und Bearbeiter je Domain; erneute Prüfung beim Annehmen (409);
  Rechte und Mandantentrennung.
- `apps/api/tests/integration/test_a80_rule_assignment_chain.py` (28.09.2026): Kontaktregel
  am Ticket ergänzt Objekt und Einheit (`auto`, Grund, Ereignis mit Regel und Kennzeichen
  `automation`, keine zweite Meldung bei späterer Prüfung); Kontaktregel an der Mail ergänzt
  das Objekt; zwei Verträge lassen die Felder leer und die Rückfrage offen; von einem Mitglied
  gesetztes oder im Review mit Nein entschiedenes Feld bleibt unverändert; Mandantentrennung.
- `apps/web-crm/src/components/settings/RuleProposals.test.tsx`: Anzeige, Annehmen, Ablehnen
  mit Grund, Konflikt, Schwelle, Hinweis-Badge.

## Offen

- Aufbewahrung der Vorschläge (enthalten Absenderadressen): siehe `docs/OPEN_QUESTIONS.md`
  M9-11.
- Erledigt 28.09.2026: Eine Kontaktregel füllt Objekt und Einheit jetzt über die sichere
  Kette nach (A80-01 Regel 6); die Tiefe 1 der Regel-Engine bleibt unverändert.
- Die Nachweissuche für Domainmuster und die Verknüpfung mit `domain_event` (kein Index auf
  `entity_id`) laufen weiterhin ohne passenden Index; bei großem Ereignisbestand prüfen.
