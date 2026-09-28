# Handlungsanweisung: Mieterwechsel und Wohnungsübergabe

Stand: 28.09.2026. Gilt für Mietverwaltung und SEV. Erfassungsregeln:
[Erfassungsstandards](erfassungsstandards.md).

## Zweck

Ein Mietverhältnis endet, die Wohnung wird zurückgegeben, gegebenenfalls neu vermietet und an
den neuen Mieter übergeben. Ziel: Vertragsende, Auszug, Zählerstände, Übergabeprotokolle,
Kautionsabrechnung und neuer Vertrag sind vollständig erfasst und mit Einheit, Vertrag und
Kontakt verknüpft.

## Wann anwenden

- Kündigung durch Mieter oder Vermieter, Aufhebungsvertrag, Zeitablauf.
- Einzug eines neuen Mieters.

## Rechtliche Voraussetzungen

Rechtlich zu prüfen durch Rechtsanwalt: [Platzhalter] Wirksamkeit und Frist der Kündigung,
Form der Kündigung, Rückgabepflichten, Schönheitsreparaturen, Einbehalt und Frist der
Kautionsabrechnung, Verzinsung der Kaution. Für die Kautionsabrechnung gilt als interne
Standardregel `docs/rules/M5-02-kautionsabrechnung.md` (Betreiberentscheidung, Entwurf, keine
Rechtsfeststellung). Kündigungen der Vermieterseite sind vor Abgabe durch die Geschäftsführung
freizugeben.

## Voraussetzungen im CRM

- Rechte: `contracts:read`, `contracts:create`, `contracts:update`; für Übergabeprotokolle
  dieselben Rechte (Stornierung abgeschlossener Protokolle `contracts:delete`, nur
  Administrator).
- Freigabestufe G3 bleibt geschlossen: keine Freigabe zur Auszahlung der Kaution, kein
  rechtlich maßgeblicher Versand von Abrechnungen. G2 geschlossen: keine Überweisung.

## Ablauf Auszug

### 1. Kündigung erfassen

1. Kündigungsschreiben hochladen: Verwaltung, DMS, Suche im Archiv, Dokument hochladen mit
   Objekt und Einheit. Ablage 04 Mieterakte.
2. Ticket zur Einheit anlegen (Übersicht, Tickets), Titel `Mieterwechsel <Einheit>`, Kontakt
   des Mieters und Einheit verknüpfen, Fälligkeit auf den Rückgabetermin.
3. Vertrag öffnen (Verwaltung, Verträge, Filter Objekt oder Einheit, Öffnen), Schaltfläche
   Bearbeiten, Abschnitt Vertrag beenden:
   - Vertragsende
   - Datum der Kündigungserklärung
   - Grund
   - Auszug (Kalendertermin)
   - Zählerstände zur Beendigung (optional je Zähler der Einheit)
   Speichern mit Vertrag beenden. Vertragsende und Auszug erscheinen in Kalender und
   Fristenliste (Typen Vertragsende, Kündigung, Auszug).

Im Abschnitt Vertrag beenden steht die Prüfung Kündigungsfrist (Orientierung): Frist in
Monaten und Tagen eintragen, wahlweise zum Monatsende, Berechnen. Das rechnerische Ende wird
als zu verifizieren angezeigt und mit dem eingetragenen Vertragsende verglichen; liegt das
Vertragsende davor, erscheint ein Hinweis. Die Prüfung blockiert nichts, da der Vertrag kein
Feld für die Kündigungsfrist hat (Betreiberentscheidung WS-01-Q2). Die Frist ist rechtlich zu
prüfen durch Rechtsanwalt [Platzhalter]; Ergebnis im Ticket vermerken.

### 2. Wohnungsübergabe (Rückgabe)

Makler, Übergabeprotokoll:

1. Neues Übergabeprotokoll, Protokollart Wohnungsübergabe (Vermietung), Objekt aus dem
   Bestand, Objekt, Einheit und Vertrag wählen (Auswahl zeigt die Verträge der Einheit),
   Anlegen. Adresse, Etage und Einheit werden vorbelegt. Die Vertragsverknüpfung lässt sich
   im Protokoll im Abschnitt Objekt, Block Verknüpfter Vertrag, ändern oder nachholen; der
   verknüpfte Vertrag ist dort als Link zur Vertragsseite sichtbar.
2. Termin anlegen erzeugt den Kalendertermin Übergabe.
3. Abschnitte ausfüllen: Beteiligte (Beteiligten aus den Kontakten übernehmen), Kaution,
   Zähler, Räume, Mängel, Schlüssel, Gegenstände, Bemerkungen, Anhänge, Fotos. Angaben im
   Abschnitt Intern erscheinen nie im PDF.
4. Unterschriften aller Beteiligten.
5. Prüfung und Abschluss, Protokoll verbindlich abschließen. Das PDF entsteht auf dem
   Briefbogen des Mandanten und wird als Dokument abgelegt; danach nur noch neue Version.
6. Zustellung vorbereiten legt E-Mail-Entwürfe an; Versand über den Postausgang mit Freigabe.

7. Zählerstände übernehmen: Abschnitt Zähler, Block Zählerstände übernehmen, Schaltfläche
   Zählerstände übernehmen, Rückfrage bestätigen. Jeder Zähler des Protokolls mit Wert wird
   als Zählerstand am Zähler der Einheit angelegt (Ablesedatum aus dem Protokoll, sonst das
   Übergabedatum, Vermerk mit der Protokollnummer). Die Zuordnung läuft über den im Eintrag
   gewählten Zähler oder über die Zählernummer; Zeilen ohne Wert, ohne passenden Zähler oder
   mit mehrdeutiger Nummer werden mit Grund übersprungen und bleiben unverändert. Jede Zeile
   wird nur einmal übernommen, ein zweiter Aufruf legt nichts doppelt an. Voraussetzung ist
   eine Einheit aus dem Bestand mit angelegten Zählern (Rechte `contracts:update` und
   `properties:update`). Die Übernahme geht auch nach dem Abschluss des Protokolls, nicht
   bei stornierten Protokollen.

Wichtig: Die Zählerstände zur Beendigung am Vertrag (Schritt 1) sind nur noch nötig, wenn
kein Protokoll erstellt wird oder ein Zähler im Protokoll nicht zugeordnet werden konnte.
Übernommene Stände werden im Protokoll als übernommen gezählt und lassen sich nur in den
Zählerständen der Einheit korrigieren. Die Protokollnummer (`UP-JJJJMMTT-NNN`) im Ticket zu
vermerken bleibt sinnvoll, ist aber keine Ersatzverknüpfung mehr.

### 3. Kaution abrechnen

Vertragsseite, Abschnitt Kautionen, Kautionsabrechnung erstellen (Recht `contracts:update`):
Abrechnungsdatum, Zinsart, Einbehalte mit Bezeichnung und Betrag, Berechnen, Als Entwurf
speichern. Abrechnung als PDF erzeugen und ablegen legt das PDF am Vertrag ab. Der Entwurf
bucht und zahlt nichts. Fehlt der Referenzzinssatz, unter Einstellungen, Kautionszinsen pflegen
lassen. Einzelheiten in [Verträge](vertraege.md), Abschnitt Kautionsabrechnung.

### 4. Leerstand und Messdienst

- Leerstand erscheint unter Verwaltung, Vermietung, Abschnitt Leerstand.
- Messdienstleister: ein Nutzerwechsel ändert die Einheitenzuordnung nicht; Mitteilung an den
  Messdienstleister nach Kapitel [Messdienstleister](messdienstleister.md).
- Portalzugang des bisherigen Mieters prüfen (Kontakt, Reiter Kommunikation, Portalzugang).

## Ablauf Einzug

### 5. Neuen Mieter und Vertrag anlegen

1. Kontakt anlegen (Übersicht, Kontakte, Kontakt anlegen), Rolle Mieter. Bankverbindung mit
   Mandat nur mit Nachweis erfassen, Freigabe durch zweite Person
   ([Bankverbindung](anleitung-bankverbindung.md)).
2. Verwaltung, Verträge, Vertrag anlegen:
   - Vertragsart Mietvertrag, Objekt, Einheit, bei Bedarf Rechtsträger (Vermieter)
   - Vertragspartner über die Kontaktsuche mit Rolle Mieter
   - Beginn, Ende leer bei unbefristetem Vertrag
   - Umsatzsteuer, Lastschrift mit SEPA-Mandat, Mieterhöhungssperre bis, Nutzerwechselgebühr
   - Sollbeträge: je Zahlungsart ein Betrag (Miete, Betriebskosten- und
     Heizkostenvorauszahlung, Netto im Format 1.234,56 und USt in Prozent), gültig ab
     Vertragsbeginn; spätere Stände auf der Vertragsseite im Abschnitt Sollbeträge
   - Zahlungsplan gleich anlegen (Intervall, Fälligkeitsregel, Fälligkeitstag, Gültig ab)
   - Kaution gleich erfassen (Kautionsart, Betrag im Format 1.234,56, Raten 1 bis 12, Fällig ab)
   Vertrag anlegen.
3. Auf der Vertragsseite Eigenschaften (Umlagewerte), Wert erfassen: zum Beispiel Personenzahl
   mit Gültig ab.
4. Unterschriebenen Mietvertrag hochladen (Dokument hochladen mit Einheit), Ablage
   04 Mieterakte, Ausweiskopie nur wenn erforderlich in 01 Legitimationsunterlagen.
5. Portaleinladung erzeugen: Kontakt, Reiter Kommunikation, Abschnitt Portalzugang.

### 6. Übergabe an den neuen Mieter

Wie Schritt 2 mit einem neuen Protokoll, Beteiligte neuer Mieter und Vermieter.

## Zu verknüpfende Datensätze

| Datensatz | Was |
| --- | --- |
| Einheit | Kündigung, Übergabeprotokolle (über Objekt und Einheit), Mietvertrag, Zählerstände aus dem Protokoll |
| Vertrag alt | Vertragsende, Übergabeprotokoll Rückgabe (Verknüpfung), Zählerstände zur Beendigung nur bei fehlender Übernahme, Kautionsabrechnung |
| Vertrag neu | Übergabeprotokoll Einzug (Verknüpfung), Sollbeträge, Zahlungsplan, Kaution, Umlagewerte, SEPA-Mandat |
| Kontakt alt und neu | Ticket, Bankverbindung, Portalzugang |

## Fristen

Automatisch: Vertragsende, Kündigung, Auszug, Einzug aus den Vertragsdaten. Zusätzlich auf der
Vertragsseite, Abschnitt Fristen, Frist anlegen: Fristtyp Kautionsabrechnung (Auslöser
Übergabe erfolgt), Auslösedatum der Rückgabe, verantwortliche Person. Die Fälligkeit wird aus
der unter Einstellungen, Fristtypen hinterlegten Dauer berechnet (zu verifizieren) oder
eingetragen. Die Frist der Kautionsabrechnung ist rechtlich zu prüfen durch Rechtsanwalt
[Platzhalter]; die Software gibt keine Dauer vor.

## Freigaben

| Schritt | Wer | Durch die Software erzwungen |
| --- | --- | --- |
| Kündigung der Vermieterseite | Geschäftsführung | nein, Hinweis im Formular |
| Versand Protokoll per Mail | zweite Person (Postausgang, Mailfreigabe) | ja, je nach Freigabemodus |
| Bankverbindung neuer Mieter | zweite Person `contacts:approve` | ja |
| Auszahlung Kaution | Freigabe hinter G3, Überweisung hinter G2 | ja, gesperrt |

## Checkliste

- [ ] Kündigung abgelegt, Frist geprüft
- [ ] Vertrag beendet mit Vertragsende, Kündigungsdatum, Grund, Auszug
- [ ] Rückgabeprotokoll mit dem Vertrag verknüpft, abgeschlossen und abgelegt
- [ ] Zählerstände aus dem Protokoll übernommen (übersprungene Zeilen geprüft)
- [ ] Kautionsabrechnung als Entwurf und PDF abgelegt
- [ ] Messdienstleister informiert
- [ ] Neuer Kontakt und Vertrag mit Sollbeträgen, Zahlungsplan und Kaution angelegt
- [ ] Umlagewerte (Personen) erfasst
- [ ] Übergabeprotokoll Einzug mit dem neuen Vertrag verknüpft, abgeschlossen, Zählerstände übernommen
- [ ] Portaleinladung erzeugt

## Häufige Fehler

- Mieter im bestehenden Vertrag getauscht: Vertragspartner ist fest, ein neuer Mieter ist ein
  neuer Vertrag.
- Zählerstände nur im Protokoll erfasst und nicht übernommen: Block Zählerstände übernehmen
  im Abschnitt Zähler nutzen; übersprungene Zeilen (kein Zähler, mehrdeutige Nummer) im
  Eintrag dem richtigen Zähler zuordnen und erneut übernehmen.
- Protokoll ohne Vertragsbezug angelegt: im Abschnitt Objekt den Vertrag nachträglich
  verknüpfen.
- Kautionsabrechnung vor dem Vertragsende datiert: wird abgelehnt.
- Einbehalte über dem Guthaben: wird abgelehnt, Nachforderung ist ein eigener Vorgang.
- Zeitanteilige Miete im Einzugs- oder Auszugsmonat erwartet: der Sollstellungslauf führt sie
  als manuellen Posten.

## Lücken in der Software

- Übergabeprotokoll und Vertrag (28.09.2026 geschlossen): Vertragsauswahl beim Anlegen und
  Block Verknüpfter Vertrag im Abschnitt Objekt.
- Zählerstände aus dem Protokoll (28.09.2026 geschlossen): Block Zählerstände übernehmen im
  Abschnitt Zähler. Offen bleibt die Zuordnung eines Protokollzählers zu einem Zähler der
  Einheit direkt im Zählereintrag; bis dahin muss die Zählernummer im Protokoll der Nummer
  in den Stammdaten entsprechen.
- Kündigungsfrist nur als Eingabe je Kündigung, kein Vertragsfeld (WS-01-Q2); Dauer des Fristtyps
  Kautionsabrechnung noch nicht hinterlegt (WS-01-Q1).
- Kein Mieterwechsel-Assistent, der Beenden und Neuanlage verbindet.
- Keine automatische Mitteilung an den Messdienstleister.
