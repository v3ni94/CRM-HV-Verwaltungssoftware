# Dossier: smart-einzug

Stand 27.09.2026. Erhebung nach Anhang B des Master-Prompts (Abschnitt 13.3). Der Quelltext
von smart-einzug liegt dem Plattform-Repo nicht vor; das Projekt läuft laut Abschnitt 13.3 auf
einem separaten VPS, der nicht Teil des Serverumzugs ist. Dieses Dossier fasst zusammen, was
aus `docs/MASTER-PROMPT.md`, `docs/OPEN_QUESTIONS.md` (Punkt V1) und
`docs/integrations/webhooks.md` belegbar ist.

## 1. Zweck

Zahlungseinzug in Verbindung mit lexoffice, das die HVM für Eigentümer- und Kundendaten nutzt
(Abschnitt 13.3, aus der Projektbezeichnung abgeleitet). [Betreiber-Erhebung offen, V1: zu ergänzen durch Betreiber: genauer
Einzugsprozess, Lastschrift- oder Rechnungslauf, betroffene Vertragsarten, Nutzergruppe].

## 2. Datenbestand

Kein Zugriff auf das Datenmodell von smart-einzug. [Betreiber-Erhebung offen, V1: zu ergänzen durch Betreiber:
Datenbank/Storage, Entitäten für Zahlungsempfänger, Einzugsaufträge, lexoffice-Referenzen].

## 3. Schnittstellen

Kein Zugriff auf die tatsächlichen Endpunkte von smart-einzug. Laut Abschnitt 13.3 ist als
Zielbild vorgesehen:

- Kontaktänderungen von Eigentümern werden per Webhook (`contact.updated`) an smart-einzug
  beziehungsweise lexoffice gespiegelt.
- Verwalterhonorar-Rechnungen können als Ausgangsrechnung an lexoffice übergeben werden.

[Betreiber-Erhebung offen, V1: zu ergänzen durch Betreiber: tatsächliche Empfangsschnittstelle von smart-einzug für diese
Webhooks, Authentifizierung, Antwortverhalten, lexoffice-API-Version und Berechtigungen].

## 4. Ablösestatus im CRM

Die Plattform stellt bereits die in Abschnitt 13.3 vorgesehene sendende Seite bereit:

- Allgemeiner ausgehender Webhook-Vertrag (`docs/integrations/webhooks.md`, Abschnitt 12,
  Aufgabe A69): Abonnement je Mandant (`POST /api/v1/tenant/webhooks`), Signatur
  `X-MHVP-Signature` (HMAC-SHA256), Zustellung mit Wiederholung (1 min, 5 min, 30 min, 2 h,
  6 h, 24 h), Zustellprotokoll und manuelle Neuzustellung.
- Ereignis `contact.updated` im Katalog (`mhvp.core.webhooks.EVENT_TYPES`): ausgelöst durch
  `PUT /contacts/{id}` mit tatsächlicher Änderung sowie durch Immoware24-Listenimporte bei
  Rollenänderung; Payload enthält nur die geänderten Feldnamen, keine Werte, keine IBAN,
  keine Namen (Datensparsamkeit laut `docs/integrations/webhooks.md`).
- Ereignis `contact.mandate_iban_changed` für IBAN-Änderungen an einem Bankkonto mit
  SEPA-Mandat, ebenfalls ohne IBAN im Payload.
- Ereignis `invoice.issued` für ausgestellte Verwalterhonorar-Rechnungen (XRechnung), das
  für eine Übergabe an lexoffice als Ausgangsrechnung in Frage kommt
  (`apps/api/src/mhvp/accounting`, Endpunkt
  `POST /accounting/admin-fees/{id}/invoice-issue`).
- Modul `apps/api/src/mhvp/contacts` als Quelle der Kontaktdaten, `apps/api/src/mhvp/billing`
  beziehungsweise `apps/api/src/mhvp/accounting` als Quelle der Verwalterhonorare.

Noch nicht umgesetzt: Ein smart-einzug-spezifischer Empfangsadapter oder eine lexoffice-
API-Anbindung existiert in der Plattform nicht; smart-einzug müsste den allgemeinen
Webhook-Vertrag als Empfänger implementieren, oder die Plattform müsste zusätzlich einen
lexoffice-Client bauen (Abschnitt 13.5 nennt lexoffice separat für Kontakte und
Ausgangsrechnungen als weitere Schnittstelle, ebenfalls noch offen).

## 5. Offene Punkte

- Kein Erhebungslauf nach Anhang B im smart-einzug-Projekt durchgeführt; Zweck, Technik,
  Datenmodell, Schnittstellen und bekannte technische Schulden von smart-einzug sind
  unbekannt.
- Unklar, ob smart-einzug den allgemeinen Webhook-Vertrag (HMAC-Signatur, Wiederholungslogik)
  ohne Anpassung empfangen kann oder ob ein eigener Adapter nötig ist.
- lexoffice als Zielsystem ist in der Plattform noch nicht direkt angebunden (Abschnitt 13.5);
  die Übergabe der Ausgangsrechnung läuft bisher nur als Webhook-Ereignis, nicht als
  vollständige API-Integration.
- Da smart-einzug auf einem separaten, vom Serverumzug ausgenommenen VPS läuft, ist die
  Betriebsverantwortung und der Migrationszeitpunkt gesondert zu klären.
- Empfehlung (anbinden, übernehmen, ablösen) kann erst nach Sichtung des smart-einzug-Projekts
  begründet werden. Nach Abschnitt 13.3 spricht die enge Kopplung an lexoffice für „anbinden“
  statt „übernehmen“; das ist eine vorläufige Einschätzung ohne Repo-Kenntnis.
- Punkt V1 in `docs/OPEN_QUESTIONS.md` bleibt für smart-einzug als offen vermerkt, bis der
  Betreiber den Anhang-B-Lauf im smart-einzug-Projekt ausführt.

## Zusammenfassung in zehn Zeilen

1. smart-einzug ist ein Bestandsprojekt der HVM auf separatem VPS, Quelltext liegt nicht vor.
2. Zweck laut Bezeichnung: Zahlungseinzug in Verbindung mit lexoffice.
3. Datenmodell und tatsächliche Schnittstellen von smart-einzug sind unbekannt.
4. Zielbild ist eine Webhook-Spiegelung von Kontaktänderungen an smart-einzug/lexoffice.
5. Die Plattform hat den allgemeinen, signierten Webhook-Vertrag bereits produktiv (A69).
6. Die Ereignisse `contact.updated` und `contact.mandate_iban_changed` sind bereits verfügbar.
7. `invoice.issued` liefert bereits Verwalterhonorar-Rechnungsdaten für eine mögliche
   Übergabe.
8. Payloads enthalten nach Datensparsamkeitsregel keine IBAN, keine Namen, keine Beträge über
   das Nötige hinaus.
9. Eine direkte lexoffice-API-Anbindung besteht in der Plattform noch nicht.
10. Nächster Schritt: Betreiber führt den Anhang-B-Prompt im smart-einzug-Projekt aus und klärt
    lexoffice-Zugangsdaten (siehe auch Punkt V12 Steuerberater-Rückfragen zu DATEV/E-Rechnung).

## Ergänzung 01.10.2026 (GA09-02): Faktenstand aus dem Repo

Belegt sind nur Master-Prompt Abschnitt 13.3 und die Sendeseite der Plattform
(`docs/integrations/smart-einzug.md`, `docs/integrations/webhooks.md`).

- Zweck: Zahlungseinzug in Verbindung mit lexoffice. Genauer Einzugsprozess: offen, Dossier
  erforderlich (AA16-03).
- Stack: eigenes Projekt auf einem separaten VPS, nicht Teil des Serverumzugs. Sprache,
  Framework, Datenbank und Betrieb: offen, [Betreiber-Erhebung offen, V1, AA16-03].
- Datenmodell: offen, [Betreiber-Erhebung offen, V1, AA16-03].
- Schnittstellen: die Plattform sendet signierte ausgehende Webhooks `contact.updated` (nur
  Kennungen und geänderte Feldnamen, keine Klardaten), `contact.mandate_iban_changed` und
  `invoice.issued` mit stabilem `Idempotency-Key` je Zustellung und Wiederholung bei
  Fehlzustellung. Test: `apps/api/tests/integration/test_ga09_smart_einzug_contact_updated.py`.
  Die Empfangsseite von smart-einzug ist offen, [Betreiber-Erhebung offen, V1, AA16-03].
- Status: Sendeseite umgesetzt, Empfang und Signaturprüfung durch smart-einzug nicht
  bestätigt.
