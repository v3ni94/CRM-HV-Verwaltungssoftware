# Integrationen

Je Bestandstool und Fremdsystem entsteht hier ein Dossier nach Anhang B des Master-Prompts (Punkt V1 in `docs/OPEN_QUESTIONS.md`). Der Betreiber führt den Erhebungsprompt aus Anhang B im jeweiligen Projekt aus; das Ergebnis wird als eigene Datei in dieses Verzeichnis übernommen und zusätzlich in der Wissensdatenbank abgelegt.

| Bestandstool | Erwartete Datei | Status |
| --- | --- | --- |
| Müller FLOW | `docs/integrations/mueller-flow.md` | `docs/integrations/dossier-flow.md` erstellt 27.09.2026 (nur Angaben aus dem Master-Prompt, Quelltext von FLOW liegt nicht vor, Lücken als [zu ergänzen durch Betreiber]) |
| Immoware Hub Integrationsplattform | `docs/integrations/immoware-hub.md` | erstellt 25.09.2026, Empfehlung ablösen |
| Immoware24-Exporte (Migration 13.1) | `docs/integrations/immoware24-exporte.md` | Anforderungsliste erstellt 01.10.2026 (AE37): Zielfelder je Berichtsart, Exportangaben und Spaltenüberschriften vom Betreiber auszufüllen |
| Mail optimierung | `docs/integrations/mail-optimierung.md` | erstellt 25.09.2026, Empfehlung übernehmen als Reiter Mail |
| Übergabeprotokoll | `docs/integrations/uebergabeprotokoll.md` | `docs/integrations/dossier-uebergabeprotokoll.md` erstellt 27.09.2026 (Zielbild bereits als Modul `handover`/M30 umgesetzt, Bestandsprojekt selbst noch nicht erhoben) |
| Objektakte | `docs/integrations/objektakte.md` | Schnittstellenvertrag M29 Stufe 3/4 erstellt 26.09.2026 (lesende API, Webhooks); `docs/integrations/dossier-objektakte.md` erstellt 27.09.2026 im Anhang-B-Format |
| smart-einzug | `docs/integrations/smart-einzug.md` | `docs/integrations/dossier-smart-einzug.md` erstellt 27.09.2026 (nur Angaben aus dem Master-Prompt und dem Webhook-Vertrag A69, Quelltext liegt nicht vor) |
| Paperless-ngx (Spiegel-DMS, Schlagwort "gelöscht" bei Löschung) | `docs/integrations/paperless.md` | erstellt 26.09.2026 (M6-01, M6-03) |
| Google Drive (Spiegelablage, Löschung mit Papierkorb-Ersatz) | `docs/integrations/google-drive.md` | erstellt 26.09.2026 (M6-02, M6-03) |
| Ausgehende Webhooks (Vertrag für alle Fremdsysteme) | `docs/integrations/webhooks.md` | erstellt 26.09.2026 (A69, `contact.updated`, `invoice.issued`) |
| Gmail (Pub/Sub-Push, Vollabruf, Sicherheitsnetz) | `docs/integrations/gmail.md` | erstellt 26.09.2026 (Betreiberentscheidung Sofortabruf, M20-07) |
| Messdienstleister (ista, Techem, KALO, Brunata Minol, BRUNATA-METRONA) | `docs/integrations/messdienstleister.md` | erstellt 26.09.2026 (M40-01, Stufe 1 ohne Anbieteradapter) |
| Postdienst (Brief- und Postversand, LetterXpress LXP API v3, Postausgangsliste) | `docs/integrations/postdienst.md` | erstellt 27.09.2026 (M23-01, Adapter nach öffentlicher Dokumentation, Freigabe je Mandant Standard aus) |
| FinTS/HBCI PIN/TAN (direkte Bankanbindung, Institutsliste extern gepflegt) | `docs/integrations/fints.md` | erstellt 27.09.2026 (M11-01 Nachtrag, DK-Produktregistrierung offen M11-42) |
| EBICS (Einreichung von Zahlungsdateien, Gerüst ohne Client) | `docs/integrations/ebics.md` | erstellt 27.09.2026 (V2, M15-01; Vertrag, Initialisierung und Bibliotheksentscheidung offen) |
| Eingehender Webhook für klassifizierte Mails (Bestandsprogramm als Quelle, signiert, idempotent) | `docs/integrations/inbound-mail-webhook.md` | erstellt 01.10.2026 (M20-04, AE38; Entscheidung Übernahme oder Webhook-Quelle offen, AE38-01) |
| Vorlage für Dossiers nach Anhang B | `docs/integrations/DOSSIER-VORLAGE.md` | erstellt 01.10.2026 (AA16-03) |
| Checkliste je Bestandstool (Stand der Dossiers, Läufe, Wissensdatenbank, Entscheidungen) | `docs/integrations/CHECKLISTE-BESTANDSTOOLS.md` | erstellt 01.10.2026 (AA16-03) |

Die Dateinamen sind ein Vorschlag nach dem Muster `docs/integrations/<tool>.md`. Mit Vorliegen aller Dossiers entsteht Version 2.1 des Master-Prompts (Abschnitt 19.3).

## Übersicht der Bestandstools (Stand 01.10.2026, GA09-02)

Quelle ist jeweils das genannte Dossier. Wo der Erhebungslauf nach Anhang B im Bestandsprojekt
aussteht, fehlen Stack und Datenmodell und sind im Dossier als "zu ergänzen durch Betreiber"
markiert. Der Nachweis des Wissensdatenbank-Eintrags je Dossier steht aus (Frage AA16-03 in
`docs/OPEN_QUESTIONS.md`); er wird im Dossier vermerkt, sobald der Betreiber ihn angelegt hat.

| Tool | Zweck | Schnittstelle zur Plattform | Status | Offene Punkte |
| --- | --- | --- | --- | --- |
| Müller FLOW | Prozess und Automatisierung der HVM | keine dokumentiert; Zielbild sind Regeln in `mhvp.automation` | Dossier Entwurf (`dossier-flow.md`) | Anhang-B-Lauf, Prozessliste, Datenmodell (V1, AA16-03) |
| Immoware Hub | Lesespiegel der Immoware24-Exporte, Objektsuche, KI | Drop-Ordner mit Begleitdatei, keine API | Empfehlung ablösen (`immoware-hub.md`), Stilllegung `docs/runbooks/hub-abschaltung.md` | Bestätigung Parser-Abgleich (AA16-02) |
| Mail optimierung | gemeinsames Postfach mit Vorgängen, SLA, Freigaben | Modul `mhvp.communication` und `mhvp.tickets`; eingehender Webhook für klassifizierte Mails (`inbound-mail-webhook.md`) | Empfehlung übernehmen (`mail-optimierung.md`) | Aktionspläne, weitere Gesellschaften, `mail.muellerhv.de` Weiterleitung |
| Übergabeprotokoll | Wohnungsübergaben | Modul `handover` (M30), Importer `uprotokoll_import` | übernommen, Dossier Entwurf (`dossier-uebergabeprotokoll.md`) | Kompatibilität des Exportformats, Stilllegung nach Übernahme der Altprotokolle |
| Objektakte | Objektordner, Dokumentablage | lesende API und Webhooks (`objektakte.md`) | Vertrag M29 Stufe 3 und 4, Dossier (`dossier-objektakte.md`) | interner Aufbau, Kontakt-ID wirkt dort noch nicht, Löschung folgt eigenen Regeln |
| smart-einzug | Lastschrifteinzug, gekoppelt an lexoffice | ausgehende Webhooks `contact.updated`, `contact.mandate_iban_changed`, `invoice.issued` (`smart-einzug.md`, `webhooks.md`) | Sendeseite umgesetzt und getestet (Test `test_ga09_smart_einzug_contact_updated.py`), Empfangsseite unbekannt | Empfangsschnittstelle, Signaturprüfung durch smart-einzug, VPS-Betrieb |

## Kennzeichnung offener Dossierangaben (GAI-118, Stand 02.10.2026)

In den Dossiers der Bestandsprojekte (Müller FLOW, Übergabeprotokoll, smart-einzug) steht jede
Angabe, die nur der Betreiber durch einen Erhebungslauf nach Anhang B des Master-Prompts liefern
kann, einheitlich als sichtbarer Platzhalter `[Betreiber-Erhebung offen, V1 ...]`. Die Suche nach
diesem Text listet alle offenen Stellen. Ein Platzhalter wird nur durch belegte Angaben ersetzt,
nie durch Vermutungen. Verantwortlich: Timo Müller (OPEN_QUESTIONS V1, AA16-03).
