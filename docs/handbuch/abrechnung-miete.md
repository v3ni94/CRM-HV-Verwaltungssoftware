# Abrechnung Miete (Betriebskosten, Eigentümerabrechnung)

## Zweck

Der Bereich Abrechnung (Menü Finanzen) erstellt Betriebskostenabrechnungen für Mieter aus
dem Buchungskreis des Vermieters; die Eigentümerabrechnung (Menü Finanzen, Buchhaltung,
Eigentümerabrechnung) fasst für den Eigentümer eines Mietobjekts oder einen SEV-Eigentümer
Einnahmen, Ausgaben, Honorar, Auszahlungen, offene Forderungen, Kautionen und Liquidität
zusammen.

Beide Abrechnungen entstehen als Entwurf und werden intern von einer zweiten Person
freigegeben. Die Ausgabe an Mieter oder Eigentümer (PDF, Versand) ist bis zur
Freigabestufe G3 gesperrt.

## Betriebskostenabrechnung anlegen

Abrechnung anlegen mit Buchungskreis (des Vermieters), Von und Bis (Abrechnungszeitraum).
Die Detailseite zeigt oben die Abrechnungsfrist orientierend (zwölf Monate nach Ende des
Zeitraums, zu verifizieren) und den Hinweis, dass Kostenpositionen nur mit Grundlage
erfasst werden.

## Kostenpositionen

Position hinzufügen mit Bezeichnung, Betrag, Umlageschlüssel (Umlageschlüssel des Objekts,
zum Beispiel WFL für Wohnfläche) und Grundlage (Pflichtfeld, zum Beispiel Mietvertrag
Anlage Betriebskosten). Heizkosten kommen aus der Messdienstabrechnung und werden als
Position mit dieser Grundlage übernommen; die Plattform verteilt Heizkosten nicht selbst.

Die Nutzer und Leerstände im Zeitraum ergeben sich aus den Mietverträgen der Einheiten
(Kapitel Verträge). Über die Schnittstelle steht zusätzlich die CO₂-Kostenaufteilung für
Wohngebäude nach Stufentabelle bereit.

## Berechnen und Ergebnis

Berechnen erzeugt einen Ergebnis-Snapshot. Die Tabelle Ergebnis je Einheit zeigt je
Einheit und Nutzer Kosten, Vorauszahlungen Soll, Vorauszahlungen gezahlt und Ergebnis
(Nachzahlung oder Guthaben). Kosten, die auf Leerstand entfallen, werden als
Leerstandsanteil Eigentümer ausgewiesen (zum Beispiel Leerstandsanteil Eigentümer:
300,00 EUR). Beispiel: Hausmeister 1.200,00 EUR nach Wohnfläche bei einer ganzjährig
vermieteten Einheit ergibt 1.200,00 EUR für diesen Nutzer.

Die KI-Plausibilität (Prüfung starten) liefert Hinweise mit Bezug auf Position oder
Einheit, Schweregrad (niedrig, mittel, hoch) und Gesamteinschätzung (unauffällig, zu
prüfen, kritisch). Sie nennt keine Beträge und keine Korrekturen; Prüfung und Entscheidung
bleiben bei einer Person.

## Status und Freigabe

| Status | Bedeutung |
| --- | --- |
| Entwurf | Positionen werden erfasst |
| berechnet | Ergebnis-Snapshot liegt vor; Änderungen erfordern erneutes Berechnen |
| intern freigegeben | zweite Person hat freigegeben (Intern freigeben; der Ersteller wird abgewiesen) |
| ausgegeben | Ausgeben mit Datum Zugang beim Mieter; verlangt G3 |
| fällig, gebucht, gesperrt | Folgestatus nach der Ausgabe (Fälligstellung, Buchung des Ergebnisses, Sperre gegen Änderung) |

Nach der Ausgabe ist eine Korrektur nur über Neue Version möglich; die neue Version
verweist auf die vorherige.

## Eigentümerabrechnung

Abrechnung anlegen mit Buchungskreis (Eigentümer eines Mietobjekts oder SEV-Eigentümer),
Von und Bis. Berechnen erstellt den Entwurf aus den gebuchten Werten des Buchungskreises.
Die Blöcke:

- Einnahmen: Mieten, Nebenkostenvorauszahlungen, sonstige Erträge.
- Ausgaben nach Kostenarten.
- Verwalterhonorar als Entwurf aus der Honorareinstellung (Netto, Umsatzsteuer, Brutto).
- Auszahlungen an den Eigentümer.
- Offene Mietforderungen zum Stichtag.
- Kautionen (Fremdgeld): Kautionsbestand und Guthaben der Kautionskonten.
- Freie Liquidität: Bank und Kasse abzüglich Kautionen und offener Verbindlichkeiten.
- Ergebnis: Einnahmen minus Ausgaben minus Honorar.
- Bei SEV zusätzlich die Überleitung zur WEG-Einzelabrechnung: Kostenanteil laut
  WEG-Abrechnung, Hausgeld Soll und gezahlt, Abrechnungsspitze, auf Mieter umgelegt,
  Eigentümerbelastung.

Prüfhinweise listen Auffälligkeiten der Berechnung; ohne Befund erscheint Keine
Auffälligkeiten. Status: Entwurf, berechnet, intern freigegeben. Die
interne Freigabe erteilt eine zweite Person über die Schnittstelle; Ausgabe als PDF und
Versand erst mit G3.

## Häufige Fehler

- Position lässt sich nicht speichern: Grundlage fehlt.
- Ergebnis je Einheit leer: Schlüsselwerte (zum Beispiel Wohnfläche) fehlen für den
  Zeitraum oder es gibt keine Mietverträge im Zeitraum.
- Intern freigeben abgewiesen: Ersteller und Freigebende müssen verschiedene Personen sein.
- Ausgeben abgewiesen: Freigabestufe G3 ist geschlossen.
