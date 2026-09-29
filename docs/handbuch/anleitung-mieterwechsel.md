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

### Übergabe am Tablet oder Handy

Die Übergabe wird im Browser des Geräts erfasst, ohne eigene App. Anmelden wie am
Arbeitsplatz; das Menü öffnet sich über das Symbol links oben (Handy und Tablet hochkant)
oder über die schmale Leiste links (Tablet quer). Dort Makler, Übergabeprotokolle.

1. Liste: am Handy erscheinen die Protokolle als Karten mit Nummer und Fassung, Status,
   Adresse mit Einheit, Beteiligten und Datum; der Chip Heute zeigt nur die Übergaben des
   Tages, Diese Woche die laufende Woche. Weitere Filter (Status, Protokollart, Archiv)
   stehen hinter Filter. Neu legt ein Protokoll mit Einheit aus dem Bestand oder mit
   manueller Adresse an.
2. Aufbau des Editors: oben die Schrittleiste zum Wischen mit einem Zähler je Schritt und
   einem Statuspunkt (grau leer, grün ausgefüllt, gelb mit Hinweis). Unten Zurück und
   Weiter; Speichern liegt in der unteren Leiste über der Tastatur. Ein Schrittwechsel mit
   ungespeicherten Eingaben fragt nach: Hier bleiben behält die Eingabe, Verwerfen wechselt.
3. Objekt und Beteiligte: Telefon, E-Mail und PLZ öffnen die passende Tastatur; Beteiligte
   lassen sich über die Kontaktsuche übernehmen.
4. Zähler: Zählerstand mit Dezimaltastatur, Foto direkt beim Anlegen über Foto aufnehmen
   oder Aus Galerie wählen (auch iPhone Fotos im HEIC Format). Nach dem Speichern zeigt jede
   Datei ihren Stand: Wartet, Wird hochgeladen, Fertig, Fehlgeschlagen mit Erneut versuchen
   (nur diese Datei) oder Später (das Formular schließt, das Foto kann später nachgereicht
   werden).
5. Räume und Mängel: Mangel mit Raum, Priorität, Status und Foto in einem Schritt anlegen.
   Fotos erscheinen als Kacheln; Tippen öffnet die Galerie zum Wischen; Entfernen fragt nach
   und erklärt, wann die Datei endgültig gelöscht wird.
6. Schlüssel, Gegenstände, Bemerkungen (Intern erscheint nie im PDF), Anhänge.
7. Unterschriften: Einwilligungstext lesen, dann Unterschrift von Beteiligtem antippen, das
   Gerät übergeben, Fläche im Vollbild unterschreiben, Rückgängig und Leeren stehen bereit;
   Weitere Person für Zeugen oder Bevollmächtigte ohne Eintrag. Höchstens eine gültige
   Unterschrift je Person; löschen nur vor dem Abschluss.
8. Nach der ersten Unterschrift sind Räume, Mängel, Zähler, Schlüssel, Gegenstände,
   Bemerkungen, Fotos und die Protokollangaben gesperrt. Muss doch etwas geändert werden:
   Änderung nach Unterschrift antippen, Änderungsgrund eingeben, bestätigen. Grund,
   Zeitpunkt und Bearbeiter stehen danach im Protokoll und im PDF; alle bisherigen
   Unterschriften gelten als vor der Änderung geleistet und müssen erneut eingeholt werden.
   Beteiligte und interne Angaben bleiben auch mit Unterschrift änderbar.
9. Prüfung und Abschluss zeigt die Zusammenfassung mit Hinweisen und Sprung zum Schritt;
   Protokoll verbindlich abschließen fragt nach, bei Hinweisen als Trotz Hinweisen. PDF
   ansehen öffnet im selben Fenster, Zurück führt zum Protokoll. Zustellung vorbereiten
   erzeugt nur Entwürfe für die Vier Augen Freigabe im Postausgang.

### Protokoll später einsehen

Abgeschlossene Protokolle öffnen als Leseansicht ohne Eingabefelder: Kopf mit Nummer,
Fassung, Status, Adresse und Datum; Beteiligte mit Anrufen und E-Mail direkt aus der
Ansicht; Zählerstände; Räume mit ihren Mängeln und Fotos, Mängel ohne Raum in einem eigenen
Block; Schlüssel, Gegenstände, Bemerkungen (Intern gekennzeichnet); Anhänge; der Verlauf
Änderungen nach Unterschrift, falls vorhanden; Unterschriften mit Zeitpunkt, ungültige mit
Kennzeichnung; PDF ansehen. Änderungen sind nur als neue Fassung mit Änderungsgrund
möglich. Weder das Öffnen der Ansicht noch ein Lesestatus sind ein Zustellnachweis; die
Zustellung läuft über den Postausgang.

### Hinweise für den Betrieb vor Ort

- Eingaben werden nur beim Speichern übertragen. Ohne Empfang erscheint der Hinweis Keine
  Verbindung; die Eingaben bleiben auf der Seite bis zum erneuten Speichern (Erneut
  senden). Die Seite nicht neu laden. Mit dem Schalter Offline Erfassung (Einstellungen,
  Mandant) gilt stattdessen der Abschnitt Offline Erfassung unten.
- Fotos werden vor dem Senden auf dem Gerät verkleinert; Metadaten wie der Aufnahmeort
  werden auf dem Server entfernt.
- Entfernen eines Fotos löst nur die Verknüpfung dieser Fassung; ist das Foto in keiner
  anderen Fassung verknüpft, wird die Datei endgültig gelöscht.
- Das Gerät beim Unterschreiben nicht unbeaufsichtigt lassen und nach der Unterschrift
  zurücknehmen.

### Offline Erfassung (Schalter je Mandant, Regel M30-10)

Ist in den Einstellungen unter Mandant der Schalter Offline Erfassung Übergabeprotokoll
aktiv, arbeitet der Editor am Handy oder Tablet auch ohne Empfang weiter:

1. Ohne Verbindung erscheint oben der Hinweis Keine Verbindung. Offline Erfassung aktiv
   mit der Zahl der wartenden Änderungen. Räume, Mängel, Zähler, Schlüssel, Gegenstände,
   Bemerkungen, Beteiligte, Fotos, Anhänge, Protokollfelder und Unterschriften lassen sich
   wie gewohnt speichern; sie werden verschlüsselt auf dem Gerät zwischengespeichert und
   in der Liste mit Wartet auf Abgleich gekennzeichnet (Fotos ohne Vorschau). Löschen von
   Fotos und Unterschriften, Abschluss, Storno, neue Fassung und Zustellung brauchen eine
   Verbindung.
2. Die Seite nicht neu laden, den Tab nicht schließen und sich nicht abmelden, solange
   Änderungen warten: der Schlüssel liegt nur im Speicher der Sitzung, danach sind die
   wartenden Änderungen unlesbar und werden gelöscht (Hinweis lokale Entwürfe waren nicht
   mehr lesbar). Das ist gewollt, damit auf einem geteilten Gerät nichts Lesbares bleibt.
3. Sobald die Verbindung zurück ist, überträgt der Editor die Änderungen von selbst in der
   Reihenfolge der Erfassung (Jetzt abgleichen stößt sie auch von Hand an). Jede Änderung
   trägt die Gerätezeit der Erfassung; der Server speichert sie als vom Gerät gemeldet
   neben seiner eigenen Zeit, das PDF druckt bei Unterschriften beide.
4. Weist der Server eine Änderung ab (Protokoll inzwischen abgeschlossen, Inhalt nach
   einer Unterschrift gesperrt, Berechtigung fehlt), hält die Übertragung an und zeigt den
   Grund; die übrigen Änderungen bleiben auf dem Gerät. Ist der Stand auf dem Server jünger
   als die Kopie, auf der die Änderung beruht, fragt der Editor mit beiden Ständen:
   Serverstand behalten verwirft die eigene Änderung, Meine Änderung übernehmen sendet sie
   erneut. Nichts wird von allein entschieden.
5. Das Abgleichsprotokoll unter dem Hinweis zeigt je Protokoll, was wann übertragen,
   abgelehnt, verworfen oder erneut eingereiht wurde (nur für diese Sitzung).
6. Lokale Entwürfe löschen entfernt alle wartenden Änderungen dieses Protokolls vom Gerät.
   Abmelden löscht die Warteschlange immer.

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
