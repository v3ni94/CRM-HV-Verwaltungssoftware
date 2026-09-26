# Verträge (Miete, WEG, SEV)

## Zweck

Verträge verbinden eine Einheit mit einer Vertragspartei (Mieter oder Eigentümer) und
tragen die Sollbeträge, den Zahlungsplan, SEPA-Mandate und Kautionen. Aus ihnen entstehen
die Sollstellungen (Kapitel Buchhaltung) und die Nutzerzeiträume der Abrechnungen (Kapitel
Abrechnung Miete, Kapitel WEG).

Die Vertragsdaten kommen im Parallelbetrieb aus der Datenübernahme (Berichte Mietverträge,
Eigentumsverhältnisse, Zahlungen des Importassistenten) oder über die Schnittstelle. Ein
eigenes Vertragsformular gibt es in der Oberfläche noch nicht; sichtbar sind Verträge in
der Suche (Strg+K), auf der Startseite (laufende Verträge, Vertragsenden der nächsten
90 Tage), im Kalender (Ende, Kündigung) und im Bereich Vermietung (laufende
Mietverträge für Mieterhöhungen, Leerstandsliste).

## Vertragsarten

| Art | Verwendung |
| --- | --- |
| Mietvertrag | Mieter einer Einheit; Vermieter ist der Eigentümer des Objekts (Mietverwaltung) oder der SEV-Eigentümer (WEG mit SEV) |
| Eigentumsverhältnis | Wohnungseigentümer einer Einheit in einer WEG; Pflichtangabe ist das Datum des Eigentumsübergangs laut Grundbuch, dazu Datum Nutzen und Lasten und die Erwerbsart (Kauf, Ersterwerb, Erbfolge) |

Bei einem Eigentumsverhältnis lässt sich die Sondereigentumsverwaltung (SEV) aktivieren.
Dann verwaltet die Hausverwaltung für diesen Eigentümer zusätzlich die Vermietung seiner
Einheit; Mietverträge dieser Einheit laufen auf den SEV-Eigentümer als Vermieter, und der
Reiter SEV in der Objektliste zeigt das Objekt. Ein abweichender Schuldner für das
SEV-Honorar kann hinterlegt werden.

Weitere Kennzeichen am Vertrag: Lastschrift mit SEPA-Mandat, Mahnsperre mit Begründung,
Sperre für Mieterhöhungen bis zu einem Datum, Nutzerwechselgebühr, Umlageausfallwagnis,
Umsatzsteueroption, Sonderrechtsnachfolgehaftung (nur Eigentum), Notizen.

## Versionen, Beendigung, Eigentümerwechsel

- Vertragsversionen: Änderungen werden als neue Version mit Gültigkeitsbeginn erfasst; die
  Historie bleibt lesbar.
- Vertrag beenden: Enddatum, Datum der Kündigungserklärung und Grund. Das Ende erscheint
  im Kalender und auf der Startseite.
- Eigentümerwechsel: Der neue Eigentümer wird mit Eigentumsübergang, Nutzen und Lasten,
  Erwerbsart und gegebenenfalls Sonderrechtsnachfolgehaftung und SEV erfasst; das bisherige
  Eigentumsverhältnis endet zum Übergang.

## Sollbeträge und Zahlungsplan

Je Vertrag werden Zahlungsarten mit Netto, Brutto und Gültigkeitsbeginn erfasst, zum
Beispiel Miete 500,00 EUR ab 01.01.2024 oder Hausgeld und Erhaltungsrücklage aus dem
beschlossenen Wirtschaftsplan (Kapitel WEG, Vorschüsse übernehmen). Die Zahlungshistorie
zeigt alle Stände mit Zeitraum.

Der Zahlungsplan legt Intervall (Standard monatlich) und Fälligkeitstag fest (Standard der
3. des Monats). Der Sollstellungslauf verarbeitet nur monatliche Beträge; zeitanteilige
Beträge bei Ein- oder Auszug innerhalb eines Monats, abweichende Intervalle,
Werktagsregeln und Umsatzsteuer auf Forderungen führt er als manuelle Posten auf und
rechnet sie nicht nach eigener Annahme.

## SEPA-Mandate

Mandate werden je Vertragspartei und Gläubiger (Rechtsträger) mit Bankverbindung des
Kontakts, Mandatsreferenz, Gläubiger-ID, Unterschriftsdatum, Art (Basis oder Firma) und
Sequenz erfasst, einem Vertrag zugeordnet und bei Bedarf widerrufen. Ein Mandat ist Voraussetzung für das Kennzeichen Lastschrift am
Vertrag. Der Einzug selbst erfolgt nicht über die Plattform (Freigabestufe G2 geschlossen,
Kapitel Buchhaltung, Zahlläufe).

## Kautionen

Zu einem Mietvertrag werden Kautionen mit Art (Barkaution, Sparbuch, Versicherung,
Bürgschaft, Festgeld, Patronatserklärung, Sonstiges), Betrag, Anzahl Raten (1 bis 12),
Gültigkeit, Kautionskonto und Verzinsungsregel erfasst. Bewegungen (Einzahlung,
Verzinsung, Verrechnung, Auszahlung) werden mit Datum und Betrag erfasst; Verrechnung und
Auszahlung verlangen eine Begründung und können als prüfpflichtig gekennzeichnet sein.
Kautionen sind Fremdgeld: sie erscheinen in der Eigentümerabrechnung und in der
Liquiditätsvorschau getrennt vom freien Vermögen des Eigentümers.

## Belegungsliste

Je Objekt liefert die Belegungsliste die Einheiten mit ihren Verträgen zum Stichtag
(Mieter, Eigentümer, Leerstand). Die Leerstandsliste im Bereich Vermietung zeigt leere
Einheiten mit Wohnfläche, Leer seit und Tagen.

## Verweise

- Kapitel Buchhaltung: Sollstellungslauf, offene Posten, Mahnwesen.
- Kapitel WEG: Wirtschaftsplan und Übernahme der Vorschüsse in die Verträge.
- Kapitel Abrechnung Miete: Nutzerzeiträume und Vorauszahlungen.
