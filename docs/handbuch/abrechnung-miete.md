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

### Bevollmächtigte

Hat der Mieter im Kontakt einen Bevollmächtigten mit Zustellregel, folgen die
Abrechnungsschreiben dieser Regel: bei "beide" entsteht je Empfänger ein Schreiben, das
Schreiben an den Bevollmächtigten trägt die Zeile "für <Vollmachtgeber>" und ist mit beiden
Kontakten verknüpft. Erhält nur der Bevollmächtigte, entsteht nur dieses Schreiben
(Betreiberentscheidung 27.09.2026, M23-07; Zugangswirkung anwaltlich zu klären).

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

## Verbrauchsinformation (§ 6a HeizkostenV)

Die monatliche Verbrauchsinformation je Einheit wird aus den Monatsverbräuchen des
Messdienstes erzeugt (Modul Messdienstleister, Periodenverbräuche Heizung und Warmwasser je
Kalendermonat). Sie ist in drei Stufen geschaltet, alle Standard aus:

1. Einstellungen, Mandant, Verbrauchsinformation: Monatsjob aktivieren. Dort stehen auch
   der Schalter für die Portalbenachrichtigung und die Bestätigung, dass die Vorlage geprüft
   ist. Ohne diese Bestätigung sehen Mieter im Portal nichts.
2. Objektseite, Abschnitt Verbrauchsinformation: Schalter je Objekt.
3. Der Monatsjob läuft am ersten Werktag (Montag bis Freitag, Feiertage werden nicht
   berücksichtigt) für den Vormonat. Der Knopf Monat jetzt erzeugen erzeugt einen Monat von
   Hand, zum Beispiel nach einem verspäteten Abruf beim Messdienst.

Je Einheit und Monat entsteht genau ein Datensatz mit Werten (Heizung, Warmwasser, Vormonat,
Vorjahresmonat, Durchschnitt im Objekt), Datengrundlage, fehlenden Angaben und einem PDF im
Dokumentenbestand (nur intern sichtbar). Ein erneuter Lauf überschreibt nichts; ein bereits
gespeicherter Monat wird übersprungen. Fehlende Verbräuche bleiben fehlend und werden im
Abschnitt als "ohne Verbrauch" gezählt, geschätzte Werte sind gekennzeichnet.

Die Liste "Vom Betreiber zu verifizieren" nennt die Inhalte des § 6a Abs. 3 HeizkostenV, die
die Spezifikation nicht festlegt (Energiemix, Emissionen, Kostenangaben, Vergleichsgruppe,
Zustellweg). Sie werden nicht erfunden und Mietern nicht angezeigt; die Entscheidung ist in
`docs/OPEN_QUESTIONS.md` unter H03 festgehalten. Das Portal ist kein Nachweis der
Zustellung; der dokumentierte Ersatzprozess mit dem Messdienst bleibt bis zur Freigabe
bestehen.

## Häufige Fehler

- Position lässt sich nicht speichern: Grundlage fehlt.
- Ergebnis je Einheit leer: Schlüsselwerte (zum Beispiel Wohnfläche) fehlen für den
  Zeitraum oder es gibt keine Mietverträge im Zeitraum.
- Intern freigeben abgewiesen: Ersteller und Freigebende müssen verschiedene Personen sein.
- Ausgeben abgewiesen: Freigabestufe G3 ist geschlossen.

## Anschreiben, Zugang und Belegeinsicht

- Unterjährige Abrechnung: beim Anlegen "Unterjährige Abrechnung" ankreuzen und den Zweck
  angeben. Ohne Zweck wird ein Zeitraum unter zwölf Monaten abgewiesen.
- Im Entwurf lassen sich Kostenpositionen und Kopfdaten ändern oder entfernen. Nach der
  Berechnung geht das nur über eine neue Version; der Differenzbericht zeigt die Änderungen
  je Mieter.
- Abschnitt "Anschreiben und Zugang je Mieter": Vorschau als PDF, Ablage als Entwurf je
  Mieter mit Kostenaufstellung. Nach der internen Freigabe wird je Mieter der Zugang mit
  Versandart, Datum und Nachweis erfasst. Die angezeigte Einwendungsfrist ist eine
  Orientierung und je Fall zu prüfen.
- Belegeinsicht: Anfragen der Mieter werden über die API erfasst (Eingang, Weg, Umfang),
  danach Bereitstellung, Schwärzungsvermerk und Einwendung.
- Ergebnisbuchung: nur mit Freigabestufe G3 im Status fällig; es entstehen Buchungsentwürfe,
  die in der Buchhaltung geprüft und gebucht werden.
- Verbrauchsinformation ohne Portal: in der Monatsliste zeigt "nicht zugestellt" die offenen
  Einheiten; die Zustellung per Post, E-Mail oder Übergabe wird mit Nachweis erfasst.
