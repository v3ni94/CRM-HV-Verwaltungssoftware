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
