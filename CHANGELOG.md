# Versionsverlauf MH Verwaltungsplattform

Schema MAJOR.MINOR.PATCH: erste Stelle (2.0, 3.0) für grundlegende Umbauten, zweite Stelle
(1.1, 1.2) für neue Funktionen oder Module, dritte Stelle (1.2.1, 1.2.2) für kleine
Korrekturen. Die aktuelle Nummer steht in `VERSION`, die Oberfläche zeigt sie im Footer und
unter `/version` (Quelle `apps/web-crm/src/lib/changelog.ts`). Neue Einträge oben anfügen.

## 1.22.0 (26.09.2026) Master-Prompt-Umsetzung Welle 6: Ticket-Mails mit TNR#, Regel-Engine Stufe 2, Portal (Eigentümer, Beirat, Formulare, Schwarzes Brett, PWA), WEG (Darlehen, Versicherung, Überleitung, Protokoll, Einsicht), Telefonie, Abgleichbericht

- Tickets und Mail: Mailverlauf im Ticket als Thread mit Anhängen (Vorschau Bild und PDF, Download, Als Beleg erfassen), Antwortformular im Ticket (An, Kopie, Betreff, Text, Anhänge) mit Vier-Augen-Freigabe wie bisher; jede Antwort trägt die Ticketnummer im Betreff (TNR#412), eingehende Mails mit TNR# werden dem Ticket nur zugeordnet, wenn der Absender am Ticket beteiligt ist, sonst als Vorschlag angezeigt; Antwort auf ein erledigtes Ticket öffnet es wieder und benachrichtigt den Bearbeiter; Postfachzugriff wird auch bei Einzelmails geprüft (Regel M19-06, Migration 0119)
- Behobene Befunde aus der Prüfung Tickets und Mail (docs/reviews/2026-09-26-review-tickets-mail.md): Gmail-Abruf verlor Mails bei mehr als 50 neuen Nachrichten oder bei Einzelfehlern (jetzt seitenweise mit Nachlauf), Rechnungsweiterleitung ohne Anhänge, SLA-Uhr für Tickets aus Mail und Portal, Ticketliste mit Seitensteuerung, Indizes und eindeutige Mail-Deduplizierung (Migration 0120)
- Automatisierung: Regel-Engine Stufe 2 mit Aktionen Webhook (signiert), E-Mail-Entwurf aus Vorlage, Brief-Entwurf, KI-Aufgabe; Zeitplan als Auslöser (täglich, wöchentlich, monatlich, genau ein Lauf je Termin); strukturiertes Regelformular mit Vorschau statt JSON (Migration 0110)
- Portal: Eigentümerseiten Beschlüsse, Ansprechpartner und Hausgeldkonto (nur gebuchte Werte, ohne Rechtsfolge); Portalrolle Beirat mit Prüfungsraum (Prüfauftrag, Belege, Vermerke, Rückfragen, keine Freigabe, Migration 0109); Schwarzes Brett je Objekt im CRM pflegbar und im Portal sichtbar; Lesebestätigungen am Dokument im CRM als Indiz mit Test D34; Fotos an Schadensmeldungen als Dokumentverknüpfung mit Metadatenbereinigung; Dienstleister-Terminvorschläge mit Bestätigung durch den Bewohner und Fotos der Ausführung (Migration 0111); konfigurierbare Formulare je Mandant mit Einreichung als Ticket (Migration 0115); QR-Code zur Einladung im CRM; Portal als PWA installierbar mit Offline-Startseite
- WEG: Darlehen, Versicherungsfälle und größere Maßnahmen mit Positionen aus gebuchten Buchungen (Migration 0116); Überleitungsrechnung Gesamtgeldfluss im Abrechnungspaket mit erklärten Differenzen, unerklärte Differenz sperrt die interne Freigabe (Regeln W04, W10); Protokollentwurf der Versammlung als PDF im Mandanten-CI; Einsichtsanfragen außerhalb des Portals mit Verlauf und Bereitstellungspaket mit Prüfsummen (Migration 0117); neue Berechtigungsressource hoa
- Vermietung: Energieausweisdaten am Objekt und Angebotsmiete an der Anzeige, Vollständigkeitsprüfung von OpenImmo-Export und Exposé darauf gestützt (Migration 0112)
- Kommunikation und Betrieb: Telefonie-Webhook anbieterneutral mit Signatur, Zuordnung über Rufnummer, Anrufliste am Kontakt und Rückrufvorschlag (Migration 0118); täglicher Abgleichbericht Parallelbetrieb je Objekt aus Immoware24-Rohzeilen mit Differenzliste und CSV; Backup-Prüfjob 02:00 mit Kennzahl; ausgehende Webhooks contact.updated und invoice.issued; Namensmaskierung im Belegeingang auch ohne Anrede
- API: Versionsregel als ADR 0009 mit Deprecation-Headern, Drift-Prüfung meldet Entfernung von Pfaden ohne Deprecation; Handbuchkapitel Objekte, Verträge, Dokumente, Buchhaltung, WEG und Abrechnung
- Technik: Seed-Skript registriert alle Modelle (Abbruch bei membership.contact_id behoben), Migrationskette 0108 bis 0120 linear, Downgrades 0110 und 0112 unter erzwungener RLS lauffähig, eindeutige Schemanamen im OpenAPI-Dokument, Testnutzer je Modul eindeutig
- Aus der parallelen Sitzung: Kontakte: neue oder geänderte Bankverbindungen (IBAN) brauchen die Freigabe einer zweiten Person (contacts:approve), der Ersteller darf nicht selbst freigeben; nicht freigegebene Konten werden in Lastschrift, Zahlung, SEPA-Mandat und Rechnungsabgleich nicht verwendet. Bestandskonten gelten mit Migration 0121 als freigegeben
- Aus der parallelen Sitzung: Verträge: Dienstleisterverträge mit Laufzeit, Kündigungsfrist und automatischer Verlängerung; Kündigungstermin als Orientierung in der Fristenliste mit 14 Tagen Vorfrist (Migration 0122)
- Aus der parallelen Sitzung: WEG: Beschlussfrist virtueller Versammlungen mit Quellenangabe, in der Fristenliste mit 7 Tagen Vorfrist (Migration 0123)
- Aus der parallelen Sitzung: Bankabgleich: Tilgungsbestimmung aus dem Verwendungszweck (Rechnungs- und Sollstellungsnummern, Monate, Quartale) setzt den passenden offenen Posten nach vorn, jede Zuordnung trägt eine Begründung
- Aus der parallelen Sitzung: Mahnwesen: Zahlungserinnerung (Stufe 1) immer ohne Gebühr und Zinsen, Validierung in den Einstellungen und Schutz im Mahnlauf; Standard-Zahlungsfristen 14, 10 und 7 Tage je Stufe mit Hinweis im Formular
- Aus der parallelen Sitzung: KI-Kontierung (propose_posting): Ausgabeschema, Prompt mit Datenminimierung und Sperre, aktiv nur mit Mandantenschalter und freigegebenem Anbieter mit AVV; Ergebnis nur als Vorschlag, nichts wird gebucht (Migration 0124)
- Aus der parallelen Sitzung: WEG: Mehrheitsregeln je Beschlussgegenstand mit Fundstelle und Freigabe durch zweite Person, Prüfung "erreicht / nicht erreicht / nicht prüfbar" am Beschluss ohne Statusänderung (Migration 0125)
- Oberfläche: Die obere Menüleiste des CRM ist jetzt deckend; der fixierte Tabellenkopf (Name, Art, Rolle) der Kontaktliste schien beim Scrollen durch die halbtransparente Leiste hindurch
- Offen (Betreiberentscheidungen in docs/OPEN_QUESTIONS.md): Direktversand einfacher Ticketantworten ohne Vier-Augen-Freigabe (M20-03), Wiederholungsplan für Regel-Webhooks (M9-08), Verteilung von Zins und Tilgung in der Jahresabrechnung (M24-03), Fristen und Umfang der Einsicht (M25-05), Telefonieanbieter (M23-06), QR-Bibliothek für Einladungs-PDF (M21-08)

## 1.21.0 (26.09.2026) Master-Prompt-Umsetzung Welle 5: Abnahmefälle Anhang D, Lastschrift, XRechnung, E-Rechnung, Eigentümerabrechnung, Prüfexport, Regel-Engine, Tagesjobs, Portal und Importassistent

- Abnahme Anhang D: 43 von 58 Fällen technisch bestanden (Protokoll docs/acceptance/PROTOKOLL-2026-09-26.md), darunter Konkurrenz und Wiederholung des Sollstellungslaufs (D48), historische Stichtage (D49), Berechtigungen aller 38 Massenendpunkte (D50), Zahlungsfreigabe und Bankrückmeldung (D35 bis D38), Aufbewahrungssperre und Import-Rücknahme (D43, D46), Prompt-Injection ohne Wirkung (D57), WEG-Fälle (D18 bis D20, D54), Beirat (D32, D33, D53), Portalzugriff über alle Pfade (D29 bis D31), Betriebskosten (D21 bis D23, D28), Restore mit Löschjournal (D47); fachliche Bestätigung bleibt offen (V16)
- Behobene Produktfehler aus den Abnahmen: Idempotenzschlüssel blockierte den Neulauf nach Storno des Sollstellungslaufs; Verwalterhonorar belastete SEV-Eigentümer mit allen Einheiten des Objekts; SEV-Abrechnung enthielt Einheiten fremder Eigentümer; KI-Kontext hatte keinen Dokumentfilter je Portalnutzer; Ablehnungsereignis der Löschsperre ging im Rollback verloren; Vier-Augen-Prinzip prüfte nur die Benutzerkennung; Bankabstimmung meldete fremde Konten nicht als unbekannt
- Buchhaltung: SEPA-Lastschriftdatei pain.008 mit Mandatsprüfung, Sequenztyp und Vorabinformation als Entwurf (Datei hinter G2); XRechnung UBL 2.1 für Verwalterhonorare, mit KoSIT-Validator geprüft; E-Rechnung lesen (XRechnung, ZUGFeRD) im Belegeingang mit Widerspruchsanzeige; Eigentümerabrechnung Miete und SEV als Entwurf (Regel A06); Prüfexport nach Abschnitt 7.7 als ZIP mit Prüfsummen; DATEV-Kontenzuordnung je Mandant mit Sperre bei fehlender Zuordnung; Steuerberaterzugang je Rechtsträger; Rechtsträger der verwaltenden Gesellschaft per Einrichtungsschritt; MT940-Import; Kennzahlen Abdeckungsgrad und Fehlerquote des Bankabgleichs
- Mahnwesen und Abrechnung: Textbausteine je Mahnstufe mit Forderungsaufstellung, Mahnbescheid-Vorbereitung als PDF mit Hinweis auf anwaltliche Prüfung, Anschreiben Guthaben und Nachzahlung je Mieter aus dem Snapshot (Regel A07), KI-Plausibilität des Abrechnungsentwurfs (check_statement, 24 Evaluationsfälle)
- Automatisierung und Jobs: Regel-Engine Stufe 1 (Auslöser, Bedingungen, Aktionen Ticket, Benachrichtigung, Feld setzen, Testlauf, Protokoll), Tagesübersicht 07:00 und Fristenliste 20:00 mit Vorfrist, Dokumenteingang 06:30 mit Zuordnungsvorschlägen, protokollierte Spiegellöschung, Erinnerung vor Ablauf der finAPI-Zustimmung, Paperless-Webhook mit Signaturprüfung, Idempotency-Key für alle schreibenden Endpunkte, Ratenbegrenzung mit X-RateLimit-Headern
- Übergabe und Portal: Versionsverknüpfung beim U-Protokoll-Import, Lesebestätigung als Indiz beim Dokumentabruf (Datenmodell), Schwarzes Brett (Datenmodell)
- Importassistent: Immoware24-Listen (Objektdaten, Kontakte) über die Oberfläche mit Testlauf und Übernahme; Schnellpfad für Eigentümer- und Mieterlisten mit deterministischer Zeilenumsetzung; Evaluationsdatensätze für alle KI-Aufgaben mit mindestens 20 Fällen
- KI-Chat: Freitext-Kontakte aus eingefügtem Text, Verbindungstest je Modellstufe, Ausgabegrenze je Stufe; Tickets: Erkennungskorpus für Stammdatenänderungen (100 Prozent Trefferquote im Korpus), Antwortentwürfe je Änderungsart; objektakte: Synchronisationsstand, Benutzerabbildung, KI-Kostenauswertung, Listenablage als Dokument, Eigentümer- und Mieterlisten; Anzeigen: Bilder je Anzeige für den OpenImmo-Export
- Sicherheit: Review der 1.19.0-Endpunkte (docs/reviews/2026-09-26-sicherheitsreview-1.19.0.md), acht Befunde behoben (Dump-Pfad auf Exportverzeichnis begrenzt, Größenlimits, Postfachprüfung bei Ticketantworten, LIKE-Escaping, CSV-Formelschutz); englische Übersetzungen vollständig mit Prüfskript im Lint
- Technik: Migration 0108 (Fremdschlüssel admin_fee_invoice.tenant_id mit ON DELETE RESTRICT), Modelle und Migrationen ohne Abweichung im Autogenerate-Vergleich, Ratenbegrenzung in der Testkonfiguration abgeschaltet und nur im eigenen Test aktiv, Celery-Testisolation (D50)
- Offen: Regel-Engine Stufe 2, Portal Eigentümer (Beschlüsse, Ansprechpartner, Hausgeldkonto), Portalrolle Beirat, Fotoanhang an Portaltickets, CRM-Anzeige der Lesebestätigungen und Pflege des Schwarzen Bretts; Betreiberentscheidungen in docs/OPEN_QUESTIONS.md (unter anderem M10-05, M12-03, M16-14, M7-08, M15-01, M18-01)

## 1.20.1 (26.09.2026) Pflege: Plan-Dokumente, Formatierung, Typprüfung

- Plan-Dokumente M30-sla, M31 und M32: veraltete Abschnitte "Nicht umgesetzt" auf den tatsächlichen Stand gebracht
- Drei ältere Migrationen formatiert, Typfehler in Testdateien behoben, mypy über das ganze Backend ohne Befund

## 1.20.0 (26.09.2026) Übergabeprotokoll, Portal, Belegeingang, Betrieb

- Übergabeprotokoll: Fotos werden beim Hochladen von EXIF- und GPS-Daten befreit und auf höchstens 2000 px Kantenlänge verkleinert (Einstellung handover_image_max_edge); nicht lesbare Bilder werden abgelehnt
- Übergabeprotokoll: Einladungscode für Gehilfen als E-Mail-Entwurf (Vier-Augen-Freigabe, kein Versand) oder als PDF-Anschreiben auf dem Briefbogen; jede Zustellung erzeugt einen neuen Code, aktivierte Zugänge sind gesperrt
- Übergabeprotokoll: Termin anlegen mit Vorbelegung von Titel, Objektadresse als Ort und Beteiligten mit E-Mail als Teilnehmer, danach Link in den Kalender
- Portal: Mitarbeiter mit Portalzugang sehen Übergabeprotokolle ihrer Objekte (GET /portal/handovers), Rollenwechsel in eine ausgenommene Rolle entzieht den Mitarbeiterzugang sofort, Rückwechsel stellt ihn wieder her
- Belegeingang: Mandantenschalter für den automatischen Eingang (Einstellungen, DMS), standardmäßig aus; bei Aktivierung wird je neuem PDF-Anhang mit Rechnungsmerkmal genau eine KI-Extraktion als Vorschlag gestartet, nichts wird gebucht (Migration 0086)
- Tickets: Integrationstest für die Zusammenführung in ein Zielticket; dabei behoben: Zuweiser und Sammelstatus umgingen die Sperre zusammengeführter Tickets, sehr lange Ziffernfolgen in der Suche führten zu einem Datenbankfehler
- Betrieb: Runbook docs/runbooks/server-recovery-und-haertung.md (Zugang wiederherstellen, Ursache prüfen, SSH nur mit Schlüssel, cloud-init stilllegen, Backup) und Skript scripts/server/harden-ssh.sh

## 1.19.0 (26.09.2026) Tickets: Antwortvorlagen, lernende Stammdatenänderung, Links von der Startseite; Belegeingang; Bankkontenauswahl; Mahnwesen je Objekt mit PDF-Entwurf; OpenImmo-Prüfung; objektakte Stufen 4 und 5; Objekt- und Kontaktimport aus Immoware24-Listen; KI-Chat-Fehlerbehandlung

- Tickets: offene Tickets auf der Startseite mit Link ins Ticket; lange Betreffs und Texte laufen nicht mehr über die Seitenbreite hinaus (Ticket #404); Antwortvorlagen mit Platzhaltern (Anrede, Name, Objekt, Einheit, Ticketnummer) und Standardanhängen unter Einstellungen, im Ticket Vorschau, Bearbeiten und Senden zur Vier-Augen-Freigabe, Anhänge werden beim Versand beigefügt
- Tickets lernen: Mails mit Namens- oder Adressänderung (zum Beispiel Kampmeier zu Müller) erzeugen den Vorschlag Stammdatenänderung mit Akzeptieren, Korrigieren, Ablehnen und einem Antwortentwurf; jede Entscheidung fließt als Beispiel in künftige Vorschläge ein; IBAN wird nie vorgeschlagen (Regel M19-05)
- Belegeingang (M14): KI-Extraktion von Rechnungen aus Upload, Mail-Anhang oder Paperless als Entwurf mit Wert, Sicherheit und Quelle je Feld; Maskierung vor dem Anbieteraufruf; Bestätigung legt nur eine offene, ungebuchte Rechnung an; IBAN nur nach ausdrücklicher Bestätigung
- Bankkonten: Auswahlliste je Objekt und Rechtsträger mit Kontostand und letzten Umsätzen, Zuordnung von Konten zu Objekten, Standardkonto je Zweck (Hausgeld, Miete) und je Rechtsträger; WEG-Konten nie für fremde Objekte
- Mahnwesen: Mahnstufen, Mahngrenze, Gebühr und Zins je Objekt mit Vererbung vom Mandanten, Zahlungsfrist und Brieftext je Stufe; Mahnschreiben als PDF-Entwurf nach DIN 5008 mit Ablage als Dokument; Versand bleibt gesperrt (Gate G1)
- Anzeigen: OpenImmo-Export je Anzeige mit Vollständigkeitsprüfung (Adresse, Preis, Fläche, Energieausweis, Kontakt), Exportsperre mit bewusstem Übersteuern, ZIP mit Bildern
- objektakte Stufe 4: Listengenerierung (Anforderungsliste je Objekt, Dokumentenübersicht je Kategorie, CSV-Export), Berechtigungsschlüssel objektakte je Rolle, Benutzerabbildung als Bericht ohne automatische Anlage, Protokoll der KI-Aufrufe je Dokument
- objektakte Stufe 5: Differenzimport aus dem Dump (nur geänderte Zeilen seit dem letzten Lauf, Löschmarkierungen statt Löschung), täglicher Lauf je Mandant abschaltbar, manueller Lauf über die API
- Datenübernahme aus Immoware24-Listen: Befehl für Objekte und Einheiten aus der Objektliste (Verwaltungsart, Gebäude, Lage, Einheitenart abgeleitet, Eigentümer und Mieter nur als Herkunftsnotiz) und Befehl für Kontakte aus den Listen Eigentümer, Mieter, Bank und Sonstige (Rolle aus der Datei, Personen und Firmen getrennt, Telefon und E-Mail geprüft, keine Dubletten über die Immoware24-Nummer); Testlauf ohne Speichern ist Standard; Handbuchkapitel import-objektdaten und import-kontakte
- KI-Chat: Anbieterfehler werden mit Begründung angezeigt und protokolliert (bisher nur HTTP-Code), abgestürzte Läufe gelten nach dem Fehler als fehlgeschlagen statt endlos zu laufen, Zeitlimit von 10 Minuten im Chat, Chip Nur neue nennt die übersprungenen unvollständigen Zeilen; offene Frage M7-07: EU-Endpunkt wird derzeit nicht an den Anbieter übergeben
- Runbook Update einspielen korrigiert: das Produktions-Compose baut keine Images, die drei Images werden mit docker build unter dem Tag aus VERSION gebaut und der Tag in .env.prod gesetzt; exportierte Shell-Variablen überstimmen .env.prod

## 1.18.0 (25.09.2026) Große Sammelversion: Mitarbeiter und Portalrechte, Kalender, Ticketfilter, Open Banking, Mahnwesen, Rechnungseinstellungen, KI-Schnellimport, Immoware-Diagnose, WhatsApp, objektakte

- Mitarbeiter: beim Einladen entsteht automatisch der Kontakt mit Rolle Verwalter und ein sofort aktiver Portalzugang; Portalrechte je CRM-Rolle unter Einstellungen, Rollen einstellbar mit Nachziehen bestehender Zugänge; Löschen nur noch für Administratoren (Regel M2-07)
- Kalender: Termine aus Tickets, Übergabeprotokollen und der Kalenderseite mit Ort und Teilnehmern aus den Kontakten; Einladungen an Externe nur nach ausdrücklicher Bestätigung; Änderungen auf Google-Seite werden angezeigt und nie still überschrieben; Postfächer einmal neu verbinden
- Tickets: Suche über Nummer, Titel, Beschreibung, Kontakt und Adresse, Filter nach Bearbeiter, Objekt, Einheit, Kontaktrolle (Eigentümer, Mieter), Status, Priorität, Kategorie, Team und Zeitraum, Meine Tickets, Filter in der Adresszeile
- Banking: Open Banking über finAPI als Hauptweg für beliebig viele Banken (Bank per IBAN, BIC oder Name, Login im Bankfenster, Konten importieren und Buchungskreisen zuordnen, Umsätze manuell und rückwirkend abrufen, täglicher Abruf je Mandant abschaltbar), Rechnung-zu-Umsatz-Abgleich, Zahlung nur als Vorschlag (Gate G2), Ticket als Rechnung mit Ablage im Drive-Jahresordner, Beleg hinter der Buchung im Portal; finAPI-Einstellungsseite war bisher am Proxy vorbei nicht erreichbar
- Mahnwesen (V7): Vorschlagswerte für die Mahnleiter, Erinnerung kostenlos, Gebühr ab 1. Mahnung nur mit gepflegtem Betrag, Verzugszins nach gesetzlicher Regel nur mit gepflegtem Basiszinssatz, Gebühr als Sollstellung auf dem Debitorenkonto und Rechnungsentwurf der HVM an WEG bzw. Vermieter, Versandmarkierung, Vorbereitung Mahnbescheid (Prüfung durch Rechtsanwalt)
- Rechnungsstellung und Steuer je Mandant: Nummernkreis KUERZEL-JJJJ-000001 lückenlos, Umsatzsteuerstatus, XRechnung nur mit gepflegten Steuerdaten, DATEV-Buchungsstapel-Kopf nur mit Beraterdaten (Kontenzuordnung zu prüfen)
- KI-Import: Tabellen (CSV, Excel) werden deterministisch verarbeitet, die KI liefert nur die Spaltenzuordnung und bearbeitet Restzeilen; 864 Zeilen in Sekunden statt Minuten
- Immoware24: standardbasierte Erkennung von Adressbuch, Kalender und Dokumentwurzel, Diagnose mit Schritttabelle (zeigt, ob das DAV-Modul freigeschaltet ist), Sammelübernahme der Kontakte, Übernahme von Dokumenten einzeln und je Ordner
- WhatsApp als Eskalationskanal (Meta Cloud API, nur freigegebene Vorlagen, Einwilligung für Kontakte, SMS-Rückfall, Zustellstatus per Webhook, Testnachricht); Meta-Konto und Vorlagen sind vom Betreiber einzurichten
- objektakte-Übernahme Stufen 1 bis 3: Datenmodell, Stammdaten- und Dokumentimport aus dem Datenbank-Dump (Drive-Verweise ohne Kopie, OCR-Text per ZIP, IBAN nie im Klartext), Regelklassifikation, KI-Klassifikation mit Maskierung, Review-Center, Vollständigkeitsprüfung mit Nachforderungsentwurf, Menüpunkt Objektakte
- Übergabeprotokoll: Termin anlegen; Portal: Mitarbeiter sehen alle Protokolle; Portal-Anmeldung ohne zweiten Faktor führte in eine Schleife, behoben
- Sicherheit: Review der neuen Endpunkte (docs/reviews), Mitarbeiterzugang nie auf externem Portalkonto, Größenprüfung beim OCR-ZIP, eindeutige Quellkennungen, strengere Rückleitung
- Handbuch (elf Kapitel) und Runbooks (Update einspielen, Ressourcengrenzen); Playwright-Kernpfade mit neuen Rauchtests
- Dashboard: Tagesbalken der Ticketstatistik ordnen Buchungen nach Ortszeit Europa/Berlin zu (bisher nach UTC, dadurch nach 22 Uhr falscher Tag); Schemaabgleich der Tabellen Mahnwesen, Rechnungseinstellungen und Objektakte-Pflichtdokumente
- Tickets: Kontaktrollenfilter erkennt Eigentümer auch über die Objektzuordnung und prüft je Ticket (bisher leer oder zu weit); Dokumentspiegelung bricht bei fehlender Datei nicht mehr für alle Mandanten ab

## 1.17.5 (25.09.2026) SLA: Kanäle je Eskalationsstufe in der Oberfläche

- SLA-Einstellungen: je Regel Tabelle Stufe 1 bis 3 mit Intern, E-Mail und SMS, vorbelegt mit dem Standard (M35), Speichern über die bestehende Regeländerung; Hinweis, dass SMS nur mit aktivem Gateway und Mobilnummer greift
- Korrektur: Bearbeiten einer Regel im Formular setzt channels_by_level nicht mehr auf Standard zurück

## 1.17.4 (25.09.2026) Google-Verbindung ohne Abmeldung

- Google-Verbindung (DMS und Postfächer): die Rückleitung von Google landet auf einer same-site Zwischenseite, damit die Sitzung erhalten bleibt; bisher erschien nach dem Google-Login die Anmeldeseite des CRM, obwohl die Verbindung gespeichert war

## 1.17.3 (25.09.2026) Datenschutz: Ticket-Vorschau lädt nur den Kontaktnamen

- Neuer Endpunkt GET /contacts/{id}/name liefert nur Anzeigename statt des vollständigen Kontakts; die Vorschau beim Zusammenführen von Tickets nutzt ihn (Datenminimierung)

## 1.17.2 (25.09.2026) Worker: KI-Clients sauber schließen

- Die HTTP-Clients der KI-Anbieter (OpenAI, Anthropic) werden nach jedem Anbieterschritt geschlossen. Bisher meldete der Worker nach jedem KI-Lauf "Event loop is closed", weil die SDKs das Schließen erst beim Aufräumen nach Ende der Ereignisschleife anstießen

## 1.17.1 (25.09.2026) KI-Import: parallele Verarbeitung der Teile

- KI: Teile großer Listen werden parallel verarbeitet (vier gleichzeitige Anfragen an den Anbieter statt nacheinander); ein Import mit 11 Teilen braucht damit statt 5 bis 10 Minuten etwa ein Viertel der Zeit. Fortschrittsanzeige und Aufteilung zu großer Teile bleiben erhalten
## 1.17.0 (25.09.2026) Tickets zusammenführen in der Oberfläche

- Tickets: Aktion Zusammenführen im Ticketdetail mit Suche nach Zielticket (Nummer oder Titel), Vorschau beider Tickets und Bestätigung, danach Weiterleitung zum Zielticket
- Tickets: zusammengeführte Quelltickets zeigen einen Hinweis mit Link zum Zielticket und sind für Bearbeitung, Checkliste und Kommentare gesperrt (auch in der API)
- Tickets: Zielticket zeigt Enthält Ticket mit allen Quelltickets
- Ticketliste: zusammengeführte Tickets standardmäßig ausgeblendet, Filter Zusammengeführte anzeigen
- API: Zusammenführen in ein bestehendes Ticket über target_ticket_id; Verlauf des Ziels vermerkt die Herkunft je Quelle mit Anzahl verschobener Einträge
- API: SLA-Uhren der Quelltickets werden erledigt, Zuweiser der Quellen am Ziel ergänzt, Ticketliste mit Suche q, include_merged und merged_into, Ticketdetail mit message_count

## 1.16.0 (25.09.2026) SLA-Eskalation per E-Mail und SMS

- SLA-Eskalation: Kanäle je Stufe (Standard Stufe 1 intern, Stufe 2 intern und E-Mail, Stufe 3 intern, E-Mail und SMS), je Regel über channels_by_level anpassbar
- SLA-Eskalation: E-Mail wird als Systemmail ohne Freigabeprozess über das Standardpostfach versendet (Gmail oder SMTP), mit Objekt, Priorität, Fälligkeit und Link zum Ticket
- SLA-Eskalation: neuer Kanal SMS über ein anbieterneutrales HTTP-Gateway je Mandant, Einstellungen unter SLA, Reiter SMS-Gateway, mit Testnachricht
- Notfallalarme zeigen Zustellung und Fehlerhinweis (delivered_at, delivery_error); fehlt Postfach oder Gateway, wird der Alarm mit Hinweis protokolliert
- Mitglieder: Mobilnummer je Mitglied pflegbar, genutzt für SMS an die Bereitschaft
- Mailversand nach Vier-Augen-Freigabe nutzt denselben gemeinsamen Transport (communication/transport.py); SMTP-Fehler nennen nur noch die Fehlerart

## 1.15.1 (25.09.2026) KI-Chat: Fehlermeldungen mit Schritt und Status

- KI-Chat: Fehlermeldungen nennen jetzt den Schritt (Unterhaltung anlegen, Nachricht senden, Lauf abfragen) und den HTTP-Status, damit Abbrüche wie Datensatz nicht gefunden zuzuordnen sind

## 1.15.0 (25.09.2026) Belegeingang mit KI, OpenImmo, Übergabeprotokoll mit Gehilfen und U-Protokoll-Übernahme

- Belegeingang (M14): KI-Extraktion von Rechnungen als Vorschlag (Aussteller, Nummern, Daten, Beträge, Skonto, Objektbezug) mit serverseitigen Warnungen bei IBAN-Abweichung und Dublette; Übernahme nur als Entwurf mit Vier-Augen-Prüfung, IBAN wird maskiert angezeigt und muss aus dem Original bestätigt werden; Fremdwährung wird gesperrt
- Belegeingang: Erfassung aus Mail-Anhängen (Schaltfläche Als Rechnung erfassen) und aus Paperless per Dokumentnummer; automatische Erfassung bleibt zurückgestellt (M14-05)
- Anzeigen (M26): OpenImmo-Export je Anzeige und als Sammelexport mit vorheriger Vollständigkeitsprüfung, Adresse nur bei Freigabe, kein Portalupload
- Übergabeprotokoll: Objekt und Einheit auch manuell erfassbar (Adresse, Etage, Einheit, externe Objektnummer, Eigentümername), Umschalter Bestand oder manuell
- Übergabeprotokoll: Gehilfenzugang über den bestehenden Portalzugang (Art Gehilfe, Mieter, Eigentümer, 30 Tage gültig), Einladung als Entwurf im Postausgang, Abschluss mit Rückfrage, PDF und Durchschrift an alle Beteiligten als Zustellentwürfe, Verwaltung der Zugänge im CRM
- Übergabeprotokoll: Datenübernahme aus U-Protokoll (MariaDB-Dump mit Vorschau und Übernahme, Dateien per ZIP mit Prüfsummenabgleich), idempotent je Quelldatensatz
- Planung: objektakte wird vollständig ins CRM überführt (docs/plans/M35-objektakte-uebernahme.md, sechs Stufen, offene Entscheidungen M35-01 bis M35-07)

## 1.14.2 (25.09.2026) Mail-Archivierung bei jedem Ticketabschluss

- Tickets: jeder Abschlussstatus (erledigt, abgeschlossen, abgelehnt) archiviert die zugehörigen Mails im Postfach; bisher nur erledigt und abgeschlossen. Die Postfach-Einstellung zur Archivierung bleibt maßgeblich

## 1.14.1 (25.09.2026) Abschaltplan Immoware Hub

- Runbook `docs/runbooks/hub-abschaltung.md`: vierstufige Abschaltung des Immoware Hub mit Rückweg je Schritt, Voraussetzungen, Aufbewahrungsfristen und Hinweis zur Domain mail.mueller-holding.ag
- Zusatzdatei `infra/compose.hub-redirect.yaml`: dauerhafte Weiterleitung der alten Hub-Hostnamen immoware.muellerhv.de und mail.muellerhv.de auf das CRM über Traefik

## 1.14.0 (25.09.2026) KI-Wissensbasis und Mail-Vorbereitung

- KI-Wissensbasis je Mandant und Objekt unter Einstellungen, KI: Ablageregeln, Arbeitsweisen, Fakten und gelernte Korrekturen, filterbar je Objekt
- Mail-Vorbereitung: eingehende Mail wird dem Kontakt, der Einheit und dem Objekt zugeordnet, passende Objektdokumente (z. B. Teilungserklärung) werden gezielt aus Paperless und Google Drive nur im Ordner bzw. unter der Objektnummer des Objekts gesucht, ein Antwortentwurf wird als Vorschlag erzeugt; nichts wird versendet
- Mail: Panel Vorbereitung in der Mail-Ansicht mit Übernehmen (Entwurf) und Korrigieren; Korrekturen werden als gelernte Wissenseinträge gespeichert
- Regel M20-05: Dokumentsuche der KI ist strikt auf das jeweilige Objekt beschränkt, keine Kontoauflistung
## 1.13.0 (25.09.2026) Lernphase Immoware24

- Neue Lernphase (M33) für den Immoware24-Spiegel: WebDAV-, CardDAV- und CalDAV-Läufe erkunden lesend Ordnerstruktur und Feldnutzung der bereits gespiegelten Daten, Übernahme des Moduls Learning aus dem stillgelegten Immoware Hub
- Jeder Lauf vergleicht sich mit dem letzten erfolgreichen Lauf gleicher Art und liefert lesbare Änderungssätze (neue Ordner, neu oder nicht mehr genutzte Felder, geänderte Anzahl gespiegelter Datensätze)
- Neue Seite Immoware24 – Lernphase mit Artauswahl, Lauflisten und Detailansicht der Fakten; Endpunkte `/api/v1/immoware/learning/runs`, kein Schreibpfad Richtung Immoware24

## 1.12.0 (25.09.2026) Portal für Mieter, Eigentümer und Dienstleister

- Portal portal.mueller-holding.ag: Startseite je Rolle nach der Anmeldung; Mieter und Eigentümer sehen Dokumente mit Download, Meldungen mit Verlauf, Foto und Kommentar, Kontoauszug, Zählerstand und Datenänderung; Dienstleister sehen ihre Aufträge mit Ablehnen, Angebot, Termin, Ausführungsbericht und Rechnungseinreichung
- Portal: alle Angaben mit Geld- oder Vertragsbezug sind Vorschläge und werden von der Verwaltung geprüft, nichts wird automatisch übernommen
- Portal: Menü je Rolle, auf Handy und Tablet nutzbar; vertrauenswürdige Geräte gibt es im Portal bewusst nicht, der zweite Faktor bleibt bei jeder Anmeldung

## 1.11.1 (25.09.2026) Immoware24-Kalender werden automatisch erkannt

- Immoware24-Kalender: der Abgleich ermittelt die Kalender unter der eingetragenen Adresse selbst (PROPFIND auf die Kalender-Heimat des Benutzers) und fragt jeden Kalender einzeln ab; eine Heimatadresse wie .../calendars/users/<Login>/ führt nicht mehr zu REPORT 404
- Immoware24-DAV: abgeleitete Adressen für Kalender und Adressbuch nutzen den hinterlegten Login (.../users/<Login>/), wenn keine eigene Adresse eingetragen ist

## 1.11.0 (25.09.2026) Zwei-Faktor für Administratoren, Google-Kalender, Kontakttypen mit SEPA-Mandat, Banking über finAPI, Bearbeiterzuweisung

- Anmeldung: Zwei-Faktor-Pflicht nur noch für Administratoren, vertrauenswürdige Geräte 180 Tage ohne erneuten zweiten Faktor
- Kalender: Google-Kalender je Postfach, Vorgabe ist das Standardpostfach des Mandanten (info@), zusätzlich das dem Benutzer zugewiesene Postfach; Postfächer müssen dafür einmal neu verbunden werden
- Kontakte: Kontakttypen (Eigentümer, Mieter, Verwalter, Dienstleister, Bank, Sonstiges), SEPA-Freigabe je Bankverbindung mit Mandat als PDF oder Erteilung per Telefon, Brief oder E-Mail mit Datum
- Banking: Kontoanbindung über finAPI (Lesezugriff, WebForm) neben dem Dateiupload, Konten werden Objekten und Buchungskreisen zugeordnet; Zahlungsauslösung bleibt hinter Gate G2 gesperrt
- Tickets: automatische Bearbeiterzuweisung nach Postfach, Anrede oder Signatur, Kompetenzen je Benutzer (Katalog unter Einstellungen, Benutzer) und bisheriger Zuordnung; mehrere Bearbeiter je Ticket
- Tickets: Erledigen archiviert die zugehörige Gmail-Nachricht; Tickets werden am Kontakt, Objekt und an der Einheit angezeigt
- Mail: Weiterleitung von Firmenrechnungen (nicht Objektrechnungen) an die Buchhaltungsadresse mit Lernen aus Korrekturen, jede Weiterleitung nur nach Freigabe
- SLA: Schaltfläche Vorschlagswerte laden legt fehlende Regeln je Priorität und den Geschäftszeitenkalender als Vorschlag an (Produktschutz, keine Rechtsvorschrift)
- Oberfläche: Favicon und App-Symbol im CRM

## 1.10.0 (25.09.2026) Tickets mit Sammelstatus und Vorlagen, Start-Auswertungen, Handy-Oberfläche, KI-Stückelung

- Tickets: Sammelauswahl mit Statuswechsel (Mitarbeiter höchstens 10 gleichzeitig, Administratoren unbegrenzt), Ticketvorlagen mit Checklisten und Pflichtfeldern (z. B. IBAN beim Kautionsticket) unter Einstellungen
- Start: Auswertungen mit Kennzahlen und Grafik (Tickets offen, neu und erledigt je Tag, Woche, Monat, Quartal, Jahr), Filter je Benutzer und Vergleich zweier Benutzer
- Menü: Mail und Tickets unter Übersicht, eigene Gruppe Makler (Anzeigen, FLOW-Import, Übergabeprotokoll), WEG-Objekte und WEG-Verwaltung als ein Eintrag, Importassistent ohne Zusatz
- Handy und Tablet: Menü im Vordergrund, Mail-Ansicht ohne seitlichen Überlauf und lesbar auf dem Handy, Chat mit Fortschrittsanzeige und eigener Farbgebung
- KI: Umlaute aus Windows-kodierten CSV-Dateien korrekt, große Listen werden in Teilen verarbeitet statt gesperrt, automatische Wahl des großen Modells bei Umfang, Fortschritt je Teil, Zeichenstatistik je Datei im Lauf
- Buchhaltung: Auswertungen je Buchungskreis (Liquiditätsvorschau 90 Tage, Zahlungen je Debitor, Erträge je Erlöskonto)
- Makler: Anzeigenformulare in Gruppen (Objekt, Adresse und Freigabe, Preise mit Warmmiete, Energieausweis, Ausstattung, Vermarktung)
- Tests: Integrationstests für DMS-Anzeige und Immoware-Spiegel

## 1.9.2 (25.09.2026) OIDC-Anbieter für die Statusseite zusammengeführt

- Das CRM stellt eine OpenID-Connect-Anmeldung für angebundene Dienste bereit, zuerst genutzt von der Statusseite status.mueller-holding.ag
- Zweig für die Statusseiten-Anmeldung in den Hauptstand übernommen, damit spätere Deploys die Funktion behalten (Runbook docs/runbooks/oidc-relying-parties.md)

## 1.9.1 (25.09.2026) Google Drive per OAuth verbinden

- Auf der DMS-Seite verbindet ein Klick auf Mit Google verbinden das Drive-Konto, Client-Secret und Refresh-Token werden automatisch hinterlegt
- Manuelle Eingabe bleibt als Alternative erhalten

## 1.9.0 (25.09.2026) Immoware24-Lesezugriff per DAV

- Neues Paket `mhvp.immoware`: Spiegel von Immoware24 per WebDAV, CardDAV und CalDAV, strikt lesend (kein Schreibpfad, es gibt keine Immoware24-REST-API)
- Anbindung je Tenant mit Verbindungstest (PROPFIND Depth 0), manueller und automatischer Abholung (Celery-Beat alle 15 Minuten, `poll_minutes` je Tenant)
- Dokumentbaum (Ordner und Dateien mit geratener Objektnummer), Adressbuch (Kontakte mit Zuordnung zu oder Anlage als CRM-Kontakt) und Kalender (Termine) als durchsuchbare Spiegeltabellen
- Backend-Endpunkte `/api/v1/immoware/...`; Frontend-Einstellungsseite und Übersichtsseite folgen in einem weiteren Schritt

## 1.8.0 (25.09.2026) Gehilfenzugang für Übergabeprotokolle über das Portal

- Makler, Übergabeprotokolle: Portalzugang je Beteiligtem mit CRM-Kontakt einrichten und beenden; Portalkonto wird bei Bedarf angelegt, Einladungscode einmalig angezeigt
- Portal (apps/web-portal): Anmeldung mit Passwort und zweitem Faktor, Liste der eigenen Übergabeprotokolle, Ausfüllen der Abschnitte, Fotos, Unterschrift, Abschluss; interne Vermerke der Verwaltung bleiben verborgen
- Nach dem Abschluss durch den Beteiligten bleibt das PDF im Portal 14 Tage lesbar, danach erlischt der Zugang; Zustellung weiterhin nur über den Postausgang
- Portal-API `/api/v1/portal/handover`, Regel M30-01 ergänzt, offene Fragen M30-01 (Einladungscode) und M30-05 (zweiter Faktor für Gehilfen)

## 1.7.0 (25.09.2026) Übergabeprotokolle im Bereich Makler

- Neuer Unterpunkt Makler, Übergabeprotokolle: Anlage mit Vorbelegung aus Objekt und Einheit, Beteiligte aus den Kontakten, Zähler, Räume, Mängel, Schlüssel, Gegenstände, Bemerkungen, Fotos und Anhänge als Dokumente
- Unterschriften per Canvas mit Prüfsumme, Hinweise vor dem Abschluss, Abschluss mit PDF auf dem Briefbogen, Festschreibung, neue Versionen ohne Dateiduplikate, Stornierung, Archivierung
- Zustellung an die Beteiligten als E-Mail-Entwurf im Postausgang (Vier-Augen-Freigabe), kein automatischer Versand
- Protokollnummern UP-JJJJMMTT-NNN aus der Nummernfolge je Mandant und Tag
- Migration 0043 (Tabellen handover_*), Regel M30-01, Plan docs/plans/M30-uebergabeprotokoll.md, offene Fragen M30-01 bis M30-04 (Gehilfenzugang über das Portal folgt als Stufe 3)

## 1.6.1 (25.09.2026) Google Drive auf der DMS-Seite einrichtbar

- Google-Drive-Anbindung wird auf der Seite DMS-Anbindung eingerichtet: Wurzelordner, OAuth-Client, Zugangsdaten

## 1.6.0 (25.09.2026) Einstellungsseite DMS-Anbindung

- Neue Einstellungsseite DMS-Anbindung: Paperless-Basis-URL, API-Token und die Feld-IDs Objektnummer und Gesellschaft im Browser pflegbar
- Google Drive wird auf derselben Seite nur lesend angezeigt (aktiv, Basis-URL, Token hinterlegt)
- Karte DMS-Anbindung in den Einstellungen, sichtbar mit dem Recht tenant_settings:update

## 1.5.1 (25.09.2026) Korrektur Migration SLA

- Migration 0042 verwendet den vorhandenen Typ ticket_priority statt ihn erneut anzulegen (Enum sla_alert_channel ebenfalls nur einmal), der Deploy brach bisher mit DuplicateObject ab

## 1.5.0 (25.09.2026) Paperless-Dokumente in Ticket und Objekt

- Abschnitt Dokumente (Paperless) in der Ticketansicht und in der Objektansicht mit Vorschau und Download
- Suche in Paperless über die Objektnummer (Custom Field) und die Ticketnummer im Volltext, Treffer werden zusammengeführt
- Dateien werden über das CRM durchgereicht, der Paperless-Zugang bleibt serverseitig
- Feld-IDs für Objektnummer und Gesellschaft je Mandant in der DMS-Anbindung einstellbar (Optionen object_field_id, company_field_id)
- Versionsnummer im Footer mit Verlauf unter /version
- Plan docs/plans/M31-paperless-view.md, keine Migration

## 1.4.0 (25.09.2026) SLA, Notfallkette und Bereitschaft

- SLA-Regeln je Ticketpriorität mit Reaktions- und Lösungszeit, Uhren laufen nur in der Geschäftszeit
- Arbeitskalender mit Feiertagen, Uhren lassen sich pausieren und fortsetzen
- Eskalationsstufen mit Benachrichtigung an Zuständige und Bereitschaft
- Bereitschaftsplan mit aktueller Bereitschaft und Alarmen zum Quittieren
- Einstellungsseite SLA und Bereitschaft, SLA-Ampel im Ticket
- Erste Antwort per freigegebener Mail stoppt die Reaktionsuhr
- Migration 0042, Plan docs/plans/M30-sla.md

## 1.3.0 (25.09.2026) KI-Vorschläge und Playbooks für Mails

- KI-Antwortvorschlag je eingehender Mail im Ticket
- Playbooks werden aus abgeschlossenen Tickets gelernt und beim nächsten gleichartigen Vorgang angeboten
- Tickets zusammenführen zu einem neuen Ticket mit neuer Nummer, Verlauf bleibt erhalten
- Migrationen 0037 und 0041

## 1.2.1 (24.09.2026) Rückwirkend: Stand vom 24.09.2026 vor Einführung des Versionsverlaufs

- Mietrecht: Regelwerk und Kappungsgebiete NRW, Mieterhöhungsprüfung mit Begründungsmitteln
- Betrieb: Produktivstack auf dem Betreiberserver mit Traefik, Let's Encrypt, Backup-Timer, Wiederherstellungstest, Health-Check, Mehrkern-Einstellungen für API, Celery und PostgreSQL
- Oberfläche: CI der Müller Holding AG, dunkle Seitenleiste mit Icons, Seitenköpfe, Kennzahlen-Kacheln, Anmeldeseite, Dunkelmodus, Bedienung auf Handy und Tablet
- KI: OpenAI als zweiter Anbieter, Anbieterreihenfolge mit automatischem Wechsel, Wiederholung bei Ratenlimit, Chatblase auf jeder Seite mit geführten Importen, Assistent als Protokollseite aller Chats
- Verwaltung: Filter Mietverwaltung, WEG und SEV, Objektebereich, Benutzerverwaltung mit Rollen, Passwort zurücksetzen und Sperren, Benutzermenü, Einstellungen, Mandanten anlegen
- Makler: Anzeigen für Vermietung und Verkauf je Einheit, Felder aus dem FLOW-Datenvertrag, Import des FLOW-Datenbankexports mit Vorschau und Übernahme
- DMS: Bereich mit Absprung in die Objektübernahme je Objektnummer
- Postfach: Gmail-Abruf mit Ticket je Mail, Fehler je Nachricht isoliert

## 1.2.0 (24.09.2026) Postfach im CRM

- Gmail-Abruf je Postfach, jede Mail wird einem Ticket zugeordnet oder eröffnet ein neues
- Google-OAuth-Einstellungen, Standardpostfach und Zugriff je Benutzer
- Mail-Reiter im Ticket mit Vier-Augen-Freigabe vor dem Versand über Gmail
- Fehlerhafte Einzelmails brechen den Abruf nicht mehr ab und werden gemeldet
- Migrationen 0035, 0036, 0039, 0040

## 1.1.0 (24.09.2026) Makler, DMS-Bereich und neue Oberfläche

- Maklerbereich mit Miet- und Kaufangeboten, Felder nach FLOW-Datenvertrag, FLOW-Import
- DMS-Bereich mit Anbindung der Objektübernahme (objektakte)
- Überarbeitetes Design mit dunkler Navigationsleiste, Seitenköpfen und Dashboard-Kacheln, mobile Ansicht
- Einstellungsbereich mit Benutzerverwaltung, Rollen, Mandant, Profil
- KI-Assistent auf jeder Seite mit Seitenkontext, Auswertung aller Chats für Revisionsleser
- Mehrkern-Auslegung für API, Celery und PostgreSQL im Produktivbetrieb

## 1.0.0 (23.09.2026) Marktreife der Grundplattform

- Mandantenfähige Plattform mit Rollen, Rechten und Revisionsprotokoll (M1, M2)
- Kontakte, Objekte, Einheiten, Verträge (M3 bis M5)
- Dokumente mit Aufbewahrung, DMS-Spiegel (Paperless, Google Drive), Briefe und Serienbriefe (M6)
- KI-Gateway, Onboarding-Chat, Immoware24-Import, Oberfläche und Betrieb (M7 bis M9)
- Buchungskreis, Bankanbindung, Matching mit KI-Kontierung, Sollstellung, Verwalterhonorar (M10 bis M13)
- Belegeingang, Kreditoren, Zahlläufe, Mahnwesen, Mietabrechnung, Auswertungen und Exporte (M14 bis M18)
- Tickets und Aufträge, Postfach, Portale für Mieter, Eigentümer und Dienstleister, Kommunikation (M19 bis M23)
- WEG-Wirtschaftsplan und Abrechnung, Versammlung, Beiratsprüfung, Mieterhöhung und Vermietung, Marktreife (M24 bis M27)
