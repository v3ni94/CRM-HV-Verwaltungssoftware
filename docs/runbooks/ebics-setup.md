# Runbook EBICS: Einrichtung, INI/HIA-Briefe, Bankschlüsselprüfung

Stand 01.10.2026 (Befund M11-10, ergänzt in Welle 16, Paket AE23). EBICS ist nicht
angebunden: es gibt keine EBICS-Protokollimplementierung im Repository, das Gerüst
`mhvp.banking.ebics.EbicsSubmitter` lehnt jede Einreichung mit `MHVP-BANK-0017` ab. Neu ist
das Grundgerüst für den Kontoauszugsabruf (Regel M11-11): Teilnehmer, Schlüssel, INI/HIA,
Freischaltung, HPB mit Prüfung und Abruf C53 sind in der Plattform abgebildet (Abschnitt 9);
jede Bankaktion endet bis zur Entscheidung V2 und Klärung AE23-01 mit `MHVP-BANK-0050`
("EBICS-Übertragung nicht verfügbar"). Dieses Runbook beschreibt das Verfahren, damit die
Einrichtung nach der Entscheidung ohne Nacharbeit ablaufen kann. Freigabetor G2 bleibt
geschlossen; kein Schritt hier bewegt Geld.

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
  Verschlüsselung (E002). Länge nach DK Krypto LifeCycle EBICS V1.4 (09.07.2025): mindestens
  2.048 Bit, läuft 11/2027 aus; ab 11/2027 mindestens 4.096 Bit. Die Plattform erzeugt
  standardmäßig 4.096 Bit und lehnt ab 01.11.2027 kürzere Schlüssel ab.
- Signaturschlüssel: Die DK empfiehlt Chipkarte oder einen eigenen Datenträger der
  unterschreibenden Person (Sicherheitsempfehlungen für Kunden, Stand 04.05.2026, Kapitel
  3.1.2). Standardvariante der Plattform ist deshalb `external`: nur der öffentliche
  Schlüssel wird hinterlegt oder INI wird als außerhalb der Plattform erledigt bestätigt.
  Die Variante `server` (Plattform erzeugt den Signaturschlüssel) erst nach Entscheidung
  S16-03-02 einschalten.
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

## 9. Bedienung in der Plattform (Grundgerüst, Regel M11-11)

Ort: Bank, Abschnitt "EBICS (Grundgerüst)". API: `/api/v1/banking/ebics`
(`docs/integrations/ebics.md`). Voraussetzungen aus Abschnitt 1 gelten unverändert.

1. Schalter einschalten (Recht `tenant_settings:update`). Variante des Signaturschlüssels
   prüfen: `external` (Standard) oder `server` (nur nach Entscheidung S16-03-02). Die
   Variante gilt für danach angelegte Teilnehmer.
2. Teilnehmer anlegen mit Host-ID, Partner-ID, Teilnehmer-ID und URL aus dem Zugangsbrief der
   Bank, EBICS-Version und Signaturverfahren aus dem Vertrag. Nur `https`-Adressen.
3. "Schlüssel erzeugen": Authentifikation (X002) und Verschlüsselung (E002), in der Variante
   `server` zusätzlich Signatur. Private Schlüssel werden nur verschlüsselt gespeichert und nie
   angezeigt.
4. Variante `external`: öffentlichen Signaturschlüssel (PEM) hinterlegen und INI senden, oder
   "INI extern bestätigen" mit Vermerk (zum Beispiel INI über die Chipkarte im Bankportal).
5. HIA senden. Briefdaten unter `GET /subscribers/{id}/letters` mit dem Ausdruck vergleichen.
   Fehlt der Hash-Wert (`source_required`), keinen Brief an die Bank senden (AE23-02).
6. Nach der Freischaltung durch die Bank: "Freischaltung bestätigen" mit Datum laut Bank.
7. "Bankschlüssel abholen" (HPB). Danach gibt eine zweite Person die beiden Hash-Werte vom
   Bankbrief ein. Bei Abweichung bleibt der Teilnehmer gesperrt (`MHVP-BANK-0053`), weiter
   nach Abschnitt 5 (Bank über die bekannte Rufnummer).
8. "Kontoauszüge abrufen" (C53, BTF `EOP/DE//camt.053/ZIP`). Ergebnis im Auftragsprotokoll:
   importierte, doppelte und übersprungene Dateien. Konten müssen vorher als internes
   Bankkonto mit gleicher IBAN angelegt sein; sonst wird die Datei übersprungen.
9. Schlüsselwechsel: "Schlüssel wechseln" mit Grund. Alte Schlüssel werden ausgemustert, ihr
   privater Teil gelöscht; danach Schritte 4 bis 7 erneut (Wechselaufträge der Spezifikation
   sind nicht umgesetzt, AE23-03).
10. Sperre: "Teilnehmer sperren" mit Grund (endgültig, private Schlüssel werden gelöscht).
    Die Sperre bei der Bank (SPR oder Telefon nach Vertrag) bleibt zusätzlich nötig.

Offene Punkte mit Quellenbedarf (docs/OPEN_QUESTIONS.md): AE23-01 Übertragung
(Bibliothek oder eigene Umsetzung, Spezifikation 3.0.2 hinter Nutzungsbedingungen), AE23-02
Hash-Werte der Briefe und Zeitraumparameter, AE23-03 Schlüsselwechsel und SPR, AE23-04
Bank-Testsystem und Abnahme.

## Häufige Fehler

| Fehler | Ursache | Vorgehen |
| --- | --- | --- |
| Bank meldet Teilnehmer unbekannt | Briefe noch nicht verarbeitet oder Kennungen vertauscht | Kennungen mit dem Zugangsbrief vergleichen, Freischaltung bei der Bank erfragen |
| Hash der Bankschlüssel weicht ab | falscher Bankbrief, falsche URL oder Angriff | abbrechen, Bank über bekannte Rufnummer kontaktieren |
| Einreichung mit `MHVP-BANK-0017` abgelehnt | Einreichungsweg nicht freigeschaltet (Normalzustand bis G2) | kein Fehler der Plattform; Freigabe nach Abschnitt 7 |
| `MHVP-BANK-0050` bei INI, HIA, HPB oder Abruf | keine EBICS-Übertragung installiert (Normalzustand bis V2 und AE23-01) | kein Fehler der Bank; Auftrag steht als fehlgeschlagen im Protokoll |
| `MHVP-BANK-0054` bei der Bankschlüsselprüfung | dieselbe Person hat HPB ausgeführt | zweite Person prüft |
| `MHVP-BANK-0051` | EBICS-Schalter des Mandanten aus | Schalter nach Abschnitt 9 Schritt 1 |

## Siehe auch

- `docs/integrations/ebics.md` (Verfahren, vorgesehene Datenhaltung, Grenzen)
- `docs/OPEN_QUESTIONS.md` V2 und M11-01
- `docs/runbooks/zahllauf-test.md`
