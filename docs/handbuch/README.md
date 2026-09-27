# Handbuch

Stand: 26.09.2026, Version 1.25.0. Kapitel zu den Versionen 1.20 bis 1.22 ergänzt am
26.09.2026 (Tickets mit Mailverlauf und TNR#, Automatisierung, Portal, WEG, Kommunikation,
Dienstleisterverträge, IBAN-Freigabe, Energieausweis, Belegeingang, Einstellungen); Abschnitte
zu 1.23.0 bis 1.25.0 ergänzt am 26.09.2026 (Erledigte ausblenden, Statusauswahl nach Rolle,
Erledigungsnotiz und Lernen, Telefonassistenz Hallo Heidi, Wissen, Objektbezüge im Kontakt,
Gmail-Archivierung, Listenimport mit Zuordnung, Rolle aus der Chatanweisung).
Produktive Buchführung, Zahlungen und Abrechnungen sind gesperrt (Freigabestufen G1 bis G5,
Abschnitt 18.0). Die Plattform zeigt keine Geldkennzahlen, solange G1 nicht freigegeben ist.

Dieses Handbuch richtet sich an Mitarbeiterinnen und Mitarbeiter der Hausverwaltung Müller
GmbH; das Kapitel Portal zusätzlich an Mieter, Eigentümer, Beiratsmitglieder und
Dienstleister. Es beschreibt die Oberfläche mit den dort verwendeten Bezeichnungen, nicht den
Programmcode. Jedes Kapitel nennt Zweck, Voraussetzungen (Rechte, Freigabestufen), Ablauf und
Grenzen (Entwurf, keine Rechtsfolge, Freigabestufe gesperrt).

## Inhaltsverzeichnis

Grundlagen

- [Start und Auswertungen](start-auswertungen.md)
- [Auswertung Tickets (Durchsatz, Rückstand, Reaktionszeiten, je Bearbeiter und Postfach)](auswertung-tickets.md)
- [Objekte und Einheiten](objekte-einheiten.md) (mit Energieausweis und Schwarzem Brett)
- [Verträge (Miete, WEG, SEV, Kautionen mit Kautionsabrechnung, Dienstleisterverträge mit Kündigungsfristen)](vertraege.md)
- [Kontakte (mit IBAN-Freigabe im Vier-Augen-Prinzip, Beziehungen zu Objekten und Einheiten)](kontakte.md)
- [Kalender](kalender.md)

Vorgänge und Kommunikation

- [Tickets (Mailverlauf, Antworten mit TNR#, Anhänge, Wiedereröffnung, Terminvorschläge, Erledigungsnotiz, Telefonassistenz)](tickets.md)
- [Mail (Vorbereitung, Freigabe, Archivierung bei Abschluss, Telefonassistenz)](mail.md)
- [Kommunikation (Telefonie-Anrufliste, Zustellungen, ausgehende Webhooks)](kommunikation.md)
- [Automatisierung (Regeln Stufe 1 und 2, Zeitpläne, Testlauf, Protokoll)](automatisierung.md)
- [Portal (Mieter, Eigentümer, Beirat, Dienstleister, Formulare, Schwarzes Brett, PWA)](portal.md)

Dokumente und Belege

- [Dokumente und DMS (Paperless, Belegeingang)](dokumente-dms.md)
- [Belegeingang (mit automatischem Eingang und Maskierung)](belegeingang.md)

Finanzen

- [Buchhaltung (Buchungskreis, Sollstellung, offene Posten, Bankabgleich, Mahnwesen, Zahlläufe)](buchhaltung.md)
- [Banking](banking.md)
- [WEG (Versammlung, Beschlüsse, Mehrheitsregeln, Abrechnung mit Überleitungsrechnung, Darlehen, Versicherungsfälle, Maßnahmen, Prüfauftrag, Einsichtsanfragen)](weg.md)
- [Abrechnung Miete (Betriebskosten, Eigentümerabrechnung)](abrechnung-miete.md)

Vermietung und Makler

- [Makler (Anzeigen mit Energieausweis und Angebotsmiete, OpenImmo, Übergabeprotokoll)](makler.md)

Datenübernahme und Importe

- [Datenübernahmen](datenuebernahmen.md)
- [Objekte und Einheiten aus der Immoware24-Objektliste](import-objektdaten.md)
- [Kontakte aus den Immoware24-Kontaktlisten](import-kontakte.md)
- [Eigentümer und Mieter den Einheiten zuordnen (Listenimport, Zuordnung)](import-zuordnung.md)
- [Abgleichbericht im Parallelbetrieb](import-abgleichbericht.md)

System

- [Einstellungen (Benutzer, Rollen, Postfächer mit Telefonassistenz, DMS, SLA, KI, Wissen, Telefonie, Portalformulare, Automatisierung, WEG, Kautionszinsen, DATEV)](einstellungen.md)
- [Messdienstleister (Verbindungen, Einrichtungsassistent, Zuordnungsübersicht, CSV, Objektreiter, Einheitenzuordnung, Abruf)](messdienstleister.md)

Die folgenden Abschnitte fassen die Grundfunktionen der Startseite zusammen; Einzelheiten zu
Auswertungen stehen im verlinkten Kapitel.

## Anmelden und Mandant wählen

Anmeldung mit E-Mail und Passwort. Das Passwort ist 6 bis 128 Zeichen lang und beginnt oder endet nicht mit einem Leerzeichen (Betreiberentscheidung vom 26.09.2026); nach 10 Fehlversuchen ist das Konto 15 Minuten gesperrt. Der zweite Faktor (Einmalcode aus einer Authenticator-App) ist freiwillig: Wer ihn unter Einstellungen, Meine Daten eingeschaltet hat, gibt nach dem Passwort den sechsstelligen Code ein und kann dabei Dieses Gerät 90 Tage merken wählen; auf diesem Gerät wird dann 90 Tage lang kein Code mehr abgefragt. Gemerkte Geräte lassen sich unter Meine Daten einzeln abmelden. Wer mehreren Mandanten angehört, wählt den Mandanten oben rechts. Alle Daten, Suchen und Benachrichtigungen gelten nur für den gewählten Mandanten.

## Start

Die Startseite zeigt Kennzahlen, soweit die eigene Rolle sie sehen darf: Objekte, Einheiten, Kontakte, laufende Verträge, Vertragsenden der nächsten 90 Tage, fällige Wartungen und offene KI-Vorschläge. Darunter stehen Termine und Fristen der letzten und nächsten 30 Tage sowie die Tagesübersicht.

## Fristen

Das Menü Fristen listet Termine aus den Stammdaten mit Vorfrist aus den Einstellungen: Vertragsende, Kündigung, Eichfrist Zähler, Ablauf Bankzustimmung, Ende Aufbewahrung, Kündigungsfrist Dienstleistervertrag (14 Tage Vorfrist) und Beschlussfrist virtuelle Versammlung (7 Tage Vorfrist). Die Liste ist Orientierung und in der Oberfläche als zu prüfen gekennzeichnet; sie ersetzt keine rechtliche Fristberechnung. Notfristen sind nie allein aus der Liste zu führen.

## Suche

`Strg+K` öffnet die Suche über Kontakte, Objekte, Einheiten, Verträge und Dokumente. Pfeiltasten wählen, Eingabe öffnet den Treffer. Ergebnisse erscheinen nur für Bereiche, für die eine Leseberechtigung besteht.

## Kontakte

Liste mit Suche, Filter nach Art und Schlagwort. Ein Filter lässt sich unter einem Namen speichern und später mit einem Klick aufrufen; gespeicherte Filter sieht nur, wer sie angelegt hat. Für mehrere Kontakte gleichzeitig: Zeilen markieren, Schlagwort eingeben, Hinzufügen oder Entfernen. Die Aktion wird ganz oder gar nicht ausgeführt.

## Kalender

Monatsansicht mit eigenen Terminen, Terminen, die Kollegen für alle freigegeben haben, fälligen Wartungen und Vertragsdaten (Ende, Kündigung). Wartungen und Vertragsdaten kommen aus den Stammdaten und werden dort geändert. Eigene Termine lassen sich löschen.

## Benachrichtigungen

Das Menü Benachrichtigungen zeigt ungelesene Hinweise, zum Beispiel fällige oder überfällige Wartungen des Objekts, das man betreut, Fristen mit Vorfrist, neue Mails an eigenen Tickets und interne Benachrichtigungen aus Automatisierungsregeln. Die Erinnerung an Wartungen kommt entsprechend der Vorlaufzeit der Wartung, sonst 14 Tage vorher.

Ein Klick auf eine Benachrichtigung öffnet den Betreff direkt: das Ticket, den Auftrag, die Mail im Postfach, das Dokument, den Vertrag, bei Wartungen die Objektakte, bei Fristen die Fristenliste und bei Terminen den Kalender mit geöffnetem Termin. Die angeklickte Benachrichtigung gilt danach als gelesen; alle anderen bleiben ungelesen. Benachrichtigungen ohne zugehörige Seite lassen sich mit einem Klick nur als gelesen markieren.

## Darstellung

Die Schaltfläche Darstellung wechselt zwischen System, Hell und Dunkel. Die Wahl gilt für den verwendeten Browser.

## Assistent und Importe

Der Assistent schlägt aus Listen Kontakte, Objekte und Verträge vor; nichts wird ohne Bestätigung übernommen, jeder Import lässt sich rückgängig machen. Eine Rolle aus der Chatanweisung (zum Beispiel "Rolle bank hinterlegen", "als Mieter anlegen") wird beim Tabellenimport auf alle Kontakte gesetzt, zusätzlich zu einer Rolle aus der Tabelle; die Werte Bank und Verwalter sind seit 1.24.0 möglich. Ohne erkennbare Rolle fragt der Assistent nach (Welche Rolle sollen die Kontakte erhalten?). Für einen bereits gelaufenen Import lässt sich die Rolle im Importverlauf über Rolle nachträglich setzen ergänzen. Der Immoware24-Import führt durch Hochladen, Zuordnen der Spalten, Prüfen, Testlauf und Übernahme; die Immoware24-Listen (Objektdaten, Kontakte) werden mit Testlauf und Übernahme direkt angelegt. Vorhandene Daten werden nie überschrieben.
