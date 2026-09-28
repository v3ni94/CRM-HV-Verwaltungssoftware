# Handbuch

Stand: 26.09.2026, Version 1.25.0. Kapitel zu den Versionen 1.20 bis 1.22 ergänzt am
26.09.2026 (Tickets mit Mailverlauf und TNR#, Automatisierung, Portal, WEG, Kommunikation,
Dienstleisterverträge, IBAN-Freigabe, Energieausweis, Belegeingang, Einstellungen); Abschnitte
zu 1.23.0 bis 1.25.0 ergänzt am 26.09.2026 (Erledigte ausblenden, Statusauswahl nach Rolle,
Erledigungsnotiz und Lernen, Telefonassistenz Hallo Heidi, Wissen, Objektbezüge im Kontakt,
Gmail-Archivierung, Listenimport mit Zuordnung, Rolle aus der Chatanweisung). Abschnitt
"Neu in der Welle vom 27.09.2026" unten ergänzt am 27.09.2026 (Postfach-Vertretungen und
Freigabemodus, Sollstellungsregeln, FinTS, Heizkosten, BetrKV-Katalog, Vorschussregel,
Vermögensbericht, Umlaufbeschluss, Mahnwesen, Aufbewahrung, Postausgang, lexoffice,
Magic-Link-Anmeldung, Mandantenübersicht, Objekt deaktivieren, Kautionsabrechnung als PDF).
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
- [Erfassungsstandards und Bericht Datenqualität (Objektname, Namensfelder, Fristen)](erfassungsstandards.md)
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
- [DATEV-Importtest (Testdatei, formale Selbstprüfung, Begleitschreiben)](datev-importtest.md)
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
- [Kataloge und benutzerdefinierte Felder](kataloge.md)
- [Messdienstleister (Verbindungen, Einrichtungsassistent, Zuordnungsübersicht, CSV, Objektreiter, Einheitenzuordnung, Abruf)](messdienstleister.md)
- [Verfahrensdokumentation (GoBD-orientierter Entwurf für den Steuerberater)](verfahrensdokumentation.md)
- [Plattform (Mandanten, Preisstruktur, Freigabe G5, Onboarding Drittmandanten, Export)](plattform.md)

## Handlungsanweisungen

Schritt für Schritt Anleitungen für wiederkehrende Vorgänge (Stand 28.09.2026). Jede Anleitung
nennt Zweck, Voraussetzungen, Menüpfade, zu verknüpfende Datensätze, Ablage, Fristen,
Freigaben, Checkliste und häufige Fehler. Rechtliche Voraussetzungen sind dort, wo keine
freigegebene Regel in `docs/rules/` besteht, als "rechtlich zu prüfen durch Rechtsanwalt"
gekennzeichnet. Schreibweisen und Pflichtfelder: [Erfassungsstandards](erfassungsstandards.md).

- [Verwalterwechsel und Objektübernahme](anleitung-verwalterwechsel.md)
- [Stammdaten anlegen und pflegen](anleitung-stammdaten.md)
- [Eigentümerwechsel](anleitung-eigentuemerwechsel.md)
- [Mieterwechsel und Wohnungsübergabe](anleitung-mieterwechsel.md)
- [Mieterhöhung](anleitung-mieterhoehung.md)
- [Bankverbindung neu anlegen oder ändern (Vier-Augen-Freigabe)](anleitung-bankverbindung.md)
- [Objektordner, Mieterakte und Objektdaten](anleitung-objektordner.md)
- [Aufgabenverteilung Mail und Tickets (Vorschlag zur Entscheidung durch die Geschäftsführung)](aufgabenverteilung-vorschlag.md)

### Lücken in der Software

Stellen, an denen die Anleitungen einen manuellen Schritt oder die Schnittstelle verlangen.
Gesammelt aus den Anleitungen, Stand 28.09.2026:

| Bereich | Lücke | Folge im Ablauf |
| --- | --- | --- |
| Stammdaten | Kein Anlageformular für Gebäude, Einheiten und Umlageschlüsselwerte | Anlage nur per Import oder Schnittstelle |
| Stammdaten | Objekteigentümer (Mietverwaltung), Ansprechpartner, Zähler, Wartungen, Zusatzfelder nicht in der Oberfläche pflegbar | Import oder Schnittstelle |
| Stammdaten | Kein Rückschreiben nach Immoware24 | Doppelpflege im Parallelbetrieb |
| Verwalterwechsel | Kein Fristtyp und keine Checkliste Verwalterwechsel | Ticket mit Fälligkeit und Kalender |
| Verwalterwechsel | Pflichtunterlagen der Vollständigkeitsprüfung nur über die Schnittstelle | Pflege durch Administrator |
| Verwalterwechsel | Nachforderungsschreiben nur als Textentwurf ohne Briefbogen und Versandnachweis | Brief manuell erstellen und ablegen |
| Verwalterwechsel | Kein Export der Objektakte bei Abgabe an einen Nachfolger | manuelle Zusammenstellung |
| Verwalterwechsel | Eröffnungsbestände der Vorverwaltung wegen G1 nicht produktiv übernehmbar | Führung im bisherigen System |
| Eigentümerwechsel | Keine Schaltfläche Eigentümerwechsel | nur `POST /api/v1/contracts/{id}/ownership-transfer` |
| Eigentümerwechsel | Sollbeträge werden nicht auf den neuen Vertrag übertragen | Nacherfassung über WEG, Vorschüsse übernehmen oder Schnittstelle |
| Eigentümerwechsel | Regel W07 fachlich nicht freigegeben, Freigabepunkt P01 offen | keine Aufteilung nach eigener Annahme |
| Mieterwechsel | Übergabeprotokoll ohne Verknüpfung zum Vertrag in der Oberfläche | Protokollnummer im Ticket vermerken |
| Mieterwechsel | Zählerstände aus dem Protokoll nicht in die Zählerstände der Einheit übernommen | zusätzlich unter Zählerstände zur Beendigung erfassen |
| Mieterwechsel | Keine Prüfung der Kündigungsfrist, kein Fristtyp Kautionsabrechnung | Ticket mit Fälligkeit |
| Verträge | Sollbeträge (Miete, Vorauszahlungen) nicht in der Oberfläche erfassbar | Import oder Schnittstelle |
| Mieterhöhung | Versand erfassen bis G3 gesperrt, damit Zustimmung und Übernahme nicht erreichbar | neue Miete im führenden System pflegen |
| Mieterhöhung | Zugangsdatum nur über die Schnittstelle | Frist von Hand im Ticket |
| Mieterhöhung | Kein Fristtyp Mieterhöhung, Musterschreiben ohne Briefbogen-PDF | Ticket mit Fälligkeit, Brief manuell |
| Mieterhöhung | Keine automatische Prüfung für Modernisierung, Index, Staffel | rechtliche Prüfung im Einzelfall |
| Bankverbindung | Keine Oberfläche, um an einem bestehenden Kontakt eine Bankverbindung hinzuzufügen, zu ändern oder zu beenden | Portalvorschlag oder Schnittstelle |
| Bankverbindung | Keine Vier-Augen-Freigabe für Bankkonten der Rechtsträger | organisatorische Freigabe |
| Bankverbindung | `contacts:approve` nur in Administratorrollen | eigene Rolle Freigabe anlegen |
| Objektordner | Keine Standardkategorie für 04_Mieterakte und 05_Eigentümerakte | Ablage über die Objektübernahme oder Ordner von Hand prüfen |
| Objektordner | Elf Unterordner der Mieter- und Eigentümerakte im CRM nicht beschrieben | Bezeichnungen der Objektübernahme verwenden |
| Objektordner | Upload in der Dokumentsuche nur mit Objekt und Einheit, ohne Kategorie, Vertrag oder Kontakt | Verknüpfung über den Vorgang |
| Objektordner | Aufbewahrungsprofile noch Entwürfe | keine Löschung |

## Neu in der Welle vom 27.09.2026

Kurzüberblick je Modul, alle Punkte als Entwurf und teils fachlich noch offen (Einzelheiten
und Freigabestufen im verlinkten Kapitel und in docs/rules):

- **Postfächer** ([Einstellungen](einstellungen.md)): Vertretungsregelung für die
  E-Mail-Freigabe und Mandantenmodus (alle Antworten, nur externe Empfänger oder keine
  Pflichtfreigabe) unter Einstellungen, Postfächer. Die Pflege der einzelnen Vertretung hat
  noch keinen eigenen Bedienweg, siehe Offene Punkte.
- **Buchhaltung, Sollstellung** ([Buchhaltung](buchhaltung.md)): Mandantenvorgaben für die
  Zeitanteilsregel (Kalendertage, 30/360, voller Monat) und die Umsatzsteueroption unter
  Einstellungen, Buchhaltung, Steuern. Buchung bleibt hinter Gate G1 gesperrt.
- **Bank, FinTS** ([Banking](banking.md)): FinTS/HBCI PIN/TAN als zweite, rein lesende
  Bankanbindung neben finAPI; Zugangsdaten verschlüsselt, erneute Freigabe nach 90 Tagen.
- **Betriebskostenabrechnung, Heizkosten** ([Abrechnung Miete](abrechnung-miete.md)): eigene
  Heizkostenvorrechnung mit Verbrauchs- und Grundanteil, Warmwassertrennung und
  CO2-Stufenmodell als Entwurf, hinter Gate G3.
- **Betriebskostenabrechnung, BetrKV-Katalog** ([Abrechnung Miete](abrechnung-miete.md)):
  Systemkatalog der Betriebskostenarten nach § 2 BetrKV mit Kennzeichen umlagefähig,
  Kontenzuordnung und Prüfhinweisen in der Abrechnungsvorschau.
- **Betriebskostenabrechnung, Vorschussregel** ([Abrechnung Miete](abrechnung-miete.md)):
  Vorschlag neuer Vorauszahlungen aus dem Abrechnungsergebnis mit wählbarem
  Sicherheitsaufschlag, Bestätigung durch eine zweite Person und Textbaustein für das
  Anschreiben.
- **WEG, Vermögensbericht** ([WEG](weg.md)): Vermögensbericht der Gemeinschaft zum Stichtag
  (Rücklage, Bankbestände, Forderungen, Verbindlichkeiten, Darlehen) mit Abstimmung gegen die
  Buchhaltung und sichtbarer Differenz; Ausgabe erst nach Gate G4.
- **WEG, Umlaufbeschluss** ([WEG](weg.md)): Umlaufbeschluss mit abgesenkter Mehrheit als
  Schalter je Mandant, Standard aus, fachlich und rechtlich noch nicht freigegeben.
- **Mahnwesen, Konto und Verzug** ([Buchhaltung](buchhaltung.md)): Fälligkeit und Verzug
  getrennt, Verzugsbeginn nur aus erfassten Tatsachen, Verzugszinsen nur als Entwurf.
- **Aufbewahrung** ([Einstellungen](einstellungen.md)): Standard-Aufbewahrungsprofile je
  Mandant, monatlicher Löschvorschlagslauf mit Vier-Augen-Freigabe und Löschprotokoll;
  Löschung bleibt bis zur fachlichen Freigabe gesperrt.
- **Postausgang** ([Kommunikation](kommunikation.md)): anbieterneutrale Post- und
  Briefschnittstelle mit Postausgangsliste und Statusrückmeldung, kein Versand ohne Freigabe
  je Mandant.
- **lexoffice** ([Einstellungen](einstellungen.md)): Anbindung an lexoffice mit
  Einstellungsseite, Testlauf und Protokoll der Export- und Importläufe je Mandant.
- **Portal, Magic-Link-Anmeldung** ([Portal](portal.md)): einmaliger, zeitlich begrenzter
  Anmeldelink für Mieter und Eigentümer, QR-Einladung im Brief, optionaler zweiter Faktor per
  E-Mail-Code; die bestehende Passwortanmeldung bleibt bestehen.
- **Mandantenübersicht** ([Plattform](plattform.md)): rein lesende, mandantenübergreifende
  Sicht für Plattformadministratoren auf Kennzahlen und Listen der eigenen Mandanten, ohne
  Buchungen, Forderungen, Bankbestände oder Belege.
- **Objekt deaktivieren** ([Objekte und Einheiten](objekte-einheiten.md)): Objekte lassen sich
  bei Beendigung des Verwaltungsverhältnisses deaktivieren, bleiben mit allen Daten erhalten
  und verschwinden aus der Objektliste; Reaktivierung nur durch den Superadmin.
- **Kautionsabrechnung als PDF** ([Verträge](vertraege.md)): die Kautionsabrechnung lässt sich
  im Briefbogen des Mandanten als PDF erzeugen und am Vertrag ablegen.

## Anmelden und Mandant wählen

Anmeldung mit E-Mail und Passwort. Das Passwort ist 6 bis 128 Zeichen lang und beginnt oder endet nicht mit einem Leerzeichen (Betreiberentscheidung vom 26.09.2026); nach 10 Fehlversuchen ist das Konto 15 Minuten gesperrt. Der zweite Faktor (Einmalcode aus einer Authenticator-App) ist freiwillig: Wer ihn unter Einstellungen, Meine Daten eingeschaltet hat, gibt nach dem Passwort den sechsstelligen Code ein und kann dabei Dieses Gerät 90 Tage merken wählen; auf diesem Gerät wird dann 90 Tage lang kein Code mehr abgefragt. Gemerkte Geräte lassen sich unter Meine Daten einzeln abmelden. Wer mehreren Mandanten angehört, wählt den Mandanten oben rechts. Alle Daten, Suchen und Benachrichtigungen gelten nur für den gewählten Mandanten.

Die folgenden Abschnitte fassen die Grundfunktionen der Startseite zusammen; Einzelheiten zu
Auswertungen stehen im verlinkten Kapitel.

## Start

Die Startseite ist der persönliche Arbeitsplatz (Betreiberentscheidung vom 27.09.2026) und besteht aus drei Spalten, die auf dem Mobilgerät untereinander stehen:

- Heute: Termine aus dem Kalender und Fristen von heute und der nächsten sieben Tage, getrennt nach Heute und Nächste sieben Tage. Jeder Eintrag führt zur Quelle (Kalender, Fristenliste, Objekt oder Vertrag). Fristen sind Orientierung und zu prüfen.
- Meine Tickets: die mir zugewiesenen offenen Tickets nach Dringlichkeit mit der Ampelfarbe der Ticketliste, höchstens zehn; der Link Alle meine Tickets öffnet die Ticketliste mit diesem Filter.
- Freigaben: alles, was auf meine Freigabe wartet, je Art als Kachel mit Anzahl und Link zur Entscheidung: Mail-Antworten, Bankverbindungen (IBAN im Vier-Augen-Prinzip), Freigabestufen, Mahnläufe, Lastschriftläufe und Übermittlungen an Messdienstleister. Es erscheinen nur Arten, die die eigene Rolle entscheiden darf.

Darüber steht die kompakte Leiste Kennzahlen mit den mandantenweiten Zahlen (Objekte, Einheiten, Kontakte, laufende Verträge, Vertragsenden der nächsten 90 Tage, fällige Wartungen, offene KI-Vorschläge), jede Zahl öffnet ihren Bereich; der Link Auswertung Tickets führt zur Ticketauswertung, dort stehen auch die Ticketstatistik und die Liste der offenen Tickets. Alle Bereiche werden gleichzeitig geladen; fällt ein Bereich aus, zeigt nur dieser einen Hinweis.

## Fristen

Das Menü Fristen listet Termine aus den Stammdaten mit Vorfrist aus den Einstellungen: Vertragsende, Kündigung, Eichfrist Zähler, Ablauf Bankzustimmung, Ende Aufbewahrung, Kündigungsfrist Dienstleistervertrag (14 Tage Vorfrist) und Beschlussfrist virtuelle Versammlung (7 Tage Vorfrist). Die Liste ist Orientierung und in der Oberfläche als zu prüfen gekennzeichnet; sie ersetzt keine rechtliche Fristberechnung. Notfristen sind nie allein aus der Liste zu führen.

## Suche

`Strg+K` (auf macOS `Cmd+K`) oder die Schaltfläche Suchen in der Kopfzeile öffnet die Befehlspalette. Ein Eingabefeld findet Kontakte, Objekte, Gebäude, Einheiten, Verträge, Tickets, Buchungen und Dokumente, dazu Aktionen (Ticket anlegen, Kontakt anlegen, Mahnlauf starten, Zur Auswertung Tickets) und jeden Eintrag der Navigation. Angezeigt wird nur, wofür eine Berechtigung besteht. Ohne Eingabe stehen die zuletzt geöffneten Datensätze bereit (je Benutzer im Browser gemerkt). Pfeiltasten wählen, Eingabe öffnet, Escape schließt. Einzelheiten in [suche.md](suche.md).

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

Fragen zu Kontakten, Objekten, Verträgen und Tickets, Vorschläge je Seite und Änderungen über den Chat beschreibt [KI-Assistent im Chat](assistent-chat.md).

Der Assistent schlägt aus Listen Kontakte, Objekte und Verträge vor; nichts wird ohne Bestätigung übernommen, jeder Import lässt sich rückgängig machen. Eine Rolle aus der Chatanweisung (zum Beispiel "Rolle bank hinterlegen", "als Mieter anlegen") wird beim Tabellenimport auf alle Kontakte gesetzt, zusätzlich zu einer Rolle aus der Tabelle; die Werte Bank und Verwalter sind seit 1.24.0 möglich. Ohne erkennbare Rolle fragt der Assistent nach (Welche Rolle sollen die Kontakte erhalten?). Für einen bereits gelaufenen Import lässt sich die Rolle im Importverlauf über Rolle nachträglich setzen ergänzen. Der Immoware24-Import führt durch Hochladen, Zuordnen der Spalten, Prüfen, Testlauf und Übernahme; die Immoware24-Listen (Objektdaten, Kontakte) werden mit Testlauf und Übernahme direkt angelegt. Vorhandene Daten werden nie überschrieben.
