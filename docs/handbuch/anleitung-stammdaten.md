# Handlungsanweisung: Stammdaten anlegen und pflegen

Stand: 28.09.2026. Betrifft Objekte, Gebäude, Einheiten und Kontakte. Schreibweisen,
Pflichtfelder und Titelmuster regeln die [Erfassungsstandards](erfassungsstandards.md).
Bedienung der Direktbearbeitung (Stift am Feld, Konflikthinweis) im Kapitel
[Stammdaten direkt bearbeiten](bearbeiten.md).

## Zweck

Stammdaten sind die Grundlage für Verträge, Sollstellungen, Abrechnungen, Serienbriefe und das
Portal. Jede Angabe wird einmal am richtigen Datensatz geführt und nicht in Freitexten
wiederholt. Änderungen stehen im Ereignisprotokoll des Datensatzes.

## Wann anwenden

- Neues Objekt, neuer Kontakt, neue Einheit.
- Änderungsmitteilung (Anschrift, Telefon, E-Mail, Name) per Mail, Brief, Telefon oder Portal.
- Korrektur fehlerhafter Angaben.

## Voraussetzungen

- Lesen: `properties:read`, `contacts:read`. Ändern: `properties:update`, `contacts:update`.
  Anlegen: `properties:create`, `contacts:create`.
- Löschen (`*:delete`) hat in der Vorbelegung nur der Mandantenadministrator (Regel
  `docs/rules/M2-07.md`). Kontakte werden grundsätzlich gesperrt statt gelöscht.
- Solange Immoware24 führend ist, sind Änderungen auch dort nachzuziehen; die Plattform
  schreibt nicht nach Immoware24 zurück.

## Objekt

### Anlegen

Übersicht, Objekte, Objekt anlegen: Objektnummer (3 Ziffern, je Mandant eindeutig), Name,
Verwaltungsart, Straße, Hausnummer, PLZ, Ort, Bundesland, Anlegen. Die Verwaltungsart legt die
Rechtsträger fest und ist danach nicht mehr änderbar.

### Pflegen

Objektseite (Klick auf das Objekt in der Objektliste):

1. Abschnitt Stammdaten: Name, Anschrift, Grundbuchangaben, Flächen, Garten, Sanierung,
   Umlageausfallwagnis, Verwaltungsbeginn, Verwaltungsende, Bemerkungen.
2. Abschnitt Gebäude: Klick auf den Gebäudenamen öffnet die Gebäudeseite mit Stammdaten des
   Gebäudes und Energieausweis (Schaltfläche Energieausweis speichern). Werte nur aus dem
   Ausweis übernehmen; der Ablauf des Energieausweises erscheint in der Fristenliste.
3. Abschnitt Abrechnungszeiträume, Bankkonten des Objekts (Als Standard setzen), Objektmappe
   und Schwarzes Brett nach Bedarf.
4. Eigentümer einer Mietverwaltung: Abschnitt Eigentümer, Eigentümer festlegen oder ersetzen.
   Verrechnungskonto, Verwaltervollmacht und Steuerberater: darunter Schaltfläche Details für
   [Name] bearbeiten. Das Verrechnungskonto ist ein Sachkonto eines Buchungskreises des
   Objekts, die Vollmacht ein bereits am Objekt abgelegtes Dokument, der Steuerberater ein
   Kontakt aus der Kontaktsuche. Alle drei sind Verweise ohne Buchungswirkung.
5. Abschnitt Ansprechpartner: Ansprechpartner zuordnen (Kontaktsuche, Kategorie aus dem
   Katalog Ansprechpartnerkategorien, Gültig ab, Sichtbarkeit im Portal für Mieter,
   Eigentümer oder Dienstleister). Bearbeiten ändert Kategorie, Zeitraum und Sichtbarkeit;
   Beenden setzt das Ende auf den heutigen Tag. Eine falsche Person wird beendet und neu
   zugeordnet, der Kontakt einer Zuordnung ist nicht änderbar.
6. Abschnitt Zähler: Zähler anlegen mit Zählernummer, Zählerart (Katalog Zählerarten),
   Einheit oder gesamtes Objekt, Standort, Anschluss (Haupt- oder Unterzähler), Gültig ab,
   Eichfrist und Fernauslesbarkeit. Bearbeiten ändert alles außer der Nummer. Ein
   ausgetauschtes Gerät wird über Zählerwechsel erfasst: Wechseldatum, Endstand alt,
   Anfangsstand neu, optional neue Zählernummer. Die Eichfrist erscheint in der Fristenliste.
7. Abschnitt Wartungen und Prüfpflichten: Wartung anlegen mit Bezeichnung, Art (Wartung,
   Prüfung, Modernisierung, Gewährleistung), Intervall in Monaten, nächster Fälligkeit,
   Erinnerung, Dienstleister (aus den Dienstleisterverhältnissen des Objekts) und Einheit.
   Erledigt erfasst das Erledigungsdatum: mit Intervall rückt die Fälligkeit um das Intervall
   nach dem Erledigungsdatum vor und der Eintrag bleibt offen, ohne Intervall wird er
   geschlossen. Das Intervall ist eine Betreibereingabe; die Plattform hinterlegt keine
   Prüfzyklen (zu verifizieren, offener Punkt STAMM-01).
8. Abschnitt Zusatzfelder: Werte bearbeiten zeigt je definiertes Feld ein Eingabefeld
   passend zum Typ; Speichern prüft die Version des Objekts (Hinweis bei zwischenzeitlicher
   Änderung, dann Seite neu laden). Neues Zusatzfeld (nur mit dem Recht
   `tenant_settings:update`) legt ein Feld für alle Objekte des Mandanten mit Bezeichnung,
   Schlüssel, Typ und bei Einzelauswahl den Auswahlwerten an; weitere Eigenschaften unter
   Einstellungen, Zusatzfelder. Felder vom Typ Verknüpfung werden nur angezeigt.

## Gebäude und Einheiten

### Gebäude anlegen

Objektseite, Abschnitt Gebäude, Schaltfläche Gebäude anlegen: Bezeichnung (Pflicht), Straße,
Hausnummer, Adresszusatz, Baujahr, Geschosse, Anlegen. Steht die Hausnummer im Feld Straße,
erscheint der Hinweis nach Erfassungsstandard ES-03; er sperrt nicht. Flächen, Bauweise,
Energieausweis und weitere Angaben danach auf der Gebäudeseite pflegen (Klick auf den
Gebäudenamen). Voraussetzung ist `properties:create`; bei beendeten Objekten fehlt die
Schaltfläche. Daneben bleiben der Import
([Objekte und Einheiten aus der Immoware24-Objektliste](import-objektdaten.md)) und die
Schnittstelle.

### Einheit anlegen

Objektseite, Abschnitt Einheiten, Schaltfläche Einheit anlegen (auch auf der Gebäudeseite mit
vorbelegtem Gebäude): Gebäude, Nummer und Art sind Pflicht; Bezeichnung, Lage, Etage,
Wohnfläche, Gesamtfläche und Zimmer optional (Dezimalzahlen mit Komma, zum Beispiel 65,5).
Die Nummer muss im Objekt eindeutig sein; das Formular meldet eine bereits vergebene Nummer
vor dem Speichern, die Schnittstelle lehnt Dubletten ab. Nach dem Anlegen führt der Link
Einheit öffnen auf die Einheitenseite. Ohne Gebäude im Objekt zuerst ein Gebäude anlegen.

### Einheit ändern

Objektseite, Tabelle Einheiten, Klick auf die Einheit. Im Abschnitt Stammdaten der Einheit
Nummer, Bezeichnung, Art, Lage, Etage, Flächen, Zimmer, Ausstattung, Anschrift,
Untergemeinschaft, Umsatzsteuer bei Leerstand, Provision, Kaution direkt ändern.

### Umlageschlüssel und Schlüsselwerte

Objektseite, Abschnitt Umlageschlüssel und Schlüsselwerte:

1. Stichtag wählen (Vorbelegung heute). Die Tabelle zeigt je Schlüssel Maßeinheit, Art,
   Sollsumme, Summe der Einheitenwerte zum Stichtag, Abweichung und die Zahl der Einheiten
   ohne Wert.
2. Sollsumme je Schlüssel eintragen und Speichern (zum Beispiel die Summe der
   Miteigentumsanteile laut Teilungserklärung). Die Sollsumme ist ein Betreiberwert ohne
   Vorgabe und zu verifizieren; ohne Sollsumme (zum Beispiel Personen) bleibt das Feld leer.
3. Weicht die Summe von der Sollsumme ab, erscheint die Summenprüfung als Warnung. Sie
   sperrt nichts; Grundlage (Teilungserklärung, Aufmaß, Beschluss) und Gültigkeitszeiträume
   prüfen und den fehlenden oder falschen Wert erfassen.
4. Schlüsselwert erfassen: Einheit, Umlageschlüssel, Wert, Gültig ab (Pflicht), Gültig bis
   (optional), Wert speichern. Ein neuer Wert schließt den offenen Vorwert am Vortag, die
   Historie bleibt erhalten. Eine Änderung nie rückwirkend eintragen, ohne dass die Grundlage
   als Dokument an der Einheit abgelegt ist.
5. Umlageschlüssel anlegen: Kürzel (Großbuchstaben, Ziffern, Unterstrich, im Objekt
   eindeutig, danach nicht änderbar), Bezeichnung, Maßeinheit, Art, Sollsumme.

Die Matrix Werte je Einheit zeigt zum Stichtag nur Schlüssel mit Werten oder Sollsumme;
Alle Schlüssel anzeigen blendet die übrigen ein. Flächen und Schlüsselwerte wirken auf
Abrechnungen; die Abrechnung liest sie erst nach den Freigaben G3 und G4. Umlagewerte bei
Leerstand: Abschnitt Umlagewerte bei Leerstand der Einheitenseite.

## Kontakte

### Anlegen

Übersicht, Kontakte, Kontakt anlegen (Seite Neuer Kontakt, auch über `Strg+K`, Aktion Kontakt
anlegen).

1. Art Person oder Firma. Bei Person Vor- oder Nachname Pflicht, bei Firma der Firmenname.
2. Anrede, Briefanrede, Titel, Sprache, bevorzugter Kanal.
3. Adressen, Telefonnummern, E-Mail-Adressen; je Art genau ein Eintrag als primär. Genau eine
   E-Mail-Adresse darf als Portalzugang markiert sein.
4. Rollen (Klassifizierung: Eigentümer, Mieter, Verwalter, Dienstleister, Bank, Sonstiges) und
   Schlagworte.
5. Bankverbindungen nur hier bei der Neuanlage und nur mit Nachweis erfassen; jede IBAN wartet
   danach auf Freigabe durch eine zweite Person, siehe
   [Bankverbindung](anleitung-bankverbindung.md).
6. Speichern. Meldet die Dublettenprüfung einen ähnlichen Kontakt, zuerst die Trefferliste
   prüfen. Trotzdem speichern nur, wenn es wirklich eine andere Person ist.

### Ändern

- Kontaktseite, Reiter Stammdaten: Anrede, Briefanrede, Titel, Name, Firma, Rechtsform,
  Position, Geburtsdatum, Sprache, bevorzugter Kanal, Notizen direkt ändern.
- Adressen, Telefonnummern, E-Mail-Adressen, Rollen und Schlagworte: Schaltfläche Bearbeiten
  (Seite Kontakt bearbeiten).
- Vorschläge aus dem Portal: Reiter Kommunikation beziehungsweise Abschnitt Vorschläge aus dem
  Portal, je Vorschlag Übernehmen oder Ablehnen.
- Die Mitteilung selbst (Mail, Brief, Telefonnotiz) als Dokument am Kontakt ablegen oder im
  Ticket belassen und im Ticket die Erledigungsart Stammdaten ergänzt wählen.

### Beziehungen

Die Zeilen im Abschnitt Beziehungen zu Objekten und Einheiten entstehen aus Verträgen und
Eigentümerzuordnungen und werden nicht von Hand gepflegt. Wer einen Kontakt einer Einheit
zuordnen will, legt den Vertrag an (Verwaltung, Verträge, Vertrag anlegen).

### Sperren statt löschen

Kontaktseite, Bearbeiten, Kennzeichen Kontakt gesperrt setzen und speichern; das Sperrdatum
wird automatisch gesetzt. Die Kontaktliste zeigt mit dem Filter Nur gesperrte Kontakte die
Sperrliste. Löschen nur im Vier-Augen-Prinzip und nur mit
freigegebenem Aufbewahrungsprofil; siehe [Kontakte](kontakte.md), Abschnitt Sperre und
Löschdatum.

## Fristen

Aus den Stammdaten entstehen automatisch Einträge in der Fristenliste (Übersicht, Fristen), zum
Beispiel Eichfrist Zähler, Energieausweis läuft ab, Vertragsende. Eigene Wiedervorlagen für
Stammdaten: Kontaktseite, Reiter Notizen, Notiz hinzufügen mit Wiedervorlage; der Eintrag
erscheint als Typ Wiedervorlage in der Fristenliste.

## Freigaben

| Schritt | Wer | Durch die Software erzwungen |
| --- | --- | --- |
| Neue oder geänderte IBAN | zweite Person mit `contacts:approve` | ja |
| Löschen eines Kontakts | Vier-Augen-Prinzip, Mandantenadministrator | ja |
| Übrige Stammdatenänderungen | keine Freigabe | nein, Ereignisprotokoll |

## Checkliste

- [ ] Dublettenprüfung beachtet
- [ ] Pflichtfelder nach Erfassungsstandards vollständig
- [ ] Rollen gesetzt
- [ ] Nachweis der Änderung abgelegt
- [ ] Änderung in Immoware24 nachgezogen, solange Immoware24 führt
- [ ] Bei Flächen oder Schlüsselwerten: Gültigkeitsbeginn und Grundlage dokumentiert
- [ ] Summenprüfung der Umlageschlüssel ohne Abweichung oder Abweichung geklärt

## Häufige Fehler

- Zweiter Kontakt für dieselbe Person über Trotzdem speichern.
- Anschrift im Notizfeld statt im Adressfeld.
- Rolle Mieter oder Eigentümer von Hand gesetzt, ohne Vertrag: Beziehung fehlt trotzdem.
- IBAN im Notizfeld oder in einer Ticketnotiz erfasst.
- Speicherkonflikt ignoriert: bei Hinweis auf eine zwischenzeitliche Änderung Seite neu laden.

## Lücken in der Software

- Umlageschlüssel: Kürzel, Bezeichnung, Maßeinheit und Art bestehender Schlüssel nur über die
  Schnittstelle änderbar (`PATCH /properties/{id}/allocation-keys/{kid}`); in der Oberfläche
  nur die Sollsumme. Löschen von Schlüsseln und Werten nicht vorgesehen.
- Zählerstände (Ablesungen) werden nicht auf der Objektseite erfasst, nur Zähler und
  Zählerwechsel; Ablesungen weiter über die Einheitenseite, das Übergabeprotokoll oder die
  Schnittstelle.
- Zusatzfelder vom Typ Verknüpfung (Kontakt, Dokument, Objekt) nur über die Schnittstelle.
- Kein Rückschreiben nach Immoware24; Doppelpflege im Parallelbetrieb.

## Pflege in Welle 2 (Stand 30.09.2026)

* Notizen am Kontakt: je Notiz die Schaltflächen Ändern, Anheften und Löschen. Löschen fragt nach und wird im Änderungsprotokoll festgehalten.
* Fremdsystem-Kennungen: im Kontaktformular stehen Immoware24 Kennung und Lexware Office Kundennummer. Ein leeres Feld entfernt den Eintrag.
* SEPA Mandate: unter Verträge die Schaltfläche SEPA Mandate. Filter nach Status, nie verwendet und Ablauf innerhalb von 90 Tagen. Abgelaufene Mandate setzt ein nächtlicher Lauf auf abgelaufen, der Lastschrifteinzug für die betroffenen Verträge endet dann wie beim Widerruf. Der Einzug selbst bleibt bis zur Freigabe Zahlungsanstoß gesperrt.
* Zahlungszeilen und Zahlungspläne eines Vertrags lassen sich über die Schnittstelle korrigieren. Liegt bereits eine gebuchte Sollstellung vor, bleiben Betrag, Zeitraum und Art gesperrt, die Korrektur erfolgt dann über eine neue Position und den Storno im Buchungskreis.

* Abrechnungszeiträume: in der Objektansicht zeigt die Tabelle den Status (Offen, Ergebnisse erstellt, Bestätigt, Abgeschlossen). Die Schaltfläche rechts daneben setzt den nächsten Status. Abschließen sperrt den Zeitraum, er lässt sich danach weder löschen noch zurücksetzen. Der Status bucht nichts.
* Dokumente: Energieausweis am Gebäude sowie Wartungsposten und Dienstleisterverhältnisse nehmen Verweise auf Dokumente des Dokumentenarchivs auf (Schnittstelle, Feld documents).
