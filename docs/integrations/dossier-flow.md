# Dossier: Müller FLOW (Fable 5.1 und Ultracode Strategie)

Stand 27.09.2026. Erhebung nach Anhang B des Master-Prompts (Abschnitt 13.4). Dem
Plattform-Repo liegt der Quelltext von Müller FLOW nicht vor; dieses Dossier fasst nur
zusammen, was aus `docs/MASTER-PROMPT.md` und `docs/OPEN_QUESTIONS.md` (Punkt V1) belegbar
ist. Es ersetzt nicht den in Anhang B verlangten Erhebungslauf im FLOW-Projekt selbst.

## 1. Zweck

Prozess- und Automatisierungssoftware der HVM (Arbeitstitel „Fable 5.1 und Ultracode
Strategie“). Laut Abschnitt 13.4 des Master-Prompts deckt sie wiederkehrende Abläufe der
Hausverwaltung ab, die als Regeln beziehungsweise Automatisierungen laufen. [zu ergänzen
durch Betreiber: konkrete Nutzergruppe, tatsächlich abgedeckte Geschäftsprozesse, Screenshots
oder Prozessliste].

## 2. Datenbestand

Kein Zugriff auf Quelltext oder Datenmodell. [zu ergänzen durch Betreiber: Datenbank/Storage,
Tabellen oder Entitäten für Regeln, Auslöser, Aktionen, Protokolle, Bezug zu Objekt- oder
Vertragsnummern].

## 3. Schnittstellen

Keine dokumentierten Endpunkte bekannt. [zu ergänzen durch Betreiber: vorhandene REST-
Endpunkte oder Funktionen, Webhooks, Authentifizierung, Zeitpläne].

## 4. Ablösestatus im CRM

Die Plattform besitzt bereits eine eigene Regel-Engine, die den in Abschnitt 13.4 genannten
Zielzustand für FLOW technisch abbildet:

- Modul `apps/api/src/mhvp/automation` (Milestone M9, Aufgaben A38/A39 der
  `docs/plans/LUECKENLISTE-2026-09-26.md`, Regelwerk `docs/rules/M9-02-automation.md`).
- Auslöser: Domain-Events (`trigger.event_type`) und Zeitpläne (`schedule`, täglich,
  wöchentlich, monatlich).
- Aktionen Stufe 1: Ticket aus Vorlage anlegen, interne Benachrichtigung, Ticketfeld setzen.
  Aktionen Stufe 2: signierter ausgehender `webhook`, `mail_draft` (Entwurf im
  Ticketpostfach, Vier-Augen-Prinzip bleibt unberührt), `letter_draft` (Brief auf dem
  Briefbogen als Dokument), `ai_task` (Vorschlag, keine autonome Buchung).
- Endpunkte: `/api/v1/automation/meta`, `/rules` (CRUD, `/activate`, `/test`), `/runs`,
  `/webhook-deliveries/{id}/redeliver` (`apps/api/src/mhvp/automation/routers.py`).
- Damit ist die in Abschnitt 13.4 genannte Anbindung „an die Regel-Engine und das
  Ticketsystem über Webhooks“ bereits als Zielmodul vorhanden; eine Übernahme bewährter
  FLOW-Abläufe als `automation_rule`-Vorlagen setzt aber die Kenntnis der tatsächlichen
  FLOW-Regeln voraus.
- Ticketsystem als Ziel der Aktionen: Modul `apps/api/src/mhvp/tickets`.

Noch nicht umgesetzt: Ein direkter FLOW-Konnektor (Import bestehender FLOW-Regeln als
`automation_rule`, Übernahme laufender FLOW-Webhooks als eingehende Auslöser) existiert nicht;
die Regel-Engine kennt bisher nur eigene, im CRM angelegte Regeln.

## 5. Offene Punkte

- Kein Erhebungslauf nach Anhang B im FLOW-Projekt durchgeführt; Zweck, Technik, Datenmodell,
  Schnittstellen, Fachlogik und bekannte technische Schulden von FLOW sind unbekannt.
- Empfehlung (anbinden, übernehmen, ablösen) kann erst nach dieser Erhebung fachlich
  begründet werden. Nach Abschnitt 13.4 ist das Zielbild „Ablösung, sobald die Regel-Engine
  den Zweck erfüllt“; ob die vorhandene Regel-Engine (Stufe 1/2) den FLOW-Funktionsumfang
  bereits deckt, ist offen.
- Punkt V1 in `docs/OPEN_QUESTIONS.md` bleibt für Müller FLOW als offen vermerkt, bis der
  Betreiber den Anhang-B-Lauf im FLOW-Projekt ausführt und das Ergebnis übergibt.

## Zusammenfassung in zehn Zeilen

1. FLOW ist ein Bestandsprojekt der HVM ohne im Plattform-Repo vorliegenden Quelltext.
2. Dieses Dossier beruht ausschließlich auf Angaben aus dem Master-Prompt.
3. Zweck, Technik und Datenmodell von FLOW sind unbekannt und offen zu erheben.
4. Schnittstellen von FLOW sind nicht dokumentiert.
5. Die Plattform hat bereits eine eigene Regel-Engine (`mhvp.automation`).
6. Diese deckt Ereignis- und Zeitplan-Auslöser sowie mehrstufige Aktionen ab.
7. Ticket-, Mail-, Brief- und Webhook-Aktionen sind bereits produktiv nutzbar (ohne
   autonome Buchungen oder Zahlungen).
8. Ein Konnektor zur Übernahme bestehender FLOW-Regeln existiert nicht.
9. Empfehlung ist ohne Anhang-B-Erhebung im FLOW-Projekt nicht seriös möglich.
10. Nächster Schritt: Betreiber führt den Anhang-B-Prompt im FLOW-Projekt aus.
