# EBICS (Einreichung von Zahlungsdateien, V2, M11-01, M15-01)

Stand 01.10.2026 (Welle 16, Paket AE23). EBICS ist als Einreichungsweg vorbereitet, aber
nicht angebunden. Das Gerüst `mhvp.banking.ebics.EbicsSubmitter` lehnt jede Einreichung mit
`MHVP-BANK-0017` ("Einreichungsweg nicht verfügbar") ab und nennt die fehlenden
Voraussetzungen. Das Freigabetor G2 bleibt geschlossen; kein Geld wird bewegt.

Neu seit 01.10.2026: ein Grundgerüst für den Kontoauszugsabruf (Abschnitt "Grundgerüst
Kontoauszugsabruf" unten, Regel M11-11). Es verwaltet Teilnehmer und Schlüssel und importiert
C53-Abrufe, spricht aber nur über eine Übertragungsschnittstelle mit der Bank, für die noch
keine geprüfte Implementierung installiert ist.

## Betreiberentscheidung (V2, offen)

- Für welche Konten (Bankliste V2) soll EBICS statt Datei-Upload oder FinTS genutzt werden?
  Die Hauptbanken benötigen einen EBICS-Vertrag je Konto, Vorlauf mehrere Wochen.
- Client-Bibliothek: `fintech` von joonis (Python, EBICS 2.5 und 3.0, Verteilte
  Elektronische Unterschrift, SEPA) ist lizenzpflichtig (Lizenzschlüssel je Installation,
  laufende Kosten). Sie ist nicht installiert und darf ohne Entscheidung des Betreibers nicht
  in `pyproject.toml` aufgenommen werden. Alternativen (eigene Implementierung des
  EBICS-Protokolls, andere Bibliothek, Bankportal-Upload) sind zu bewerten. Entscheidung
  eintragen in `docs/OPEN_QUESTIONS.md` unter V2.

## Ablauf der Anbindung

1. Vertrag: EBICS-Vertrag mit der Bank je Konto und je Teilnehmer abschließen. Die Bank
   übermittelt Host-ID, Partner-ID (Kunden-ID), User-ID (Teilnehmer-ID), EBICS-URL und die
   freigeschalteten Auftragsarten (CCT für pain.001, CDD für pain.008 CORE; in EBICS 3.0 die
   entsprechenden BTF-Kennungen) sowie die Unterschriftsklasse (E für Einzelunterschrift,
   A/B für gemeinsame Unterschrift, T für Transport ohne Unterschrift).
2. Schlüssel erzeugen: drei Schlüsselpaare des Teilnehmers (Signatur A005 oder A006,
   Authentifikation X002, Verschlüsselung E002), Mindestlänge 2.048 Bit, ab 11/2027
   4.096 Bit (DK Krypto LifeCycle EBICS V1.4; Standard der Plattform 4.096 Bit). Private
   Schlüssel werden ausschließlich verschlüsselt mit dem Masterkey der Plattform gespeichert
   (wie FinTS-Zugangsdaten, Regel M11-05), nie im Repository, nie im Log. Der
   Signaturschlüssel bleibt in der Standardvariante bei der unterschreibenden Person
   (Regel M11-11).
3. Initialisierung: Auftrag `INI` (Signaturschlüssel) und `HIA` (Authentifikations- und
   Verschlüsselungsschlüssel) an die Bank senden. Danach INI-Brief und HIA-Brief ausdrucken
   (Hash-Werte der öffentlichen Schlüssel), unterschreiben und per Post an die Bank senden.
4. Freischaltung: die Bank prüft die Briefe und schaltet den Teilnehmer frei (Status
   "bereit", zuvor "initialisiert, wartet auf Freischaltung").
5. Bankschlüssel: Auftrag `HPB` holt die öffentlichen Bankschlüssel. Die Hash-Werte sind
   gegen den Bankbrief zu prüfen und die Prüfung ist zu protokollieren (wer, wann, Ergebnis).
   Ohne diese Prüfung keine Einreichung.
6. Test: mit dem Bank-Testsystem eine Datei aus dem Runbook `docs/runbooks/zahllauf-test.md`
   einreichen, Kundenprotokoll (`HAC` oder `PTK`) abholen und auswerten.
7. Freigabe: Feature-Flag `MHVP_EBICS_PAYMENT_SUBMISSION` je Mandant, Freigabetor G2 je
   Mandant, Abnahme M15 durch den Betreiber. Erst danach `submission_channel = ebics` in
   der Konfiguration des Bankkontos (`PUT /api/v1/banking/payment-bank-config/{account}`).

## Grundgerüst Kontoauszugsabruf (AE23, Regel M11-11)

Quellen, frei abrufbar auf ebics.de und am 01.10.2026 geprüft:

| Quelle | Inhalt, der umgesetzt ist |
| --- | --- |
| DK, Krypto LifeCycle EBICS, Version 1.4 vom 09.07.2025 | RSA für alle Schlüsselpaare mindestens 2.048 Bit (läuft 11/2027 aus), ab 11/2027 mindestens 4.096 Bit; TLS ab Version 1.2; EBICS 2.4 ausgelaufen seit 11/2023 |
| DFÜ-Abkommen Anlage 3, Version 26.11 vom 09.04.2026, Kapitel 9.2.1 und 9.2.2 (Seiten 808 bis 810) | C53 = BTF `EOP/DE//camt.053/ZIP`, ZIP mit allen abholbereiten camt.053 des Kunden, Zip32 und Zip64, Dateinamen `JJJJ-MM-TT_C53_<Konto>_<WWW>_<ID>.xml` |
| DFÜ-Abkommen Anlage 3, Seiten 697 und 698 | eine camt-Nachricht je Konto; Teilung großer Auszüge über die Seitennummer bei gleicher Auszugs-ID |
| DK, EBICS Sicherheitsempfehlungen für Kunden, Stand 04.05.2026, Kapitel 3.1 und 3.2 | Signaturschlüssel beim Teilnehmer (Chipkarte empfohlen), Authentifikations- und Verschlüsselungsschlüssel bei Portal-Lösungen beim Betreiber, Sperre mit SPR, gemeinschaftliche Zeichnung empfohlen |

Die EBICS-Spezifikation 3.0.2 selbst ist auf ebics.de nur nach Zustimmung zu den
Nutzungsbedingungen abrufbar. Diese Zustimmung ist für das Repository nicht erteilt worden.
Daher baut die Plattform keine EBICS-Nachricht selbst (offene Fragen AE23-01 bis AE23-04).

Datenhaltung (Migration 0379, RLS je Mandant):

- `ebics_tenant_setting`: Schalter `enabled` (Standard aus), Variante des
  Signaturschlüssels `signature_key_mode` (`external` Standard, `server` vorbereitet).
- `ebics_subscriber`: Host-ID, Partner-ID, Teilnehmer-ID, URL (nur https), EBICS-Version
  (2.5 oder 3.0), Signaturverfahren (A005 oder A006), Schlüssellänge, Zustand und je Schritt
  Zeitpunkt und Person.
- `ebics_key`: öffentliche Schlüssel von Teilnehmer und Bank, private Schlüssel nur
  verschlüsselt (`EncryptedText`), Hash-Wert der Übertragung für den Brief, interner SHA-256
  des öffentlichen Schlüssels, Ausmusterung mit Zeit, Person und Grund.
- `ebics_order`: Protokoll aller Aufträge (INI, HIA, HPB, C53) mit Ergebnis oder Fehlercode.

Zustände: `created`, `keys_ready`, `initialised` (INI und HIA erledigt), `activated`
(Freischaltung bestätigt), `bank_keys_received` (HPB), `ready` (Bankschlüssel geprüft),
`suspended` (endgültig).

API (`/api/v1/banking/ebics`, Lesen mit `accounting:read`, Aktionen mit `banking:approve`,
Schalter mit `tenant_settings:update`):

| Methode und Pfad | Zweck |
| --- | --- |
| `GET /status` | Schalter, Variante, Übertragung verfügbar, Schlüsselpolitik, Quellen, offene Fragen |
| `PUT /settings` | Schalter und Variante setzen |
| `GET /subscribers`, `POST /subscribers`, `GET /subscribers/{id}` | Teilnehmer, mit Schlüsseln und den letzten 20 Aufträgen |
| `POST /subscribers/{id}/keys` | Schlüssel erzeugen; bei vorhandenen Schlüsseln Wechsel mit Pflichtgrund |
| `POST /subscribers/{id}/signature-key` | öffentlichen Signaturschlüssel hinterlegen (Variante extern) |
| `POST /subscribers/{id}/ini`, `POST /subscribers/{id}/ini/external`, `POST /subscribers/{id}/hia` | Initialisierung |
| `GET /subscribers/{id}/letters` | Daten für INI- und HIA-Brief (Exponent, Modulus, Hash-Wert der Übertragung) |
| `POST /subscribers/{id}/activation` | Freischaltung durch die Bank mit Datum bestätigen |
| `POST /subscribers/{id}/hpb`, `POST /subscribers/{id}/bank-keys/verify` | Bankschlüssel holen und durch eine zweite Person prüfen |
| `POST /subscribers/{id}/statements` | Abruf C53 mit Import |
| `POST /subscribers/{id}/suspend` | lokale Sperre (endgültig) |

Fehlercodes: `MHVP-BANK-0050` Übertragung nicht verfügbar, `0051` Schalter aus, `0052`
falscher Zustand, `0053` Hash-Wert weicht ab, `0054` Prüfung durch dieselbe Person, `0055`
Hash-Wert fehlt, `0056` Bank hat den Auftrag abgelehnt.

Übertragung: `mhvp.banking.ebics_transport.EbicsTransport` mit `send_ini`, `send_hia`,
`fetch_bank_keys`, `download` und `letter_hash`. Standard ist `UnavailableEbicsTransport`.
Eine Implementierung (lizenzierte Bibliothek oder eigene, gegen die Spezifikation geprüfte
Umsetzung) wird erst nach Entscheidung V2 und Klärung AE23-01 angebunden; sie ist für
Nachrichtenaufbau, Signatur, Verschlüsselung, Quittung und die Hash-Werte der Briefe
verantwortlich. Tests nutzen den Testdoppel `apps/api/tests/ebics_fake.py` ohne Netz.

## Einreichung und Rückmeldung

- Einreichung nur für Sammler mit Status `file_generated`, vollständiger Vier-Augen-Freigabe,
  abgelegter Datei mit übereinstimmender Prüfsumme (`payment_batch.file_sha256`).
- Bei Unterschriftsklasse T bleibt die Freigabe im Bankportal (VEU) beim Betreiber; die
  Plattform setzt den Status nur auf "eingereicht", nie auf "ausgeführt".
- Ausführung wird ausschließlich durch den importierten Kontoumsatz nachgewiesen (D06);
  das Kundenprotokoll dient nur der Zuordnung von Ablehnungen.

## Grenzen

- Keine EBICS-Protokollimplementierung im Repository und keine Bankverbindung; Schlüssel,
  Zustände und der Import von C53-Abrufen sind vorhanden (Grundgerüst oben).
- Der Hash-Wert für INI-Brief, HIA-Brief und Bankbrief kommt ausschließlich aus der
  Übertragung; ohne sie zeigt die Plattform keinen Hash-Wert (`source_required`) und die
  Bankschlüsselprüfung ist gesperrt.
- Der Briefaufbau (Layout, Unterschriftsfelder) ist nicht nachgebildet; die Plattform liefert
  nur die Daten.
- Die Abläufe oben beschreiben das Standardverfahren der Deutschen Kreditwirtschaft in
  allgemeiner Form; die konkreten Vorgaben (Version, Auftragsarten, Unterschriftsklassen)
  stehen im Vertrag der jeweiligen Bank und sind vor Umsetzung zu belegen (P05).
