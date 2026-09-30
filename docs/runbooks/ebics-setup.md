# Runbook EBICS: Einrichtung, INI/HIA-Briefe, Bankschlüsselprüfung

Stand 30.09.2026 (Befund M11-10). EBICS ist nicht angebunden: es gibt keinen EBICS-Client im
Repository, das Gerüst `mhvp.banking.ebics.EbicsSubmitter` lehnt jede Einreichung mit
`MHVP-BANK-0017` ab, der Konnektor für den Kontoauszugsabruf fehlt (Befund M11-01,
Betreiberentscheidung 1 a: nicht umsetzen bis Entscheidung V2). Dieses Runbook beschreibt
das Verfahren, damit die Einrichtung nach der Entscheidung ohne Nacharbeit ablaufen kann.
Freigabetor G2 bleibt geschlossen; kein Schritt hier bewegt Geld.

Die Schritte folgen dem allgemeinen Standardverfahren der Deutschen Kreditwirtschaft. Version
(2.5 oder 3.0), Auftragsarten und Unterschriftsklassen stehen im Vertrag der jeweiligen Bank
und sind vor der Umsetzung aus diesem Vertrag zu belegen (P05). Technische Einzelheiten:
`docs/integrations/ebics.md`.

## 1. Voraussetzungen (vor Beginn prüfen)

| Punkt | Nachweis | Verantwortlich |
| --- | --- | --- |
| Entscheidung V2 (welche Konten, welche Bibliothek) | Eintrag in `docs/OPEN_QUESTIONS.md` V2 | Betreiber |
| EBICS-Vertrag je Konto und Teilnehmer | Vertragsunterlagen der Bank im DMS | Betreiber |
| Zugangsdaten der Bank: Host-ID, Partner-ID, User-ID, URL, freigeschaltete Auftragsarten, Unterschriftsklasse | Bankbrief (Zugangsdaten), im DMS abgelegt | Betreiber |
| Bankbrief mit den Hash-Werten der Bankschlüssel (für Schritt 5) | Papierbrief oder signiertes Dokument der Bank | Betreiber |
| Masterkey der Plattform eingerichtet | `MHVP_MASTER_KEY` gesetzt, Backup verifiziert | Betrieb |

Fehlt ein Punkt, nicht beginnen.

## 2. Schlüssel erzeugen

- Drei Schlüsselpaare je Teilnehmer: Signatur (A005 oder A006), Authentifikation (X002),
  Verschlüsselung (E002), Mindestlänge 2048 Bit.
- Private Schlüssel nur verschlüsselt mit dem Masterkey speichern (wie FinTS-Zugangsdaten,
  Regel M11-05). Nie in das Repository, nie in Logs, nie per E-Mail.
- Ergebnis im Protokoll festhalten: Datum, Person, Teilnehmer, Schlüsselversionen. Keine
  privaten Schlüssel ins Protokoll.

## 3. INI und HIA senden, Briefe erstellen

1. Auftrag `INI` sendet den öffentlichen Signaturschlüssel.
2. Auftrag `HIA` sendet die öffentlichen Schlüssel für Authentifikation und Verschlüsselung.
3. INI-Brief und HIA-Brief erzeugen. Sie enthalten die Hash-Werte der öffentlichen
   Schlüssel, Teilnehmerkennung, Datum und Uhrzeit.
4. Die Hash-Werte auf den Briefen mit den in der Plattform erzeugten Werten vergleichen,
   bevor unterschrieben wird.
5. Briefe von der vertretungsberechtigten Person unterschreiben lassen und an die Bank
   senden (Weg nach Vorgabe der Bank). Kopie ins DMS mit Dokumenttyp Bankkorrespondenz.

Status danach: initialisiert, wartet auf Freischaltung durch die Bank.

## 4. Freischaltung abwarten

Die Bank prüft die Briefe und schaltet den Teilnehmer frei. Die Freischaltung schriftlich
oder im Bankportal bestätigen lassen und das Datum protokollieren. Ohne Freischaltung keine
weiteren Aufträge.

## 5. Bankschlüssel holen und prüfen (Pflicht vor jeder Nutzung)

1. Auftrag `HPB` holt die öffentlichen Schlüssel der Bank.
2. Die Hash-Werte der empfangenen Bankschlüssel Zeichen für Zeichen mit dem Bankbrief aus
   Abschnitt 1 vergleichen. Zwei Personen prüfen (Vier Augen, Produktschutz).
3. Protokoll: wer, wann, welche Hash-Werte, Ergebnis. Bei Abweichung sofort abbrechen, die
   Bank telefonisch über die bekannte Rufnummer (nicht über eine Nummer aus einer E-Mail)
   kontaktieren und keine Datei einreichen.

Ohne dokumentierte Prüfung bleibt die Anbindung gesperrt.

## 6. Test

- Testsystem der Bank nutzen, sofern angeboten.
- Kontoauszugsabruf (Auftragsart laut Vertrag, zum Beispiel für CAMT.053) für einen kurzen
  Zeitraum; Ergebnis gegen den Kontoauszug im Bankportal abgleichen (B09).
- Zahlungsdatei nur nach `docs/runbooks/zahllauf-test.md`, Kundenprotokoll abholen und
  auswerten. Ausführung gilt erst durch den importierten Kontoumsatz als nachgewiesen (D06).

## 7. Freigabe

- Feature-Flag `MHVP_EBICS_PAYMENT_SUBMISSION` je Mandant, Freigabetor G2 je Mandant und
  Abnahme M15 durch den Betreiber. Erst danach den Einreichungsweg des Kontos auf EBICS
  stellen.
- Die Verteilte Elektronische Unterschrift (VEU) bleibt bei Unterschriftsklasse T im
  Bankportal bei den berechtigten Personen; die Plattform meldet nur "eingereicht".

## 8. Schlüsselwechsel, Sperre, Verlust

- Verdacht auf Kompromittierung: Teilnehmer bei der Bank sperren lassen (Sperrauftrag oder
  Telefon nach Vertrag), Schlüssel neu erzeugen, Ablauf ab Schritt 3 wiederholen.
- Geplanter Schlüsselwechsel: nach Vorgabe der Bank, Protokoll wie oben.
- Ausscheiden einer unterschriftsberechtigten Person: Teilnehmer bei der Bank löschen lassen.

## Häufige Fehler

| Fehler | Ursache | Vorgehen |
| --- | --- | --- |
| Bank meldet Teilnehmer unbekannt | Briefe noch nicht verarbeitet oder Kennungen vertauscht | Kennungen mit dem Zugangsbrief vergleichen, Freischaltung bei der Bank erfragen |
| Hash der Bankschlüssel weicht ab | falscher Bankbrief, falsche URL oder Angriff | abbrechen, Bank über bekannte Rufnummer kontaktieren |
| Einreichung mit `MHVP-BANK-0017` abgelehnt | Einreichungsweg nicht freigeschaltet (Normalzustand bis G2) | kein Fehler der Plattform; Freigabe nach Abschnitt 7 |

## Siehe auch

- `docs/integrations/ebics.md` (Verfahren, vorgesehene Datenhaltung, Grenzen)
- `docs/OPEN_QUESTIONS.md` V2 und M11-01
- `docs/runbooks/zahllauf-test.md`
