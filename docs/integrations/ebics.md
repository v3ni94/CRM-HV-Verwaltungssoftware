# EBICS (Einreichung von Zahlungsdateien, V2, M11-01, M15-01)

Stand 27.09.2026. EBICS ist als Einreichungsweg vorbereitet, aber nicht angebunden. Das
Gerüst `mhvp.banking.ebics.EbicsSubmitter` lehnt jede Einreichung mit `MHVP-BANK-0017`
("Einreichungsweg nicht verfügbar") ab und nennt die fehlenden Voraussetzungen. Das
Freigabetor G2 bleibt geschlossen; kein Geld wird bewegt.

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
   Authentifikation X002, Verschlüsselung E002), Mindestlänge 2048 Bit. Private Schlüssel
   werden ausschließlich verschlüsselt mit dem Masterkey der Plattform gespeichert (wie
   FinTS-Zugangsdaten, Regel M11-05), nie im Repository, nie im Log.
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

## Vorgesehene Datenhaltung (noch nicht angelegt)

Tabelle `ebics_subscriber` je Mandant mit RLS: Bankkonto, Host-ID, Partner-ID, User-ID,
URL, EBICS-Version, Status (angelegt, initialisiert, freigeschaltet, gesperrt), verschlüsselte
Schlüssel, Hash der Bankschlüssel, Datum und Prüfer der Bankschlüsselprüfung. Tabelle
`ebics_order` je Einreichung: Auftragsart, Auftragsnummer der Bank, Datei-Prüfsumme,
Kundenprotokoll. Die Migration wird erst nach der Betreiberentscheidung angelegt (keine
Felder auf Vorrat, Regel 0.1.2).

## Einreichung und Rückmeldung

- Einreichung nur für Sammler mit Status `file_generated`, vollständiger Vier-Augen-Freigabe,
  abgelegter Datei mit übereinstimmender Prüfsumme (`payment_batch.file_sha256`).
- Bei Unterschriftsklasse T bleibt die Freigabe im Bankportal (VEU) beim Betreiber; die
  Plattform setzt den Status nur auf "eingereicht", nie auf "ausgeführt".
- Ausführung wird ausschließlich durch den importierten Kontoumsatz nachgewiesen (D06);
  das Kundenprotokoll dient nur der Zuordnung von Ablehnungen.

## Grenzen

- Kein EBICS-Client im Repository, keine Schlüsselerzeugung, keine Bankverbindung.
- Die Abläufe oben beschreiben das Standardverfahren der Deutschen Kreditwirtschaft in
  allgemeiner Form; die konkreten Vorgaben (Version, Auftragsarten, Unterschriftsklassen)
  stehen im Vertrag der jeweiligen Bank und sind vor Umsetzung zu belegen (P05).
