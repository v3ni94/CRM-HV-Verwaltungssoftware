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

Status eines Objekts: in Aufnahme, aktiv, beendet. Der Status wird über die Schnittstelle
oder die Datenübernahme gesetzt.

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

Weitere Abschnitte der Detailseite:

- Rechtsträger: alle Rechtsträger des Objekts mit Art (GdWE, Eigentümer, SEV-Eigentümer,
  Verwalter) und Name.
- Einheiten: Tabelle mit Nr., Bezeichnung, Art, Wohnfläche und Schlüsselwerten (zum Beispiel
  MEA: 125,00 oder WFL: 60,00). Arten: Wohnung, Gewerbe, Büro, Stellplatz, Garage, Lager,
  Garten, Sonstiges.
- Ansprechpartner: zugeordnete Kontakte mit ihrer Rolle, verlinkt in die Kontakte.
- Offene Wartungen und Prüfpflichten mit Fälligkeitsdatum. Fällige Wartungen erscheinen
  auch im Kalender und in den Benachrichtigungen (Kapitel Kalender).
- Bankkonten des Objekts: Konten der Rechtsträger und zugeordnete Bankverbindungen, ein Konto
  je Rechtsträger kann als Standardkonto für Hausgeld oder Miete markiert werden (Kapitel
  Banking).
- Dokumente (Paperless): Dokumente aus dem DMS mit Objektbezug (Kapitel Dokumente und DMS).
- Vollständigkeit der Objektakte: Pflichtunterlagen und ein Nachforderungsschreiben als
  Entwurf (Kapitel Dokumente und DMS).
- Tickets zum Objekt (Kapitel Tickets).
- Energieausweis: Art, Kennwert, Energieträger, Baujahr laut Ausweis, Ausstellungsdatum,
  Gültig bis und Effizienzklasse; Anzeigen und Exposé übernehmen die Werte (Kapitel Makler).
- Schwarzes Brett: Aushänge für das Portal mit Gültigkeit und Zielgruppe (Kapitel Portal).

## Einheiten, Gebäude und Umlageschlüssel

Einheiten gehören zu einem Gebäude des Objekts. Je Einheit sind Nummer, Bezeichnung, Lage,
Art und Wohnfläche hinterlegt. Einheiten und Schlüsselwerte lassen sich zu einem Stichtag
lesen; Änderungen werden mit Zeitraum erfasst, sodass eine Abrechnung den Stand des
jeweiligen Abrechnungszeitraums verwendet.

Umlageschlüssel werden je Objekt geführt (zum Beispiel MEA für Miteigentumsanteile, WFL für
Wohnfläche). Muster für die gängigen Schlüssel stehen bereit. Schlüsselwerte werden je
Einheit mit Gültigkeitszeitraum erfasst; die Historie bleibt erhalten. Eine
Umsatzsteueroption wird ebenfalls mit Zeitraum geführt.

Die Anlage von Gebäuden, Einheiten und Schlüsselwerten erfolgt derzeit über die
Datenübernahme (Berichte Objekte und Einheiten) oder die Schnittstelle; ein eigenes
Formular in der Oberfläche gibt es dafür noch nicht.

## Objekteigentümer und Rechtsträger

Bei Mietverwaltung wird der Eigentümer des Objekts mit Gültigkeitsbeginn als
Objekteigentümer erfasst; daraus entsteht der Rechtsträger Eigentümer, dem Buchungskreis,
Forderungen und Bankguthaben zugeordnet werden. Bei WEG-Objekten entsteht die GdWE mit der
Anlage des Objekts.

## Zähler, Dienstleister, Wartungen, Katalog, Zusatzfelder

Über die Schnittstelle stehen je Objekt außerdem bereit: Zähler mit Zählerständen,
Dienstleisterverhältnisse, Wartungen und Prüfpflichten mit Vorlaufzeit, ein Katalog für
Ausstattungsmerkmale und frei definierbare Zusatzfelder. In der Oberfläche sichtbar sind
davon derzeit die offenen Wartungen (Objektdetail, Kalender, Benachrichtigungen).

## Verweise

- Kapitel Datenübernahmen: Objekte und Kontakte aus Immoware24-Listen anlegen.
- Kapitel Verträge: Miet- und Eigentumsverhältnisse je Einheit.
- Kapitel WEG: laufende Verwaltung der Gemeinschaft.
