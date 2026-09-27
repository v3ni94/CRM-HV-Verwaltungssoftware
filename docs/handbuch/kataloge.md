# Kataloge und benutzerdefinierte Felder

Stand 27.09.2026, Paket P1 AP4 (Spezifikation 4.11 und Anhang B).

## Kataloge

Unter Einstellungen, Kataloge pflegt der Mandant alle Auswahllisten aus Anhang B der
Spezifikation, zum Beispiel Kontaktgruppen, Gewerke, Kautionsarten, Zustellwege,
Versammlungstypen oder Ticketprioritäten. Jede Liste ist ein Katalog mit Einträgen aus
Code (interner Schlüssel) und Bezeichnung.

Zwei Arten von Einträgen:

* Systemeinträge stammen aus Anhang B und werden für jeden Mandanten angelegt. Sie lassen
  sich umbenennen, in der Reihenfolge ändern und deaktivieren, aber nicht löschen, weil
  bestehende Datensätze ihre Codes verwenden. Ein deaktivierter Eintrag erscheint in keiner
  Auswahl mehr, bleibt an bereits gespeicherten Datensätzen aber lesbar.
* Eigene Einträge ergänzt der Mandant mit Code und Bezeichnung. Sie lassen sich löschen,
  solange sie nicht mehr benötigt werden.

Der Code ist nach dem Anlegen unveränderlich. Lesen erfordert das Recht Objekte lesen,
Pflegen das Recht Mandanteneinstellungen ändern. Jede Änderung wird im Ereignisprotokoll
festgehalten.

Hinweis zu vorhandenen Feldern: Einige Listen sind im Programmcode fest hinterlegt, etwa
Verwaltungsart, Art der Einheit, USt-Option, Zahlungsintervall, Ticketstatus und
Versammlungstyp. Diese Felder prüfen weiterhin gegen die feste Liste; der zugehörige Katalog
dient der Anzeige und der Erweiterung neuer Felder (Betreiberentscheidung 27.09.2026). Eine
Umstellung dieser Felder auf Kataloge ist ein späteres Paket.

## Benutzerdefinierte Felder

Unter Einstellungen, Felder definiert der Mandant Zusatzfelder für Objekt, Gebäude, Einheit,
Vertrag, Kontakt, Dienstleister und Dienstleistervertrag. Je Feld:

| Attribut | Bedeutung |
| --- | --- |
| Entität, interner Name, Feldtyp | nach dem Anlegen unveränderlich, weil gespeicherte Werte davon abhängen |
| Bezeichnung, Gruppe, Beschreibung, Reihenfolge | Anzeige in der Oberfläche |
| Feldtyp | Anhang B.28: Ganzzahl, Nummer, Betrag, Ja/Nein, Datum, Datum und Uhrzeit, Zeichenkette, Text, formatierter Text, Kontaktverknüpfung, Dokumentverknüpfung, Objektverknüpfung, Einzelauswahl, URL |
| Gültig für Verwaltungsarten und Vertragsarten | leer bedeutet gültig für alle |
| Eindeutigkeit | nicht, im Vertrag, in allen Verträgen |
| Pflichtfeld, sichtbar in Hauptansicht | Verhalten in Formularen |
| Minimum, Maximum | bei Zahlen der Wertebereich, bei Texten die Länge |
| Standardwert, Auswahlwerte | Vorbelegung, Werte der Einzelauswahl |

Beim Speichern eines Datensatzes prüft die Plattform Typ, Wertebereich und Auswahlwerte.
Wird eine Felddefinition gelöscht, bleiben bereits gespeicherte Werte im Datensatz erhalten;
beim nächsten vollständigen Speichern des Datensatzes muss der Schlüssel entfallen.

Noch nicht umgesetzt: Prüfung der Gültigkeit je Verwaltungsart und Vertragsart sowie der
Eindeutigkeit beim Speichern (Attribute werden gespeichert und angezeigt). Beides folgt mit
der Nutzung der Felder in den Formularen der Detailseiten.
