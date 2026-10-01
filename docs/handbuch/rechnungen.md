# Rechnungen (Invoices)

## Zweck

Das Menü Rechnungen verwaltet Eingangsrechnungen (Rechnungen von Kreditoren an die verwalteten Objekte oder den Verwalteter), Honorarrechnungen und Dauerrechnungen. Aus diesen entstehen offene Posten und Zahlläufe (Kapitel [Buchhaltung](buchhaltung.md)).

Rechnungen durchlaufen einen Prüfprozess:

1. **Erfassung**: Beleg eingehend (automatisch über Belegeingang, manuell hochgeladen oder per E-Mail).
2. **Sachliche Prüfung**: Auftrag, Vertrag, Beschluss und Zuständigkeit geprüft.
3. **Rechnerische Prüfung**: Netto, Steuern, Summen korrekt.
4. **Freigabe**: genehmigende Person bestätigt Voraussetzungen oder lehnt ab.
5. **Buchung**: Forderung und Verbindlichkeit werden gebucht (hinter Gate G1), offener Posten entsteht.

Alle Schritte sind reversibel: Rechnungen können aktualisiert oder mit einer Storno-/Gutschrift korrigiert werden.

## Vorbedingungen

- Berechtigung `accounting:read` und `accounting:create` für die Verwaltung

## Bedienung

Das Menü zeigt eine Tabelle mit Spalten:

- **Rechnungsnummer / Dokumentreferenz**: Nummer und optional Zuordnung (Objekt, Ticket).
- **Kreditor / Empfänger**: Name und IBAN des Ausstellers.
- **Leistungsempfänger**: Objekt oder Einheit oder „Verwaltung".
- **Nettobetrag / Steuerbetrag / Brutto**: Summen im Format 1.234,56 EUR.
- **Rechnungsdatum / Leistungszeitraum**: Ausstellungs- und Leistungszeitraum.
- **Status**: Erfassung (offen), Entwurf (Prüfung), Freigegeben (zur Buchung bereit), Gebucht, Teilweise bezahlt, Bezahlt.
- **Befunde**: Prüf-Hinweise oder Fehler (z. B. „Dublette", „Leistungsort fehlt", „Interessenkonflikt").

Ein Klick auf eine Rechnung öffnet die Detailseite mit allen Prüfschritten.

### Rechnung erfassen

Schaltfläche „Rechnung erfassen" oder Link aus dem Belegeingang (Kapitel [Belegeingang](belegeingang.md)) öffnet ein Formular:

- **Rechnungsnummer** (Pflicht): Nummer auf dem Beleg.
- **Kreditor / Aussteller** (Pflicht): Kontakt mit Rolle Bank / Anbieter (Suchfeld; neue Kontakte möglich).
- **Leistungsempfänger** (Pflicht): Objekt, Einheit oder Verwaltung (Suchfeld).
- **Nettobetrag / USt-Satz / Bruttobetrag** (Pflicht): berechnet.
- **Rechnungsdatum** (Pflicht): Datum im Format TT.MM.JJJJ.
- **Leistungszeitraum**: Zeitraum von / bis (optional; wichtig für Betriebskostenabrechnung).
- **Auftrag / Bestellung** (optional): Freitextfeld oder Verweis auf Ticketnummer.
- **Zahlbedingung** (optional): Zahlungsfrist, Skonto.
- **Belege** (optional): Hochladen von Rechnungskopien, Rechnungsfotos oder Dokumente.

Nach dem Speichern zeigt die Plattform automatische Prüfmerkmale (s. u.) und wechselt zur Detailseite.

### Prüfschritte

#### Sachliche Prüfung

Überprüfung, ob die Rechnung zur Verwaltung passt:

- **Auftrag / Beschluss vorhanden**: Ist die Leistung beauftragt (Ticket, Beschluss, Vertrag)?
- **Interessenkonflikt**: Ist der Aussteller verbunden mit dem Verwalter, Beirat, Eigentümer oder einer Gesellschaft der Gruppe?
- **Zeitraum plausibel**: Liegt der Leistungszeitraum in einem angemessenen Intervall (z. B. nicht 5 Jahre in der Zukunft)?

#### Rechnerische Prüfung

Überprüfung der Zahlen:

- **Netto + Steuern = Brutto**: summiert korrekt.
- **Positionen summieren**: Positionen (Posten) in der Rechnung summieren zum Nettobetrag.
- **Steuersätze plausibel**: Sätze entsprechen dem Ort und der Leistungsart.
- **Skonto berechnet**: bei Frühzahlung oder Abzügen.

Abweichungen werden als Befund angezeigt; die Buchung bleibt möglich, wenn Abweichungen ignoriert oder gelöst werden.

#### Freigabe

Nach der Prüfung gibt eine Person mit Recht `accounting:release` die Rechnung frei. Die Freigabe wird mit Datum, Person, Grund und optional Anhaltspunkten dokumentiert.

### Dublettenprüfung

Die Plattform prüft auf Rechnungsdubletten:

- Gleiche Rechnungsnummer, Betrag und Rechnungsdatum (mögliche Weitergabe).
- Dokumenthash oder Dateigröße und -datum (Dateiinhalt identisch, z. B. PDF mehrmals gemailt).
- Betrag und Kreditor gleich, aber unterschiedliches Datum (Wiederholte Leistung oder Fehler).

Ist eine Dublette erkannt, wird sie als Befund angezeigt; die Buchung kann trotzdem erfolgen, eine Markierung wird empfohlen.

### Storno und Gutschrift

Eine Rechnung wird nicht gelöscht, sondern mit einer Gutschrift oder Stornorechnung korrigiert:

- **Gutschrift**: Minder- oder Teilrückzahlung (z. B. 20 EUR von 100 EUR).
- **Stornorechnung**: Vollständige Rückgängigmachung (100 EUR Storno gegen 100 EUR Rechnung).

Beide werden als neue Rechnungen erfasst, verlinkt mit der Bezugsrechnung und mit der Art „Gutschrift" oder „Storno". Die Differenz entsteht als offener Posten.

## Rechnungstypen

| Typ | Verwendung |
| --- | --- |
| Eingangsrechnung | Kreditoren-Rechnung zur Miete, Betriebskosten, Dienstleistung oder Liegenschaft. |
| Honorarrechnung | Rechnung des Verwalters an eine WEG oder einen Einzeleigentümer (Verwaltungshonorar, Sonderumlage). |
| Dauerrechnung | Wiederkehrende Rechnung (z. B. monatliche Miete, wöchentliche Reinigung). |

## Freigabestufen

- **Entwurf / Prüfung**: Erfassung und Prüfung ohne Freigabe (Stufe offen).
- **Gebucht**: Nach Freigabe durch die sachlich und rechnerisch zuständige Person wird die Forderung / Verbindlichkeit gebucht (hinter Gate G1, Regel E01).
- **Zahlläufe**: Gebuchte Rechnungen mit offenen Posten können in Zahlläufe aufgenommen werden (Kapitel [Buchhaltung](buchhaltung.md)).

## Grenzen

- Rechnungen werden nicht versendet oder gezahlt; sie dokumentieren Ansprüche und Verbindlichkeiten.
- Eine Verknüpfung zu Aufträgen und Tickets erfolgt manuell (Freitextfeld oder Ticketreferenz).
- Im Parallelbetrieb mit Immoware24 werden Rechnungen nur in der Plattform erfasst (kein Rückschreiben).

Weitere Details zur Verarbeitung stehen im Kapitel [Belegeingang](belegeingang.md).

## Prüfhinweise, Kreditoren und Rechnungspläne (30.09.2026)

- **Pflichtangaben**: An der Rechnung werden Leistungsort, USt-IdNr. oder Steuernummer des Ausstellers, weitere Anlagen und der Dienstleistervertrag erfasst. Die Checkliste zeigt je Angabe aus PÜ01, ob sie vorhanden ist. Ein Leistungszeitraum, dessen Ende vor dem Beginn liegt, wird nicht angenommen.
- **Beträge**: Skonto wird nachgerechnet und mit dem angegebenen Betrag verglichen. Anzahlung und Sicherheitseinbehalt mindern den Zahlbetrag, nicht den Aufwand. Reverse Charge und Bauabzugsteuer sind Kennzeichen für die Prüfung durch den Steuerberater.
- **Hinweise**: Die Plattform meldet mögliche verbundene Unternehmen und Interessenkonflikte (Aussteller zugleich Eigentümer, Verwalter oder Beirat), inhaltsgleiche Dateien an anderen Rechnungen und eine gegenüber der Vorversion geänderte IBAN. Die Bewertung trifft die prüfende Person.
- **Gutschriften**: Eine Gutschrift braucht die Ursprungsrechnung. Gebucht wird sie nur, wenn die Ursprungsrechnung gebucht ist und alle Gutschriften zusammen deren Betrag nicht übersteigen.
- **Vertretung**: Ein Prüfschritt kann in Vertretung erfasst werden; dann sind die vertretene Person und der Vertretungsgrund Pflicht. Geprüfte Seiten, Positionen und Anlagen lassen sich einzeln nennen.
- **Kreditoren** (Rechnungen, Schaltfläche „Kreditoren“): Liste je Buchungskreis mit Saldo, offenen Posten und Kontoauszug je Kreditor. Nur Anzeige.
- **Rechnungspläne** (Schaltfläche „Rechnungspläne“): Liste je Buchungskreis, Entwurf erzeugen, Plan beenden mit Datum und Grund, unbenutzten Plan löschen. Fällt der Starttag auf ein Monatsende, bleibt die Fälligkeit am Monatsende. Erzeugt wird immer nur ein ungeprüfter Entwurf.

## Kreditoren (Seite Rechnungen, Kreditoren)

Nach Auswahl des Buchungskreises listet die Seite die Kreditorenkonten mit Saldo. Je Kreditor sind offene Posten und Rechnungen einsehbar, ebenso ein Kontoauszug für einen Zeitraum mit Anfangssaldo, Buchungen (Datum, Beleg, Text, Soll, Haben, Saldo) und Endsaldo. Kreditorenkonten entstehen mit der ersten gebuchten Rechnung. Die Seite ist eine reine Auskunft.

## Rechnungspläne (Seite Rechnungen, Pläne)

Rechnungspläne erzeugen wiederkehrende Rechnungsentwürfe. Die Liste je Buchungskreis zeigt Leistung, Bruttobetrag, Rhythmus (alle n Monate), nächste Fälligkeit und Status.

- "Entwurf erzeugen" legt einen ungeprüften Rechnungsentwurf an. Prüfung, Freigabe und Buchung bleiben getrennte Schritte.
- "Beenden" verlangt ein Enddatum und einen Grund. Ein Plan kann auch gelöscht werden.

## Rechnungspläne bearbeiten, Kreditorenkonten, Prüfangaben am Beleg

Rechnungspläne lassen sich unter "Bearbeiten" ändern (Leistung, Betrag, Rhythmus, Enddatum, Auftragsbezug, Dienstleistervertrag); geändert werden nur künftige Entwürfe. Bei Plänen mit Stichtag am 29. bis 31. zeigt die Liste den Hinweis auf den letzten Tag kürzerer Monate. Auf der Kreditorenseite legt "Kreditorenkonten anlegen" fehlende Konten für alle Dienstleisterverhältnisse des Buchungskreises an. Beim Erfassen einer Rechnung stehen unter "Weitere Angaben zur Prüfung am Beleg" optional Leistungszeitraum, Leistungsort, Steuerangaben des Ausstellers, Anzahlung, Sicherheitseinbehalt, Skonto, Reverse Charge und Bauabzugsteuer bereit; die steuerliche Bewertung bleibt bei Fachpersonal oder Steuerberater.

## Anlagen am Beleg und neuen Rechnungsplan anlegen

Beim Erfassen einer Rechnung können unter "Weitere Angaben zur Prüfung am Beleg" die Dokument-IDs der Anlagen und Seiten des Originals eingetragen werden (mehrere IDs mit Leerzeichen, Komma oder Zeilenumbruch trennen, höchstens 50). Ungültige oder doppelte IDs sperren das Speichern. Unter "Rechnungspläne" legt "Neuen Rechnungsplan anlegen" einen Plan an (Aussteller, Kostenkonto, Leistung, Brutto, Umsatzsteuer, Rhythmus, erste Fälligkeit, optional Enddatum, Auftragsbezug, Dienstleistervertrag). Der Plan erzeugt nur ungeprüfte Rechnungsentwürfe.

## Verwalterhonorar: Status und Buchungsentwurf (01.10.2026)

- Die Liste der Honorarrechnungen lässt sich nach Status filtern (ausgestellt, freigegeben,
  storniert). Eine stornierte Rechnung bleibt mit ihren Dokumenten erhalten; die Korrektur ist
  die Gutschrift mit eigener Nummer, die ebenfalls freigegeben werden kann.
- Für eine freigegebene Rechnung oder Gutschrift legt die Schaltfläche Buchungsentwurf je einen
  Entwurf im Buchungskreis des Zahlers und im Buchungskreis des Verwalters an. Das funktioniert
  nur bei geöffneter Freigabestufe G1 und nach Hinterlegung der Kontenzuordnung
  (Schnittstelle `/accounting/admin-fee-posting-config`). Ohne Kontenzuordnung entsteht kein
  Entwurf. Gebucht wird erst im Journal.
- Die Kontenzuordnung pflegen Sie unter Einstellungen, Buchhaltung, Honorarbuchung: Buchungskreis
  des Verwalters wählen, Forderungs, Erlös und optional Umsatzsteuerkonto aus dem Kontenrahmen
  auswählen, für die Zahlerseite die sechsstelligen Kontonummern eintragen. Lesen mit Buchhaltung
  lesen, Speichern mit Freigaberecht der Buchhaltung. Die steuerliche Behandlung ist offen
  (T04-01) und mit der Steuerberatung zu klären.

## Sachliche Prüfung als Befunde (01.10.2026)

- In der Rechnungsansicht zeigt der Abschnitt "Sachliche Prüfung (Befunde)" den Abgleich gegen
  den verknüpften Auftrag (Angebotsbetrag, Kostengrenze, Status, Dienstleister, Objekt), den
  Dienstleistervertrag, den WEG Beschluss, die Wirtschaftsplanposition (Planansatz), den
  Rechnungsplan (Betrag, Rhythmus) sowie Menge mal Einzelpreis je Position.
- Darunter steht der Zuständigkeitsvorschlag: der am Objekt hinterlegte Objektverwalter.
- Die Befunde sind Hinweise. Der Prüfschritt "sachlich" wird weiterhin von einer Person
  erfasst; nichts wird automatisch freigegeben.
- Auftrag, Beschluss, Planposition und Rechnungsplan werden beim Erfassen über die Schnittstelle
  verknüpft (`work_order_id`, `resolution_id`, `plan_item_id`, `recurring_plan_id`); der
  Freitext Auftragsbezug bleibt möglich.
- Die Toleranzen (Preis, Menge in Prozent) setzt die Verwaltung je Mandant über
  `/accounting/invoice-check-settings`; Standard ist 0, also exakter Abgleich. Die Maske dazu
  steht unter Einstellungen, Buchhaltung, Rechnungsprüfung (Speichern mit dem Recht zur Änderung
  der Mandanteneinstellungen, Werte von 0 bis 100 mit höchstens vier Nachkommastellen).
- In der Rechnungserfassung wählen Sie Auftrag, Beschluss, Wirtschaftsplanposition und
  Rechnungsplan im aufklappbaren Bereich "Verknüpfungen für die sachliche Prüfung" aus. Die
  Listen laden erst beim Öffnen und gelten je Buchungskreis; alle Angaben sind optional.

## E-Rechnung: Prüfergebnis im Belegeingang

Im Belegeingang zeigt der Block "E-Rechnung: Prüfergebnis" Profil, Prüfer, Version, Ergebnis und Meldungen. Die interne formale Prüfung ist kein amtlicher Validator. Ein Reverse Charge Kennzeichen führt zum Hinweis auf einen möglichen Fall des § 13b UStG als gesonderten Freigabepunkt; die Einordnung nimmt der Steuerberater vor.

## Budgetabgleich und Beschlussdeckung

Ist eine Rechnung einer Wirtschaftsplanposition zugeordnet, zeigt die sachliche Prüfung Planansatz, bisher zugeordnete Rechnungen, diese Rechnung und den Rest. Ist ein Beschluss verknüpft, erscheinen Nummer, Datum, Gegenstand und ein Hinweis, ob der Beschluss als wirksam erfasst ist. Alle Angaben sind Hinweise, Freigabe und Prüfschritte bleiben manuell.

## Nummern von Mietrechnungs-Entwürfen

Solange die Freigabestufe G1 geschlossen ist, sind Mietrechnungen und Gutschriften Entwürfe mit Wasserzeichen. Standardmäßig tragen sie eine Entwurfsnummer (ENTWURF-JJJJ-NNNNNN) und verbrauchen die fortlaufende Rechnungsnummer MR nicht. Die reguläre Nummer wird erst bei Ausgabe mit offenem G1 vergeben, ein Entwurf wird nicht umnummeriert. Im Vertrag unter Mietrechnungen kann der Nummernmodus gewählt werden: Entwurfsnummer (Standard), reguläre Nummer auch im Entwurf oder Ablehnung der Ausgabe bei geschlossenem G1. Die Einstufung ist mit Steuerberatung zu klären (OPEN_QUESTIONS AC03-01).
