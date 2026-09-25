# Makler

## Zweck

Der Bereich Makler bündelt Anzeigen für Vermietung und Verkauf, den FLOW-Import aus dem
bisherigen Müller FLOW sowie Übergabeprotokolle. FLOWFACT bleibt der Kanal zu den
Immobilienportalen: die Plattform sendet, FLOWFACT inseriert.

## Anzeigen

Neue Anzeige entsteht aus einem Verwaltungsobjekt und einer Einheit; Stammdaten (Adresse,
Fläche, Zimmer, Baujahr, Miete oder Kaufpreis) werden vorbelegt. Reiter Vermietung und
Verkauf trennen die Anzeigenarten. Pflichtangaben umfassen unter anderem
Adressfreigabe (vollständige Adresse oder nur PLZ und Ort) und den Energieausweis-Status.
Die Warmmiete wird serverseitig berechnet (Kaltmiete plus Nebenkosten plus Heizkosten,
außer die Heizkosten sind bereits Teil der Nebenkosten); der angezeigte Wert vor dem
Speichern ist nur eine Vorschau. Die Übergabe an FLOWFACT selbst folgt erst, sobald die
Schnittstellendokumentation vorliegt.

## OpenImmo-Export

Je Anzeige und als Sammelexport lässt sich eine OpenImmo-1.2.7-Datei erzeugen, mit
vorheriger Vollständigkeitsprüfung. Die Adresse erscheint im Export nur entsprechend der
gesetzten Adressfreigabe; ein Portalupload findet nicht statt.

## FLOW-Import

Unter Makler, FLOW-Import wird ein SQL-Datenbankexport aus dem bisherigen Müller FLOW
hochgeladen und vor der Übernahme geprüft. Es erfolgt kein Zugriff auf FLOWFACT selbst,
nur ein Dateiimport.

## Übergabeprotokoll

Ein Übergabeprotokoll entsteht aus einem Objekt und einer Einheit (Adresse, Etage,
Einheit werden vorbelegt) oder wird manuell erfasst.

### Manuelles Objekt

Umschalter Objekt aus dem Bestand / Objekt manuell erfassen: Bei einem Objekt, das nicht
im Bestand geführt wird, lassen sich Straße, Hausnummer, PLZ, Ort, Etage, Bezeichnung der
Einheit, externe Objektnummer und Eigentümer frei eintragen. Kein Feld ist Pflicht, alle
Angaben bleiben im Protokoll änderbar.

### Gehilfenzugang

Über Gehilfenzugänge lässt sich ein Mieter, Übernehmer oder Eigentümer einladen, das
Protokoll selbst im Portal auszufüllen (Art des Zugangs, 30 Tage gültig). Die Einladung
entsteht als E-Mail-Entwurf im Postausgang und braucht eine Freigabe; ist kein Postfach
hinterlegt, wird stattdessen ein Einladungscode angezeigt, der einmalig zu übermitteln
ist.

### Abschluss und Zustellung

Protokoll verbindlich abschließen schreibt das Protokoll fest, erzeugt ein PDF auf dem
Briefbogen des Mandanten und legt es in der Dokumentenverwaltung ab; danach sind keine
Änderungen mehr möglich (nur eine neue Version). Trotz Hinweisen verbindlich abschließen
überschreibt offene Hinweise bewusst. Zustellung vorbereiten legt für jeden Beteiligten
mit Kontakt im CRM einen E-Mail-Entwurf an; der Versand läuft über den Postausgang mit
Vier-Augen-Freigabe.

### U-Protokoll-Übernahme

Bestehende Protokolle aus der bisherigen Anwendung U-Protokoll (MariaDB-Dump) lassen sich
mit Vorschau vor der Übernahme prüfen; Dateien werden per ZIP mit Prüfsummenabgleich
übernommen. Die Übernahme ist idempotent je Quelldatensatz (ein erneuter Lauf legt keine
Duplikate an). Details siehe Kapitel Datenübernahmen.

## Was ist Vorschlag, was verbindlich

Vorbelegte Stammdaten, die Warmmiete-Vorschau und der OpenImmo-Export vor Freigabe sind
Vorschläge bzw. Entwürfe. Verbindlich wird ein Übergabeprotokoll erst mit Protokoll
verbindlich abschließen; eine Anzeige wird erst mit der tatsächlichen Übergabe an
FLOWFACT wirksam.

## Häufige Fehler

- **FLOW-Import bricht ab**: Der SQL-Export entspricht nicht dem erwarteten Format;
  Export erneut aus Müller FLOW ziehen.
- **Gehilfe kann sich nicht anmelden**: Der Zugang ist abgelaufen (30 Tage) oder wurde
  beendet; über Zugang einrichten neu anlegen.
- **Protokoll lässt sich nicht abschließen**: Es liegen Hinweise vor (z. B. fehlende
  Unterschrift); entweder beheben oder bewusst mit Trotz Hinweisen verbindlich
  abschließen fortfahren.
