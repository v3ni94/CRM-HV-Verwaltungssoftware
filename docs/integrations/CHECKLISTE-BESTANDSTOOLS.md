# Checkliste je Bestandstool (V1, AA16-03)

Stand 01.10.2026. Quelle der Statusangaben sind ausschließlich die Dossiers und Verträge in
diesem Verzeichnis sowie `docs/OPEN_QUESTIONS.md`; erhoben wurde im Bestandsprojekt selbst
nichts neu. `[x]` heißt: im Repo belegt. `[ ]` heißt: offen oder nicht belegt. Wer einen Punkt
abhakt, trägt Datum und Fundstelle ein. Das Vorgehen je Dossier beschreibt `DOSSIER-VORLAGE.md`.

Für alle Tools gilt gleich:

* Der Erhebungslauf nach Anhang B (Prompt in `docs/MASTER-PROMPT.md`) wird vom Betreiber im
  jeweiligen Bestandsprojekt ausgeführt (V1). Ohne Lauf bleibt das Dossier ein Auszug aus dem
  Plattform-Repo und trägt den Vermerk "Quelltext liegt nicht vor".
* Der Wissensdatenbank-Eintrag je Dossier ist für kein Dossier nachgewiesen (AA16-03). Das
  Dossier erhält nach dem Eintrag eine Zeile mit Datum und Fundstelle.
* Die Empfehlung eines Dossiers ist ein Vorschlag. Anbinden, übernehmen oder ablösen
  entscheidet der Betreiber; die Entscheidung wird im Abschnitt 8 des Dossiers vermerkt.

## Müller FLOW

Dossier: `dossier-flow.md` (27.09.2026, Ergänzung 01.10.2026). Erwartete Datei:
`mueller-flow.md`. Plattformseite: `mhvp.automation` (Regeln, Webhook-Aktion),
Anmeldung über die OIDC-Fähigkeit der Plattform (Master-Prompt Abschnitt 6).

* [ ] Erhebungslauf im FLOW-Projekt ausgeführt (steht aus)
* [ ] 1 Zweck: konkrete Prozesse der HVM (Prozessliste)
* [ ] 2 Technik: Stack, Hosting, Abhängigkeiten
* [ ] 3 Datenmodell
* [ ] 4 Schnittstellen: tatsächliche Endpunkte von FLOW (vorgesehen sind Webhooks und OIDC)
* [x] Zielbild der Plattformseite dokumentiert (Ablösung durch `mhvp.automation`)
* [ ] 7 Empfehlung begründet (erst nach dem Lauf)
* [ ] Entscheidung des Betreibers: anbinden, übernehmen oder ablösen
* [ ] Wissensdatenbank-Eintrag nachgewiesen

## Immoware Hub Integrationsplattform

Dossier: `immoware-hub.md` (25.09.2026, Quelle Repo IMMOWARE24). Empfehlung des Dossiers:
ablösen. Stilllegung: `docs/runbooks/hub-abschaltung.md`.

* [x] Dossier mit den Abschnitten 1 bis 8 erstellt
* [x] Plattformseite: Übernahme der Immoware24-Exporte in `mhvp.imports`, Paperless-Objektsuche,
      CalDAV-Kalenderadresse (Abschnitte im Dossier)
* [ ] Parser-Abgleich Hub gegen `mhvp.imports` bestätigt (AA16-02, Betreiber)
* [ ] Fragen aus Abschnitt 8 beantwortet: DAV-Modul von Immoware24, Nutzung der Hub-API durch
      andere Programme, Schreibzugriff auf Paperless, Stichtag der Abschaltung
* [ ] Entscheidung des Betreibers: ablösen bestätigt, Stichtag
* [ ] Wissensdatenbank-Eintrag nachgewiesen

## Mail optimierung

Dossier: `mail-optimierung.md` (25.09.2026, Quelle Repo IMMOWARE24). Empfehlung: Übernahme als
Modul (Reiter Mail). Plattformseite: `mhvp.communication` und `mhvp.tickets`
(`apps/api/src/mhvp/communication/README.md`). Das Bestandsprogramm hat laut Dossier
Abschnitt 4 keine eigene REST-API; Stand Produktion 24.09.2026: Schreib- und Versandschalter
aus, kein Postfach angebunden, KI nicht eingerichtet.

* [x] Dossier mit den Abschnitten 1 bis 8 erstellt
* [x] Vorgang und Ticket als gemeinsames Objekt entschieden (25.09.2026) und umgesetzt
      (`POST /api/v1/tickets/merge`, `mhvp.tickets`)
* [x] Antwortentwürfe mit Vier-Augen-Freigabe umgesetzt (`communication:approve`)
* [x] Eingehender Webhook für klassifizierte Mails technisch vorbereitet (`inbound-mail-webhook.md`,
      M20-04, AE38); Wirkung nur, wenn das Bestandsprogramm einen ausgehenden Webhook erhält
* [ ] Entscheidung des Betreibers: Übernahme als Modul bestätigt oder Webhook-Quelle (AE38-01)
* [ ] Freigabe für Aktionspläne (Frage 4 des Dossiers, offen)
* [ ] Frage 2: weitere Gesellschaften, die das Modul nutzen
* [ ] Frage 3: Gmail bleibt Mailanbieter
* [ ] Frage 5: Weiterleitung von `mail.muellerhv.de`
* [ ] Wissensdatenbank-Eintrag nachgewiesen

Bei Entscheidung "Webhook-Quelle" zusätzlich:

* [ ] Erweiterung im Bestandsprogramm: ausgehender Webhook nach dem Vertrag in
      `inbound-mail-webhook.md` (Signatur, `event_id`, Zeitstempel) [zu ergänzen durch Betreiber]
* [ ] Quelle und API-Schlüssel (Recht `mail_inbound:ingest`) im Testmandanten angelegt
* [ ] Testlieferung mit Wiederholung (200) und falscher Signatur (401) geprüft
* [ ] Entscheidung zur Fremdklassifikation (Vorschlag oder verbindlich) dokumentiert

## Übergabeprotokoll

Dossier: `dossier-uebergabeprotokoll.md` (27.09.2026). Erwartete Datei:
`uebergabeprotokoll.md`. Plattformseite: Modul `handover` (M30), Importer `uprotokoll_import`.

* [ ] Erhebungslauf im Projekt "Übergabeprotokoll" ausgeführt (steht aus)
* [x] Zielbild als Modul `handover` umgesetzt
* [ ] Kompatibilität des Exportformats (Feldnamen, Version) zum Importer bestätigt
* [ ] Übernahme aller offenen Altprotokolle bestätigt (Voraussetzung für die Stilllegung)
* [ ] Entscheidung des Betreibers: Stilllegung des Bestandsprojekts
* [ ] Wissensdatenbank-Eintrag nachgewiesen

## Objektakte

Dossier: `dossier-objektakte.md` (27.09.2026) und Schnittstellenvertrag `objektakte.md`
(M29, Stufe 3 und 4). Plattformseite: lesende API und Webhooks.

* [ ] Erhebungslauf im Objektakte-Projekt ausgeführt (steht aus; das Dossier bündelt nur den
      Vertrag aus Sicht des CRM)
* [x] Schnittstellenvertrag der Plattform dokumentiert (`objektakte.md`)
* [ ] 2 Technik: Hosting und Abhängigkeiten außerhalb von Drive
* [ ] 3 Datenmodell: interne Struktur von Objektakte
* [ ] Kontakt-ID wirkt in Objektakte noch nicht (Dossier Abschnitt 7)
* [ ] Löschung: Regel für Drive und Paperless nach Löschung im CRM (Dossier Abschnitt 7)
* [ ] Wissensdatenbank-Eintrag nachgewiesen

## smart-einzug

Dossier: `dossier-smart-einzug.md` (27.09.2026). Vertrag der Sendeseite: `smart-einzug.md`,
`webhooks.md`. Das Projekt läuft laut Master-Prompt Abschnitt 13.3 auf einem eigenen VPS.

* [ ] Erhebungslauf im smart-einzug-Projekt ausgeführt (steht aus)
* [x] Sendeseite der Plattform umgesetzt und getestet: `contact.updated`,
      `contact.mandate_iban_changed`, `invoice.issued`
      (Test `apps/api/tests/integration/test_ga09_smart_einzug_contact_updated.py`)
* [ ] Empfangsschnittstelle von smart-einzug dokumentiert, Signaturprüfung geklärt
* [ ] lexoffice-Anbindung als Zielsystem geklärt (Abschnitt 13.5)
* [ ] Betriebsverantwortung und Zeitpunkt der Migration des separaten VPS
* [ ] Entscheidung des Betreibers: anbinden oder übernehmen
* [ ] Wissensdatenbank-Eintrag nachgewiesen
