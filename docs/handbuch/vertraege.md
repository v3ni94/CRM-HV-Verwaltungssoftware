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

## Vertrag anlegen

Im CRM unter Verträge, Schaltfläche Vertrag anlegen (auch aus der Vermietung erreichbar,
Berechtigung `contracts:create`). Das Formular fragt ab:

1. Vertragsart (Mietvertrag oder Eigentum), Objekt und Einheit als Auswahl; bei mehreren
   Rechtsträgern im Objekt wahlweise der Vermieter, sonst ermittelt ihn die Plattform.
2. Vertragspartner über die Kontaktsuche mit Rollenfilter (Mieter, Eigentümer).
3. Beginn und Ende (leer bei unbefristet), bei Eigentum zusätzlich Eigentumsübergang laut
   Grundbuch (Pflicht, nicht nach dem Beginn), Nutzen und Lasten, Erwerbsart, Haftung bei
   Sonderrechtsnachfolge und SEV (nur in Objekten mit Verwaltungsart WEG mit SEV).
4. Umsatzsteuer, Lastschrift mit Verweis auf ein aktives SEPA-Mandat des Vertragspartners,
   Mahnsperre mit Begründung, Mieterhöhungssperre, Nutzerwechselgebühr, Umlageausfallwagnis.
5. Optional gleich ein Zahlungsplan (Intervall, Fälligkeitsregel, Tag, Gültigkeit) und bei
   Mietverträgen eine Kaution (Art, Betrag im Format 1.234,56, Raten, Fälligkeit).

Nach dem Speichern öffnet sich die Detailseite. Fehlermeldungen der Schnittstelle erscheinen
am jeweiligen Feld. Bearbeiten legt eine neue Version ab einem Stichtag an (Lastschrift,
Mandat, Sperren, Umsatzsteuer, Notizen); Einheit, Vertragspartner, Beginn und
Eigentumsangaben bleiben fest. Ein Mietvertrag wird dort beendet, Eigentum nur über den
Eigentümerwechsel. Kündigungen sind vorher durch die Geschäftsführung freizugeben.

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

## Dienstleisterverträge mit Kündigungsfristen

Unter Verwaltung, Dienstleisterverträge werden Verträge mit Dienstleistern (Hausmeister,
Wartung, Reinigung und ähnliche) mit Laufzeit, Kündigungsfrist und automatischer
Verlängerung geführt. Rechte: Lesen mit Verträge lesen, Anlegen mit Verträge anlegen,
Ändern mit Verträge ändern, Löschen mit Verträge löschen (in der Vorbelegung nur
Administrator).

Dienstleistervertrag anlegen: Bezeichnung, Dienstleister (Kontakt), Objekt (optional),
Beginn, Ende (optional, leer = unbefristet), Kündigungsfrist mit Einheit Tage oder Monate,
Automatische Verlängerung in Monaten (optional), Gekündigt am (optional), Notizen.

Die Liste zeigt je Vertrag Status (Laufend, Unbefristet, Gekündigt, Beendet), das
nächstmögliche Vertragsende und den spätesten Kündigungstermin, gekennzeichnet als
Orientierung, zu prüfen. Regeln der Orientierungsrechnung:

- Monatsfristen werden kalendermonatsweise vom Vertragsende zurückgerechnet; ist das
  Vertragsende ein Monatsletzter, ist auch der Kündigungstermin ein Monatsletzter (Ende
  30.06., drei Monate: spätester Kündigungstermin 31.03.).
- Ohne Ende läuft der Vertrag unbefristet; das nächstmögliche Ende ist heute plus
  Kündigungsfrist, ein fester Kündigungstermin wird nicht geführt.
- Mit automatischer Verlängerung verschiebt sich das Ende um die Verlängerungsmonate,
  solange der Kündigungstermin des aktuellen Endes bereits verstrichen ist.
- Ein gekündigter Vertrag endet zum ersten Ende, dessen Kündigungstermin nicht vor dem
  Kündigungstag liegt.

Der späteste Kündigungstermin erscheint in der Fristenliste (Menü Fristen, Typ
Kündigungsfrist Dienstleistervertrag) mit 14 Tagen Vorfrist; Benutzer mit dem Recht
Verträge ändern erhalten einmalig eine Benachrichtigung. Die Berechnung ersetzt keine
rechtliche Fristprüfung am Vertragsdokument; Kündigungen sind vor Abgabe mit der
Geschäftsführung abzustimmen und werden nicht über die Plattform erklärt.

## Verweise

- Kapitel Buchhaltung: Sollstellungslauf, offene Posten, Mahnwesen.
- Kapitel WEG: Wirtschaftsplan und Übernahme der Vorschüsse in die Verträge.
- Kapitel Abrechnung Miete: Nutzerzeiträume und Vorauszahlungen.
