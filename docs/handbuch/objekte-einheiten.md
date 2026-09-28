# Objekte und Einheiten

## Zweck

Der Bereich Objekte (Menü Verwaltung, Objekte) führt die Stammdaten des Verwaltungsbestands:
Objekte, Gebäude, Einheiten, Umlageschlüssel, Rechtsträger, Ansprechpartner, Bankkonten,
Zähler, Wartungen und Prüfpflichten. Die Stammdaten sind die Grundlage für Verträge,
Sollstellungen, Abrechnungen und die WEG-Verwaltung. Solange Immoware24 führend ist, werden
Objekte in der Regel über die Datenübernahmen angelegt (Kapitel Datenübernahmen und
Importassistent); die Anlage von Hand bleibt möglich.

## Objektliste

Die Liste zeigt Nr., Name, Anschrift, Verwaltungsart und Status. Das Suchfeld sucht in
Nummer, Name, Straße und Ort. Die Reiter Alle, Mietverwaltung, WEG und SEV filtern nach
Verwaltungsart; der Reiter SEV zeigt nur WEG-Objekte mit aktivierter
Sondereigentumsverwaltung, für die mindestens ein Mietvertrag hinterlegt ist.

Status eines Objekts: in Aufnahme, aktiv, deaktiviert. In Aufnahme und aktiv werden über die
Schnittstelle oder die Datenübernahme gesetzt; deaktiviert entsteht durch Verwaltung beenden
(Abschnitt Verwaltung beenden). Deaktivierte Objekte fehlen in der Objektliste. Der Superadmin
sieht über den Schalter Deaktivierte anzeigen zusätzlich die deaktivierten Objekte, grau und
mit der Statusmarke Deaktiviert.

## Objekt anlegen

Objekt anlegen fragt Objektnummer (3 Ziffern), Name, Verwaltungsart sowie Straße,
Hausnummer, PLZ, Ort und Bundesland ab. Die Objektnummer ist je Mandant eindeutig.

Die Verwaltungsart legt die Rechtsträger fest und kann nach der Anlage nicht mehr geändert
werden:

| Verwaltungsart | Rechtsträger, die angelegt werden |
| --- | --- |
| Mietverwaltung | Eigentümer (aus dem Objekteigentümer, siehe unten) |
| WEG | GdWE (Gemeinschaft der Wohnungseigentümer) |
| WEG mit SEV | GdWE und je Sondereigentum ein SEV-Eigentümer |

Der Verwalter selbst ist ein eigener Rechtsträger und wird nie automatisch Gläubiger oder
Inhaber verwalteter Gelder. Diese Trennung ist Grundlage der Buchhaltung (Kapitel
Buchhaltung, Buchungskreis je Rechtsträger).

## Objektdetail

Die Detailseite zeigt oben Status, Verwaltungsart, Anschrift und die Anzahl der Einheiten.
Bei WEG-Objekten führt die Schaltfläche Zur WEG-Verwaltung in die laufende Verwaltung der
Gemeinschaft (Kapitel WEG), bei allen Objekten Zur Vermietung in den Bereich Vermietung.

Unter der Kopfzeile steht die Verknüpfungsleiste mit Sprungwegen zu Einheiten, Verträgen,
Kontakten, Tickets und zur Buchhaltung des Objekts.

Weitere Abschnitte der Detailseite:

- Stammdaten: Name, Anschrift, Grundbuchangaben, Flächen, Garten, Sanierung,
  Umlageausfallwagnis, Verwaltungsbeginn und Verwaltungsende, Bemerkungen. Die Felder werden
  mit Schreibrecht für Objekte direkt auf der Seite geändert (Kapitel Stammdaten direkt
  bearbeiten).
- Rechtsträger: alle Rechtsträger des Objekts mit Art (GdWE, Eigentümer, SEV-Eigentümer,
  Verwalter) und Name.
- Eigentümer: bei Mietverwaltung der Objekteigentümer mit Beginn und Anteil sowie
  Verrechnungskonto, Vollmacht (Verweis auf das Dokument) und Steuerberater (Verweis auf den
  Kontakt). Die drei Angaben werden über Details für [Name] bearbeiten gepflegt
  (Handlungsanweisung Stammdaten).
- Gebäude: alle Gebäude des Objekts mit Anschrift, Adresszusatz, Baujahr, Geschossen und dem
  Stand des Energieausweises; der Name führt auf die Gebäudeseite.
- Einheiten: Tabelle mit Nr., Bezeichnung, Art, Wohnfläche und Schlüsselwerten (zum Beispiel
  MEA: 125,00 oder WFL: 60,00). Arten: Wohnung, Gewerbe, Büro, Stellplatz, Garage, Lager,
  Garten, Sonstiges.
- Untergemeinschaften (nur WEG) mit Kürzel und Name.
- Abrechnungszeiträume je Art (Hausgeldabrechnung, Betriebskostenabrechnung,
  Heizkostenabrechnung, Wirtschaftsplan, Eigentümerabrechnung) mit Von, Bis und dem Kennzeichen
  für die Online-Belegprüfung durch den Beirat.
- Ansprechpartner: zugeordnete Kontakte mit Kategorie, Gültigkeit und Portalsichtbarkeit,
  verlinkt in die Kontakte; Zuordnen, Bearbeiten und Beenden direkt im Abschnitt.
- Zähler: Nummer, Zählerart, Einheit, Standort, Gültigkeit und Eichfrist; Anlegen,
  Bearbeiten und Zählerwechsel direkt im Abschnitt.
- Wartungen und Prüfpflichten mit Art, Intervall, nächster Fälligkeit, Dienstleister,
  letzter Erledigung und Status; Anlegen, Bearbeiten und Erledigt direkt im Abschnitt.
  Fällige Wartungen erscheinen auch im Kalender und in den Benachrichtigungen (Kapitel
  Kalender).
- Zusatzfelder des Objekts mit Werten je definiertem Feld; Werte bearbeiten und Neues
  Zusatzfeld direkt im Abschnitt.
- Dienstleister: Dienstleisterverhältnisse mit Kontakt, Vertragsart, Laufzeit, Kundennummer,
  Stand und Gültigkeit der Freistellungsbescheinigung und Kreditorenkonto.
- Bankkonten des Objekts: Konten der Rechtsträger und zugeordnete Bankverbindungen, ein Konto
  je Rechtsträger kann als Standardkonto für Hausgeld oder Miete markiert werden (Kapitel
  Banking). Darunter steht je Bankkonto das zugeordnete Sachkonto.
- Dokumente (Paperless): Dokumente aus dem DMS mit Objektbezug (Kapitel Dokumente und DMS).
- Objektmappe: Dokumente, die im Portal für Mieter oder Eigentümer sichtbar sind.
- Schwarzes Brett: Aushänge für das Portal mit Gültigkeit und Zielgruppe (Kapitel Portal).
- Vollständigkeit der Objektakte: Pflichtunterlagen und ein Nachforderungsschreiben als
  Entwurf (Kapitel Dokumente und DMS).
- Tickets zum Objekt (Kapitel Tickets).
- Ereignisprotokoll: alle protokollierten Änderungen am Objekt mit altem und neuem Wert.

Der Energieausweis wird seit der Ergänzung der Objektdaten am Gebäude geführt und auf der
Gebäudeseite gepflegt (siehe unten).

## Verwaltung beenden

Endet das Verwaltungsverhältnis, wird das Objekt auf der Detailseite über Verwaltung beenden
deaktiviert. Das Formular fragt ab: gekündigt von (Verwaltung, Eigentümer,
Eigentümergemeinschaft, Sonstige), Kündigungsdatum, Ende der Verwaltung, optional
nachfolgender Verwalter und nachfolgender Eigentümer (Auswahl aus den bestehenden
Kontakten), das Kündigungsschreiben (Datei hochladen, wird als Dokument am Objekt abgelegt)
und eine Notiz. Nach Weiter fasst eine Bestätigung die Beendigung zusammen; erst Verwaltung
beenden führt sie aus. Voraussetzung ist das Recht Objekte ändern und ein Objekt in Aufnahme
oder aktiv.

Danach zeigt die Detailseite oben das Banner Objekt deaktiviert mit Verwaltungsende,
Kündigendem, Kündigungsdatum, den Nachfolgern (Verweis auf den Kontakt), dem
Kündigungsschreiben (Verweis auf das Dokument) und der Notiz. Alle Daten des Objekts
(Einheiten, Verträge, Buchhaltung, Dokumente) bleiben unverändert erhalten und einsehbar;
die Stammdaten sind schreibgeschützt.

Wieder aktivieren kann nur der Superadmin (Schaltfläche im Banner mit Bestätigung). Das
Objekt erhält dann seinen vorherigen Status zurück und erscheint wieder in der Liste; die
Beendigung bleibt im Änderungsprotokoll erhalten. Diese Einschränkung ist ein interner
Standard, keine Rechtsvorschrift (Regel M4-05).

## Gebäudeseite

Die Gebäudeseite erreicht man über den Gebäudenamen auf der Objektseite oder über die
Verknüpfungsleiste der Einheit. Sie zeigt:

- Stammdaten des Gebäudes: Bezeichnung, Straße, Hausnummer, Adresszusatz, Baujahr,
  Sanierungsstand, Bauweise, Gebäudetyp, Geschosse, Fenster, Flächen, Aufzug, Kellerräume,
  Denkmalschutz und Bemerkungen, direkt auf der Seite änderbar.
- Energieausweis: Rechtsgrundlage (GEG oder EnEV 2014), Art des Ausweises, Endenergie Wärme
  und Strom in kWh/(m²a), Warmwasser enthalten, Heizungsart, Energieträger, Baujahr laut
  Ausweis, Ausstellungsdatum, Gültig bis und Effizienzklasse. Die Werte werden aus dem Ausweis
  übernommen, nichts wird abgeleitet; Anzeigen und Exposé lesen sie vom Gebäude der Einheit
  (Kapitel Makler). Gespeichert wird mit der Schaltfläche Energieausweis speichern.
- Einheiten des Gebäudes und das Ereignisprotokoll des Gebäudes.

## Einheitenseite

Die Einheitenseite (Bereich Vermietung) zeigt die Verknüpfungsleiste (Objekt, Gebäude,
laufende Verträge, Mieterkontakte, Tickets, Buchhaltung), die Stammdaten der Einheit
(Nummer, Bezeichnung, Art, Lage, Etage, Flächen, Zimmer, Ausstattung, Anschrift, fiktive
Einheit, Untergemeinschaft, Umsatzsteuer bei Leerstand, Provision, Kaution) direkt änderbar,
Eigentümer und Mieter, Umlageschlüsselwerte, Umlagewerte bei Leerstand, Zählerwechsel der
Zähler der Einheit, den Energieausweis des Gebäudes, das Exposé, Interessenten, Tickets und
das Ereignisprotokoll. Provision und Kaution sind Stammwerte der Einheit; Zahlungen und
Kautionskonten werden davon nicht berührt.

## Einheiten, Gebäude und Umlageschlüssel

Einheiten gehören zu einem Gebäude des Objekts. Je Einheit sind Nummer, Bezeichnung, Lage,
Art und Wohnfläche hinterlegt. Einheiten und Schlüsselwerte lassen sich zu einem Stichtag
lesen; Änderungen werden mit Zeitraum erfasst, sodass eine Abrechnung den Stand des
jeweiligen Abrechnungszeitraums verwendet.

Umlageschlüssel werden je Objekt geführt (zum Beispiel MEA für Miteigentumsanteile, WFL für
Wohnfläche). Muster für die gängigen Schlüssel stehen bereit. Schlüsselwerte werden je
Einheit mit Gültigkeitszeitraum erfasst; die Historie bleibt erhalten. Eine
Umsatzsteueroption wird ebenfalls mit Zeitraum geführt.

Gebäude und Einheiten werden auf der Objektseite angelegt (Schaltflächen Gebäude anlegen und
Einheit anlegen, letztere auch auf der Gebäudeseite); Einheitennummern sind je Objekt
eindeutig. Der Abschnitt Umlageschlüssel und Schlüsselwerte der Objektseite zeigt je
Schlüssel die Sollsumme (Betreiberwert, zu verifizieren) und die Summe der Einheitenwerte zum
Stichtag, warnt bei Abweichung ohne zu sperren und nimmt neue Werte mit Zeitraum sowie neue
Schlüssel auf. Ablauf in der [Handlungsanweisung Stammdaten](anleitung-stammdaten.md).
Daneben bleiben die Datenübernahme (Berichte Objekte und Einheiten) und die Schnittstelle.
Bestehende Gebäude und Einheiten werden auf ihrer Seite direkt bearbeitet.

## Objekteigentümer und Rechtsträger

Bei Mietverwaltung wird der Eigentümer des Objekts mit Gültigkeitsbeginn als
Objekteigentümer erfasst; daraus entsteht der Rechtsträger Eigentümer, dem Buchungskreis,
Forderungen und Bankguthaben zugeordnet werden. Bei WEG-Objekten entsteht die GdWE mit der
Anlage des Objekts.

## Zähler, Dienstleister, Wartungen, Katalog, Zusatzfelder

Zähler, Wartungen und Prüfpflichten sowie Zusatzfelder werden seit dem 28.09.2026 auf der
Objektseite gepflegt (Handlungsanweisung Stammdaten, Abschnitte Zähler, Wartungen und
Zusatzfelder). Über die Schnittstelle stehen je Objekt außerdem bereit: Zählerstände
(Ablesungen), Dienstleisterverhältnisse (Anlage), ein Katalog für Ausstattungsmerkmale und
Zusatzfelder vom Typ Verknüpfung. In der Oberfläche sichtbar sind davon die
Dienstleisterverhältnisse (Objektdetail) und die Zählerwechsel (Objektseite und
Einheitenseite).

## Verweise

- Kapitel Datenübernahmen: Objekte und Kontakte aus Immoware24-Listen anlegen.
- Kapitel Verträge: Miet- und Eigentumsverhältnisse je Einheit.
- Kapitel WEG: laufende Verwaltung der Gemeinschaft.
- Kapitel Stammdaten direkt bearbeiten: Bedienung, Speicherzustände und Konflikthinweis.
