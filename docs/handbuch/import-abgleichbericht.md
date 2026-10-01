# Abgleichbericht im Parallelbetrieb (Immoware24 gegen Plattform)

Stand 26.09.2026. Solange Immoware24 führendes System bleibt, vergleicht die Plattform täglich
die eingelesenen Rohzeilen der Immoware24-Exporte mit den eigenen Werten. Der Bericht liest und
vergleicht nur. Es wird nichts gebucht, ausgeglichen oder korrigiert; jede Abweichung ist ein
Prüfhinweis für die Sachbearbeitung.

## Voraussetzungen

* Im Importassistenten (Importe, Importassistent) sind Exportdateien der Reporttypen Journal
  und Bankumsätze eingelesen. Diese Dateien bleiben als Rohzeilen gespeichert und werden nicht
  übernommen (Abschnitt 13.1). Der Bericht verwendet je Reporttyp die zuletzt eingelesene Datei.
* Die Objekte tragen dieselbe dreistellige Objektnummer wie in Immoware24; ein- und
  zweistellige Nummern der Exporte werden mit Nullen aufgefüllt (81 wird 081).
* Kontonummern der Exporte werden auf sechs Stellen aufgefüllt (1200 wird 001200) und mit den
  Konten des Buchungskreises verglichen. Die Kontoart (Bank, Debitor, Kreditor, Rücklage) kommt
  aus dem Buchungskreis. Ein Quellkonto ohne passendes Plattformkonto wird ausgewiesen, aber
  keiner Kontoart zugeordnet.

## Kennzahlen je Objekt

| Kennzahl | Quelle (Rohzeilen) | Plattform |
| --- | --- | --- |
| Kontosaldo je Konto | Summe der Beträge je Konto bis zum Stichtag (Soll positiv, Haben negativ) | Saldo der gebuchten Buchungssätze bis zum Stichtag (Soll minus Haben) |
| Offene Posten Debitoren | Summe der Salden aller Debitorenkonten | offene Forderungen zum Stichtag (Betrag abzüglich Tilgungen bis zum Stichtag) |
| Offene Posten Kreditoren | Summe der Habensalden aller Kreditorenkonten | offene Verbindlichkeiten zum Stichtag |
| Rücklage | Habensaldo der Rücklagenkonten | Habensaldo der Rücklagenkonten des Buchungskreises |
| Bankstand je IBAN | letzter Saldo der Bankzeilen, ohne Saldospalte die Summe der Umsätze | Schlusssaldo des jüngsten Kontoauszugs bis zum Stichtag, ohne Auszug die Summe der Umsätze |
| Zahlungseingänge je IBAN | Summe der Gutschriften im Zeitraum der Bankzeilen | Summe der Gutschriften der Bankumsätze im selben Zeitraum |

Die Differenz ist immer Plattform minus Quelle. Fehlt eine Seite (Objekt, Konto oder Bankkonto
nicht vorhanden), bleibt die Differenz leer und der Hinweis nennt den Grund.

## Bedienung

* Importe, Abgleichbericht Parallelbetrieb: Liste aller Berichte mit Stichtag, Auslöser
  (täglicher Lauf oder manuell), Anzahl Objekte und Abweichungen, CSV-Download.
* "Bericht jetzt erstellen" startet den Abgleich sofort; ohne Stichtag gilt das jüngste
  Buchungsdatum der Rohzeilen. Zeilen nach dem Stichtag werden nicht berücksichtigt.
* Im Bericht zeigt der Filter "Nur Abweichungen anzeigen" die Zeilen mit Differenz oder
  fehlender Seite. Rohzeilen, die nicht lesbar waren (Objektnummer fehlt, Betrag nicht lesbar),
  stehen als Hinweise über der Tabelle.
* Die CSV-Datei (Semikolon, Beträge 1.234,56, UTF-8) enthält alle Zeilen mit Objekt, Kennzahl,
  Schlüssel, Quelle, Plattform, Differenz, Abweichung und Hinweis.
* Der tägliche Lauf erfolgt automatisch um 05:30 Uhr (Betreiber-Einstellung
  `MHVP_IMPORT_RECONCILIATION_TIME`); Mandanten ohne Rohzeilen werden übersprungen.

## Spaltenzuordnung

Die Spaltennamen der Immoware24-Exporte sind nicht festgelegt. Standard: Journal mit `Objekt`,
`Konto`, `Datum`, `Betrag` (ersatzweise `Soll` und `Haben`); Bankumsätze mit `Objekt`, `IBAN`,
`Datum`, `Betrag`, optional `Saldo`. Weichen die Exporte ab, wird die Zuordnung je Mandant über
die API `PUT /api/v1/imports/reconciliation-reports/columns` hinterlegt (Feld gegen
Spaltenüberschrift); `GET .../columns` zeigt Standard, aktuelle Zuordnung und Felder.

## Rechte

Lesen mit `ai:read`, Bericht erstellen und Spaltenzuordnung ändern mit `ai:create`. Der
Bericht ändert keine Buchungen; für Korrekturen gelten die Regeln der Buchhaltung (Storno statt
Überschreiben).

## Vollimport mit Stichtag und Abgleichbericht je Entität (Nachtrag 27.09.2026, M8-01, M8-02, V9)

Neben dem täglichen Abgleich der Rohzeilen gibt es den Vollimport unter Importe, "Vollimport
mit Stichtag und Abgleichbericht" (`/importe/vollimport`, API
`/api/v1/imports/immoware24/vollimport`). Er belegt den Vollimport des Bestands (67 Objekte,
869 Einheiten) mit einem Abgleichbericht Soll (Zeilen der Datei) gegen Ist (Datensätze in der
Plattform) und ist beliebig wiederholbar.

### Exporttypen und erwartete Kopfzeilen

| Exporttyp | Pflichtspalten | Weitere erkannte Spalten | Schlüssel |
| --- | --- | --- | --- |
| Objektdaten | Objekt-Nummer, Objekt, Verwaltungsart, VE-Nummer | Gebäude, VE-Beschreibung, VE-Lage, aktueller Eigentümer, aktueller Mieter, vereinbarter Zahlbetrag | Objekt-Nummer, Objekt-Nummer/VE-Nummer |
| Kontaktlisten (Eigentümer, Mieter, Sonstige, Banken, Dienstleister) | id, Name | Briefanrede, Benutzername, Adresse, Hausnummer, Stadt, PLZ, Staat, Land, Landesvorwahl, Vorwahl, Telefonnummer, E-Mail, IBAN | id (Immoware24-Kontakt-ID) |
| Adressliste | Objektnummer | Straße, Hausnummer, PLZ, Ort | Objektnummer |
| Bankumsätze | Objekt, IBAN, Betrag | Datum, Saldo | keiner (nur Vorprüfung, Einlesen über den Importassistenten) |
| Saldenliste | Objekt-Nummer, VE-Nummer, Saldo | Vertragsart, Name | Objekt-Nummer/VE-Nummer/Vertragsart/Name |
| Mietverträge | Objektnummer, Einheitennummer, Kontakt-ID Mieter, Mietbeginn | Vertragsnummer, Mietende, Miete | Vertragsnummer, sonst Objektnummer/Einheitennummer/Mietbeginn |
| Eigentümerverträge | Objektnummer, Einheitennummer, Kontakt-ID Eigentümer, Beginn | Vertragsnummer, Eigentumsübergang (Grundbuch), Nutzen-/Lastenwechsel, Ende, Hausgeld, SEV | Vertragsnummer, sonst Objektnummer/Einheitennummer/Beginn |

Abweichende Schreibweisen der Kopfzeilen (Groß- und Kleinschreibung, Leerzeichen, Bindestriche,
Umlaute) werden toleriert; `GET .../vollimport/exporttypen` listet die Spalten je Exporttyp.
Die Kopfzeilen der Saldenliste sind eine Annahme, bis der Betreiber den echten Export liefert
(offener Punkt V9).

### Ablauf

1. Dateien wählen; der Exporttyp wird aus dem Dateinamen vorgeschlagen und ist je Datei
   änderbar. Stichtag eintragen (V9); der Lauf und der Bericht tragen dieses Datum.
2. Vorprüfung: ohne Datenbankzugriff je Datei Zeichensatz (UTF-8, UTF-8 mit BOM,
   Windows-1252, UTF-16), Trennzeichen, Spaltenabgleich gegen die erwarteten Kopfzeilen
   (fehlende Pflichtspalten, fehlende optionale Spalten, unbekannte Spalten), Zeilenzahl,
   Dubletten je Schlüssel (bei Objektdaten nur, wenn dieselbe Einheit mit abweichendem Inhalt
   mehrfach vorkommt), fehlende Pflichtfelder je Zeile und die SHA-256-Prüfsumme der Datei.
3. Trockenlauf: dieselben Importer wie die Listenimporte laufen in einer zurückgerollten
   Transaktion. Die Vorschau zeigt je Entität (Objekte, Einheiten, Kontakte, Adressen), was
   angelegt, unverändert gelassen oder als Konflikt gemeldet würde; der Abgleich wird auf dem
   Zwischenstand berechnet. Es wird nichts gespeichert.
4. Übernehmen und abgleichen: Import wie beim Trockenlauf, dann Abgleich. Der Lauf wird als
   Importlauf (`immoware24:vollimport`, Rücknahme wie bei den Listenimporten) und als
   Vollimport-Lauf mit Stichtag, Dateien mit Prüfsumme, Zählern, Bericht und Laufzeit
   gespeichert. Ein fehlgeschlagener Vorprüfungsschritt bricht vor jedem Schreiben ab.
5. Nur Abgleich: kein Import, nur der Vergleich der Dateien mit dem aktuellen Bestand,
   ebenfalls gespeichert. Damit lässt sich der Vollimport jederzeit erneut belegen.

### Abgleichbericht

Je Entität: Soll, Ist, übereinstimmend und die Differenzliste mit
* fehlend (in der Datei, nicht in der Plattform, mit Grund, zum Beispiel "nicht dreistellig"),
* doppelt (mehrere Plattformdatensätze zum selben Schlüssel),
* abweichend (Felder mit Soll und Ist: Objektname, Verwaltungsart, Einheitenbezeichnung,
  Lage, Kontaktrolle, exportierter Name, gefüllte Adressfelder),
* zusätzlich (Plattformdatensätze aus Immoware24, die nicht in der Datei stehen; keine
  Differenz der Datei, nur Hinweis).

Der Vollimport gilt als belegt, wenn die Summe der Differenzen 0 ist. Bericht als JSON
(`GET .../vollimport/{id}`) und als PDF-Entwurf (`GET .../vollimport/{id}/pdf`, ohne
Briefbogen, gekennzeichnet als Entwurf).

### Wiederholter Import

Schlüssel sind die Immoware24-Objektnummer (dreistellig, `source_id`), die Einheit
(`<Objekt>/<VE>`) und die Kontakt-ID (`external_ids.immoware24`). Ein zweiter Lauf mit
denselben Dateien legt nichts doppelt an (alles "unverändert"). Mit der Option "Vorhandene
Datensätze aktualisieren" folgen Objektname, Einheitenbezeichnung und Lage der Datei; die
Änderungen stehen im Bericht unter "Aktualisierte Felder". Die Verwaltungsart eines
vorhandenen Objekts wird nie durch einen Import geändert (Konflikt bleibt gemeldet).

### Eröffnungssalden (Entwurf, Gate G1)

Aus einer Saldenliste entsteht je Zeile ein Eröffnungssalden-Vorschlag: Objekt, Einheit,
Vertragsart, Name, Saldo und, wenn zum Stichtag genau ein passender Vertrag auf der Einheit
besteht, dessen Kennung. Es wird nichts gebucht (Regel 0.1.1, B01); die Liste ist ein
Prüfstand für die Eröffnungsbuchungen nach Freigabe von G1 und nach Prüfung je Vertrag.
Ein Eintrag steht auf "zugeordnet", wenn zum Stichtag genau ein Vertrag der Einheit (bei
mehreren Verträgen: der Vertragsart, sonst des exportierten Namens) besteht, sonst auf
"offen" mit Grund. Werden die Vertragslisten im selben Lauf übernommen, sind die Einträge
direkt den neuen Verträgen zugeordnet.

### Vertragslisten (Nachtrag 27.09.2026, Fortsetzung M8-01, M8-02)

Die Exporttypen Mietverträge und Eigentümerverträge werden nach Objekten und Kontakten
übernommen (Eigentümerverträge vor Mietverträgen). Die Spaltenbezeichnungen entsprechen den
Zielfeldern des Importassistenten (Reporttypen Mietverträge, Eigentümerverträge); die echten
Kopfzeilen der Immoware24-Exporte sind nicht spezifiziert und werden beim ersten Lauf über die
Vorprüfung sichtbar (M8-01).

* Zuordnung: Partei über die Kontakt-ID der Kontaktlisten (`external_ids.immoware24`,
  Mehrpersonenparteien aus M8-04 werden erkannt), Einheit über Objektnummer und
  Einheitennummer. Fehlt Objekt, Einheit oder Kontakt, bleibt die Zeile "ungültig" mit Grund;
  es wird nichts geraten.
* Schlüssel: die Immoware24-Vertragsnummer (Tabelle `import_external_key`, Migration 0204),
  ohne Vertragsnummer Objekt, Einheit, Vertragsart und Beginn. Ein zweiter Lauf legt nichts
  doppelt an (alles "unverändert"); ein vorhandener Vertrag mit anderer Partei ist ein
  Konflikt und wird nie überschrieben. Vertragsbeträge werden nie durch einen Import geändert
  (Abweichungen stehen im Abgleich).
* Laufzeiten: Beginn und Ende aus der Datei; bei Eigentümerverträgen Eigentumsübergang und
  Nutzen-/Lastenwechsel, fehlt die Spalte Eigentumsübergang, gilt der Beginn (Hinweis im
  Bericht, je Vertrag zu prüfen).
* Miete und Hausgeld werden als Vertragsbeträge (`rent` beziehungsweise `hoa_fee`, Steuersatz
  0, monatlich zum 1.) übernommen. Es wird nichts gebucht: importierte Verträge tragen die
  Quelle `immoware24:vollimport` und warten auf die Freigabe der Geschäftsführung (Verträge,
  Freigabe); der Sollstellungslauf überspringt sie bis dahin.
* Regeln der Plattform: in reinen WEG-Objekten wird kein Mietvertrag angelegt (M5-03, Zeile
  ungültig mit Grund); in Objekten "WEG mit SE-Verwaltung" braucht ein Mietvertrag ein Eigentum
  mit SEV, das aus der Spalte SEV (ja, x, 1) oder aus einem Mietvertrag derselben Einheit in
  der hochgeladenen Mietvertragsliste abgeleitet wird; ein Eigentümervertrag in einem
  Mietverwaltungsobjekt wird als Vermieter (Eigentümer des Objekts) erfasst, nicht als
  Vertrag; ein Mietvertrag in einem Mietverwaltungsobjekt braucht diesen Vermieter.
* Abgleich je Vertragsliste: Soll (Zeilen), Ist (Verträge der Vertragsart auf den Objekten der
  Datei), übereinstimmend, fehlend, doppelt, abweichend (Partei, Ende, Miete oder Hausgeld
  zum Stichtag). Zusätzlich "je Objekt": Anzahl Soll und Ist sowie Summe der Sollmieten
  beziehungsweise des Hausgelds aus der Datei gegen die zum Stichtag gültigen Vertragsbeträge
  der Plattform, mit Kennzeichnung der abweichenden Objekte (Filter "Nur Abweichungen
  anzeigen"). Die Referenzzahlen aus Immoware24 (M8-02) können damit je Objekt gegen die
  Datei und gegen die Plattform geprüft werden.

### Rechte und Grenzen

Vorprüfung, Trockenlauf, Abgleich und Übernahme mit `ai:create` sowie `properties:create`,
`contacts:create`, `contracts:create`; Lesen mit `ai:read`. Maximal 20 MB je Datei.
Bankumsätze sind nicht Teil des Vollimports: sie werden nur vorgeprüft und über den
Importassistenten als Rohzeilen eingelesen. Die namensbasierte Zuordnung aus der Objektliste
(`mhvp.imports.zuordnung`) bleibt als Alternative ohne Vertragslisten bestehen.

### Messwert mit synthetischem Bestand

Synthetischer Bestand mit 67 Objekten und 869 Einheiten aus den Beispielstrukturen der Tests
(`tests/synthetic_immoware.py`): `tests/integration/test_vollimport.py` führt Vorprüfung,
Trockenlauf, Übernahme, zweiten Lauf und Aktualisierung durch; Differenzen 0. Die gemessene
Laufzeit am 27.09.2026 im Entwicklungscontainer: Übernahme mit Abgleich rund 31 Sekunden,
zweiter Lauf ohne Änderungen rund 6 Sekunden, reiner Abgleich rund 1 Sekunde
(`docs/plans/M8.md`). Die Messung mit den echten Exporten der HVM steht aus (M8-01).

## Objektzuordnung

Ist Ihre Mitgliedschaft auf einzelne Objekte beschränkt, zeigt der Abgleichbericht nur diese
Objekte samt ihren Zeilen und Summen. Hinweise zu fremden Objekten werden ausgeblendet. Die
Immoware24 Datei- und Vollimporte wirken mandantenweit und stehen nur Mitgliedern ohne
Objektzuordnung zur Verfügung.
