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
- Eigentümerwechsel: Abschnitt Eigentümerwechsel auf der Vertragsseite eines offenen
  Eigentums (auch auf der Einheitenseite). Der neue Eigentümer wird mit Eigentumsübergang,
  Nutzen und Lasten, Erwerbsart, Nachweis und gegebenenfalls Sonderrechtsnachfolgehaftung und
  SEV erfasst; das bisherige Eigentumsverhältnis endet am Vortag, die am Übergang gültigen
  Sollbeträge, der Zahlungsplan und die Umlagewerte werden auf Wunsch übernommen. Ablauf in
  der [Anleitung Eigentümerwechsel](anleitung-eigentuemerwechsel.md).

## Sollbeträge und Zahlungsplan

Je Vertrag werden Zahlungsarten mit Netto, Umsatzsteuer, Brutto und Gültigkeitszeitraum
erfasst, zum Beispiel Miete 500,00 EUR ab 01.01.2024, Betriebskosten- und
Heizkostenvorauszahlung, Hausgeld und Erhaltungsrücklage (aus dem beschlossenen
Wirtschaftsplan, Kapitel WEG, Vorschüsse übernehmen) oder weitere Zahlungsarten des Katalogs
(Einstellungen, Kataloge, Zahlungsarten).

Abschnitt Sollbeträge auf der Vertragsseite (Recht `contracts:update` zum Erfassen):

- Die Tabelle zeigt alle Stände mit Zahlungsart, Netto, USt, Brutto, Gültig ab, Gültig bis
  und Grund (Erstbetrag, Erhöhung, Indexanpassung, Staffel, Anpassung aus Abrechnung,
  Sonstiges), auch aus früheren Vertragsversionen. Die zum Stichtag gültigen Stände sind
  markiert, darüber steht die Summe je Monat zum Stichtag (Vorbelegung heute, Stichtag
  änderbar, zum Beispiel für die Summe nach einer Erhöhung).
- Betrag erfassen legt einen neuen Stand ab Datum an: Zahlungsart, Netto im Format 1.234,56,
  USt in Prozent (Brutto wird berechnet), Gültig ab, optional Gültig bis, Grund. Der offene
  Vorbetrag derselben Zahlungsart endet automatisch am Vortag; frühere Stände werden nie
  überschrieben. Negative Beträge nur bei Mietminderung.
- Die Software lehnt ab: Gültig ab außerhalb der Laufzeit, Gültig bis vor Gültig ab, einen
  Zeitraum, der sich mit einem befristeten oder gleich beginnenden Stand derselben Zahlungsart
  überschneidet (befristeten Stand zuerst anpassen oder späteres Datum wählen).
- Beim Anlegen eines Vertrags lassen sich die ersten Sollbeträge gleich mitgeben (Abschnitt
  Sollbeträge im Formular, je Zahlungsart ein Betrag, gültig ab Vertragsbeginn, Grund
  Erstbetrag). Schlägt ein Betrag fehl, ist der Vertrag trotzdem angelegt; die Vertragsseite
  zeigt den Hinweis und der Betrag wird dort nacherfasst.

Das Erfassen eines Sollbetrags bucht nichts: Sollstellungen entstehen erst im manuell
gestarteten Sollstellungslauf (Kapitel Buchhaltung), Abrechnungen bleiben bis zur
Freigabestufe G3 Entwürfe. Der Zusammenhang mit dem Mieterhöhungsfall steht in
[Mieterhöhung](anleitung-mieterhoehung.md).

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

### Kautionsabrechnung bei Vertragsende (Entwurf)

Standardregel (Betreiberentscheidung vom 26.09.2026, Regel M5-02): die Kaution wird getrennt
verwahrt, die Verzinsung wird je Jahr als Bewegung erfasst, die Abrechnung bei Vertragsende
ist ein Entwurf. Auf der Vertragsseite steht im Abschnitt Kautionen die Schaltfläche
Kautionsabrechnung erstellen (Recht Verträge ändern).

1. Abrechnungsdatum wählen, vorbelegt mit dem Vertragsende. Bewegungen nach diesem Datum
   sind nicht erlaubt; das Datum darf nicht vor dem Vertragsende liegen.
2. Zinsart wählen:
   - Zinsen je Jahr einzeln erfassen: Beträge je Kalenderjahr eingeben, zum Beispiel aus dem
     Kontoauszug des Kautionskontos. Bereits erfasste Zinsbewegungen sind vorbelegt.
   - Referenzzinssatz je Jahr: die Plattform rechnet tagesgenau je Kalenderjahr auf das
     Kautionsguthaben (Einzahlungen abzüglich Verrechnungen und Auszahlungen) mit dem Satz aus
     Einstellungen, Kautionszinsen, kaufmännisch gerundet je Jahr. Fehlt der Satz für ein Jahr,
     ist die Berechnung gesperrt, bis er gepflegt ist.
   - Keine Verzinsung.
3. Einbehalte mit Bezeichnung und Betrag erfassen (zum Beispiel Schaden, Endreinigung, offene
   Betriebskosten laut Abrechnung). Einbehalte über dem Guthaben lehnt die Plattform ab; eine
   Nachforderung gegen den Mieter ist ein eigener Vorgang.
4. Berechnen zeigt eingezahlte Kaution, erfasste Verrechnungen und Auszahlungen, Guthaben vor
   Zinsen, Zinsen je Jahr mit Satz und Tagen, Einbehalte und Auszahlungsbetrag. Bereits
   erfasste Zinsbewegungen werden nur zum Abgleich ausgewiesen und nicht erneut addiert.
5. Als Entwurf speichern legt den Datensatz am Vertrag ab. Mehrere Entwürfe je Kaution sind
   möglich; sie bleiben nachvollziehbar erhalten.

Der Entwurf bucht nichts und zahlt nichts aus. Die Freigabe zur Auszahlung liegt hinter der
Freigabestufe G3 und ist je Mandant standardmäßig gesperrt. Die Auszahlung selbst wird nach
Freigabe als Bewegung Auszahlung erfasst; die Überweisung läuft über das Zahlungsmodul (G2).
Ein PDF der Kautionsabrechnung gibt es noch nicht; der Entwurf ist als Datensatz und über die
API abrufbar. Welcher Zinssatz für Mietkautionen rechtlich gilt und ob Zinseszins anzusetzen
ist, muss die Rechtsberatung bestätigen; die Plattform stellt keine Rechtslage fest.

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

## Bemerkungen und Mahnsperre direkt bearbeiten

Der Abschnitt Bemerkungen und Mahnsperre auf der Vertragsseite wird an Ort und Stelle
geändert (Recht Verträge ändern) und erzeugt keine neue Vertragsversion. Wird die Mahnsperre
gesetzt, ist eine Begründung Pflicht; die Sperre wird erst zusammen mit der Begründung
gespeichert. Alle übrigen Vertragsdaten (Laufzeit, Parteien, Sollbeträge, Zahlungsplan)
bleiben versioniert und werden über Bearbeiten als neue Version erfasst. Die
Verknüpfungsleiste unter dem Kopf führt zu Objekt, Einheit, Vertragspartner, Buchhaltung und
Tickets der Einheit; das Ereignisprotokoll am Seitenende zeigt jede Änderung mit altem und
neuem Wert (Recht audit:read).

## Verweise

- Kapitel Buchhaltung: Sollstellungslauf, offene Posten, Mahnwesen.
- Kapitel WEG: Wirtschaftsplan und Übernahme der Vorschüsse in die Verträge.
- Kapitel Abrechnung Miete: Nutzerzeiträume und Vorauszahlungen.

## SEPA Mandate (Seite Verträge, SEPA Mandate)

Die Übersicht zeigt alle SEPA Mandate der Verträge mit Referenz, IBAN, Art und Folge, Unterschriftsdatum, Gültigkeit und letzter Verwendung. Filter: Status (aktiv, widerrufen, abgelaufen), Suche nach Referenz oder IBAN, "Noch nie verwendet" und "Läuft innerhalb von 90 Tagen ab". Die Erfassung ist reine Dokumentation, der Einzug bleibt bis zur Freigabe Zahlungsanstoß (G2) gesperrt.

- Mieterhöhungssperre: Unter dem Feld stehen die Mieterhöhungsfälle des Vertrags. Wird ein offener Fall vor Ablauf der Sperre wirksam, erscheint ein Hinweis; die Freigabe des Falls bleibt gesperrt.

## Verzinsung der Kaution und Zinsgutschrift

Am Mietvertrag zeigt die Karte Verzinsung und Zinsgutschrift je Kaution den Zinssatzverlauf: Der Satz gilt ab dem genannten Datum, bis ein neuerer Eintrag folgt. Sätze trägt der Betreiber nach Bankbestätigung ein, das System ruft keinen Satz ab und belegt keinen vor. Für Versicherung, Bürgschaft und Patronatserklärung wird keine Verzinsung geführt.

Mit Entwurf berechnen entsteht für ein abgeschlossenes Jahr die Zinsgutschrift als Entwurf (Berechnung taggenau, je Jahr auf den Cent gerundet). Bestätigen erfasst eine Zinsbewegung am 31.12. auf dem Kautionskonto, Verwerfen lässt den Entwurf ohne Wirkung. Es wird nichts gebucht und nichts gezahlt. In der Kautionsabrechnung rechnet die Zinsart Zinssatz der Kaution mit diesem Verlauf; die Abrechnung bleibt ein Entwurf.
