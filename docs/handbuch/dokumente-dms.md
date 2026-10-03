# Dokumente und DMS (Paperless, Belegeingang)

## Zweck

Die Plattform speichert Originale unveränderlich, verknüpft sie mit Objekten, Einheiten,
Verträgen, Kontakten, Tickets und Rechnungen und spiegelt sie in das angebundene
Dokumentenmanagement (Paperless-ngx, Google Drive). Kein Dokument wird aus der Plattform
versendet; Briefe und Serienbriefe entstehen als PDF-Entwurf und werden abgelegt.

## Dokumente in der Plattform

Jedes hochgeladene Dokument (zum Beispiel ein Beleg aus dem Rechnungseingang, ein Anhang
aus dem Mailpostfach, ein Foto aus dem Portal) erhält Titel, Kategorie und einen
Textindex für die Volltextsuche. Die Suche Strg+K findet Dokumente, sofern Leserecht
besteht. Über die Schnittstelle stehen bereit: Volltextsuche, Original herunterladen,
Metadaten ändern, Verknüpfen und Verknüpfung lösen, Spiegelung in das DMS erneut anstoßen
sowie Portalzugriffe lesen (ein Zugriff im Portal ist ein Indiz, keine Zustellung).

Dokumentkategorien und Aufbewahrungsprofile werden je Mandant geführt. Ein
Aufbewahrungsprofil wird zunächst entworfen und muss freigegeben werden. Löschen ist nur
mit freigegebenem Aufbewahrungsprofil möglich; eine Löschungssperre (zum Beispiel bei
Rechtsstreit) verhindert das Löschen, bis sie aufgehoben wird. Löschungen werden im
Löschjournal festgehalten.

Gespiegelte Dokumente (Betreiberentscheidung vom 26.09.2026): Wird ein Dokument rechtmäßig
gelöscht, entfernt die Plattform anschließend die Kopie in Google Drive (endgültig; lehnt
Drive das ab, wandert die Datei in den Papierkorb, das Journal vermerkt, welcher Fall
eingetreten ist). Das Dokument in Paperless bleibt erhalten und erhält das Schlagwort
"gelöscht", damit im DMS sichtbar ist, dass es im CRM gelöscht wurde; fehlt das Schlagwort
in Paperless, wird es angelegt. Beide Schritte werden mit Erfolg oder Fehler im Löschjournal
protokolliert. Die Löschung gilt als "offen", bis beide Schritte gelungen sind; fehlgeschlagene
Schritte wiederholt der Auftrag selbsttätig (nach 1, 5, 30 Minuten, 2, 6 und 24 Stunden).
Über die Schnittstelle (`GET /documents/deletions?status=open`) sind offene Löschungen
einsehbar, `POST /documents/deletions/{id}/retry` stößt die offenen Schritte erneut an.
Eine Oberfläche dafür gibt es noch nicht.

Seit dem 26.09.2026 sind je Mandant Standardprofile als Entwurf hinterlegt (Status
"entwurf", Prüfnotiz "Entwurf, Prüfung Steuerberatung offen"): Buchungsbelege, Journale und
Abrechnungen 10 Jahre; Geschäftsbriefe, Vorgänge und E-Mails 6 Jahre; Verträge 10 Jahre nach
Vertragsende; Portal- und Bewerberdaten 6 Monate nach Zweckende; WEG-Protokolle und
Beschlüsse dauerhaft ohne Löschung. Ein Entwurf gibt keine Löschung frei. Die Freigabe je
Profil und Mandant erfolgt nach Prüfung durch die Steuerberatung über die API
(`POST /api/v1/retention-profiles/{id}/release`, Recht Mandanteneinstellungen ändern, eine
andere Person als die Verfasserin des Entwurfs) und wird protokolliert. Eigene Änderungen an
den Profilen bleiben bei erneutem Seed erhalten. Eine Seite in den Einstellungen gibt es dafür
noch nicht; Status und Werte sind über `GET /api/v1/retention-profiles` einsehbar.

## Paperless

Die Anbindung wird unter Einstellungen, DMS-Anbindung eingerichtet (Kapitel
Einstellungen: Basis-URL, API-Token, Feld-IDs für Objektnummer und Gesellschaft,
Webhook-Geheimnis, Schalter Belegeingang aus Paperless automatisch).

Im CRM erscheinen Paperless-Dokumente an zwei Stellen:

- Objektdetail, Abschnitt Dokumente (Paperless): alle Dokumente mit der Objektnummer des
  Objekts im hinterlegten Paperless-Feld.
- Ticketdetail: Dokumente des Objekts des Tickets und Treffer der Volltextsuche nach der
  Ticketnummer.

Die Tabelle zeigt Titel, Datum, Korrespondent, Dokumenttyp und Tags mit den Aktionen
Vorschau und Download, seitenweise mit Zurück und Weiter. Die Dateien werden über die
Plattform durchgereicht; der Paperless-Token verlässt den Server nicht. Meldungen:
Paperless nicht eingerichtet (keine aktive Anbindung) und Paperless nicht erreichbar.

Paperless meldet neue Dokumente über den Post-Consume-Webhook an die Plattform. Das
Dokument wird dann als Paperless-Dokument indexiert. Ist der Schalter Belegeingang aus
Paperless automatisch aktiv (Standard aus), entsteht zusätzlich ein Belegentwurf in der
Warteschlange des Belegeingangs; ein Entwurf ist keine Rechnung und keine Buchung.

## Belegeingang

Der Belegeingang (Menü Rechnungen, Belegeingang) erzeugt aus PDF-Belegen, Mailanhängen oder
Paperless-Dokumenten KI-Entwürfe für Eingangsrechnungen, die eine Person prüft, ergänzt und
bestätigt oder verwirft. Einzelheiten, Pflichtfelder (IBAN nur aus dem Original) und
häufige Fehler stehen im Kapitel Belegeingang; die weitere Bearbeitung der Rechnung
(Prüfschritte, Freigabe durch eine zweite Person, Buchung) im Kapitel Buchhaltung.

## Vorlagen, Briefe, Serienbriefe

Dokumentvorlagen mit Betreff, Text und Platzhaltern werden je Mandant in Versionen
geführt. Ein Brief lässt sich als Vorschau berechnen (nicht abgelegt) oder erzeugen und
ablegen; er entsteht als PDF nach DIN 5008 auf dem Briefbogen des Mandanten (Absenderzeile
aus den Mandantendaten). Ein Serienbrief erzeugt je Empfänger einen Brief. Der Versand
findet außerhalb der Plattform statt und wird dort, wo es fachlich nötig ist, als
versendet dokumentiert (zum Beispiel Mahnschreiben, Kapitel Buchhaltung).

## DMS und Objektübernahme (Google Drive)

Der Menüpunkt DMS zeigt den Stand der Anbindung an die digitale Objektübernahme
(Kurzname objektakte), die die Objektakten in Google Drive führt: Sechs-Ordner-Struktur je
Objekt (01 Legitimationsunterlagen, 02 Stammakte, 03 Buchhaltung, 04 Mieterakte,
05 Eigentümerakte, 06 Sonstiges), Texterkennung, Klassifikation und Review. Die
Objekttabelle bietet je Objekt den Absprung Akte suchen mit der Objektnummer; eine direkte
Verknüpfung je Akte folgt mit einer späteren Stufe.

Der Menüpunkt Objektakte ist das Prüfcenter der dreistufigen Dokumentklassifikation:

- Klassifikationsregeln mit Mustertyp (Dateiname, Text-Stichwort, Absender oder Domain,
  Drive-Ordner), Zielkategorie, Priorität und Konfidenz; Regeln lassen sich anlegen,
  bearbeiten, aktivieren, deaktivieren und löschen.
- Prüffälle mit Status (Offen, In Bearbeitung, Erledigt, Verworfen), Mindestpriorität und
  Stufe; je Fall Kandidaten übernehmen, KI-Vorschlag abfragen, ablehnen, 7 Tage
  zurückstellen oder die Klasse manuell setzen; Sammelentscheidung für mehrere Fälle.
- Synchronisationsstand des täglichen Differenzimports aus dem objektakte-Export
  (Standard aus; ohne Exportpfad nicht aktivierbar), Bericht des letzten Laufs, Jetzt
  abgleichen, vollständigen Export hochladen. In objektakte gelöschte Datensätze werden im
  CRM nur als Löschmarkierung geführt, nie gelöscht.
- Benutzerabbildung: Vorschlag je objektakte-Benutzer; Einladungen bleiben eine Handlung
  des Administrators.

Im Objektdetail zeigt der Abschnitt Vollständigkeit der Objektakte die vorhandenen
Pflichtunterlagen und erzeugt bei Lücken ein Nachforderungsschreiben als Entwurf (nicht
versendet).

## Häufige Fehler

- Paperless nicht eingerichtet: Unter Einstellungen, DMS-Anbindung fehlt eine aktive
  Paperless-Verbindung oder die Feld-ID der Objektnummer.
- Leere Dokumentliste am Objekt: Die Objektnummer ist in Paperless nicht im hinterlegten
  Feld gepflegt.
- Dokument lässt sich nicht löschen: Aufbewahrungsprofil nicht freigegeben oder
  Löschungssperre gesetzt.
- Löschung bleibt "offen": Die Kopie in Drive oder das Schlagwort in Paperless konnte noch
  nicht gesetzt werden (Anbindung deaktiviert, DMS nicht erreichbar, fehlendes Recht). Den
  Fehlertext des Schritts prüfen, Anbindung beheben, dann erneut anstoßen.

## Datenschutz: Löschantrag und Register (Entwurf)

- Löschantrag erfassen (API `POST /privacy/erasure-requests`): Das System prüft sofort alle Sperren und zeigt sie am Antrag. Freigeben kann nur eine zweite Person, und nur ohne Sperre. Die Ausführung anonymisiert den Kontakt, Buchungen bleiben unberührt. Vorher muss das Löschprofil für Kontakte angelegt und von einer zweiten Person freigegeben sein.
- Register der Auftragsverarbeiter und Verarbeitungstätigkeiten pflegen, daraus den Entwurf des Verarbeitungsverzeichnisses erzeugen (`GET /privacy/processing-records`). Der Entwurf ist vor Verwendung durch einen Rechtsanwalt zu prüfen.
- Die Bedienung im CRM ist noch nicht vorhanden, bis dahin nur über die API.

## Sammelaktion in der Dokumentliste

In der Dokumentliste lassen sich mehrere Dokumente ankreuzen. Über der Liste setzt "Kategorie setzen"
die gewählte Kategorie für alle Markierten (das zugeordnete Aufbewahrungsprofil wird wie bei der
Einzeländerung übernommen), "Mit Objekt verknüpfen" legt die Verknüpfung zum gewählten Objekt an.
Bereits gesetzte Werte werden nicht doppelt angelegt. Die Aktion gilt ganz oder gar nicht und braucht
das Recht Dokumente bearbeiten.

## Ablegen per Ziehen, ZIP-Archive, Briefe und Kategorien (Stand 30.09.2026)

- **Ablegen**: Dateien auf ein beliebiges Fenster des CRM ziehen oder in der Kopfleiste auf
  „Ablegen“ klicken. Im Dialog Objekt und Kategorie wählen. Eine ZIP-Datei wird entpackt, jede
  Datei einzeln geprüft und abgelegt; nicht zulässige Dateien stehen mit Grund in der Meldung.
- **Briefe und Vorlagen** (Dokumente, Link „Briefe und Vorlagen“): Vorlage wählen, Empfänger
  suchen, Betreff und Text eintragen, „Vorschau“ zeigt das PDF. Bei mehreren Empfängern entsteht
  ein Serienbrief. Briefe werden abgelegt, nicht versandt. Vorlagen mit Einstellungsrecht dort
  pflegen; Speichern legt eine neue Version an.
- **Dokumentkategorien** (Einstellungen): Baum der Kategorien, je Kategorie Paperless-Dokumenttyp,
  Paperless-Tag und Drive-Ordner. Neue Kategorien lassen sich unter eine bestehende hängen.
- **Eingangsadresse, geschwärzte Kopien, Drive-Änderungen**: vorerst nur über die API
  (siehe `docs/rules/Q03-documents-w3.md`).

## Briefe und Vorlagen (Version 1.49.0)

Seite `/dokumente/briefe`. Zweck: Brief aus einer Vorlage auf dem Briefbogen des Mandanten erzeugen.
Briefe werden abgelegt und verknüpft, nicht versandt.

* Brief erzeugen: Vorlage wählen, Empfänger über die Suche hinzufügen, Betreff und Text in die
  Felder eintragen, Vorschau als PDF ansehen, dann erzeugen. Bei mehreren Empfängern entsteht ein
  Serienbrief mit einem Dokument je Empfänger; Vertretungen werden nach der Zustellregel berücksichtigt.
* Vorlagen verwalten: Kürzel, Bezeichnung, Betreffvorlage und Textvorlage mit den angezeigten
  Platzhaltern. Jedes Speichern erzeugt eine neue Version. Voraussetzung ist das Recht zum Ändern der
  Mandanteneinstellungen.

## Löschvorschläge (Seite Dokumente, Löschvorschläge)

Voraussetzung: Recht Dokumente lesen, für die Freigabe Dokumente freigeben, für die Ausführung Dokumente löschen. Regel M6-04. Der monatliche Lauf (oder Löschvorschlag jetzt erstellen) schlägt Dokumente mit abgelaufener, freigegebener Aufbewahrungsfrist vor. Der Lauf löscht nichts.

* Freigeben oder Ablehnen (mit optionaler Begründung): nicht durch den Ersteller des Vorschlags.
* Ausführen: nicht durch den Freigeber, nach Bestätigungsfrage. Jedes Dokument wird erneut auf Sperre, Frist und Profil geprüft. Gesperrte oder nicht fällige Dokumente bleiben erhalten und werden mit Grund protokolliert. Drive-Kopien werden gelöscht, Paperless-Dokumente mit dem Schlagwort gelöscht gekennzeichnet.
* Je Lauf zeigt Dokumente anzeigen Titel, Unterlagenklasse, Frist bis, Status und Hash. Die Löschung bleibt bis zur fachlichen Freigabe der Aufbewahrungsprofile gesperrt.

## Geschwärzte Kopien, Eingangsadresse und direkter Upload (R02)

* Geschwärzte Kopie: Im Dokument (Seite Dokumente, Detailansicht des Originals) steht der Abschnitt Geschwärzte Kopien. Datei (bereits geschwärzt), Grund, Umfang und Bearbeitungsschritte (ein Schritt je Zeile) angeben und Kopie anlegen. Die Schwärzung selbst erfolgt außerhalb des Systems, das Original bleibt unverändert. Die Kopie ist zunächst intern. Eine zweite Person mit dem Recht Freigeben wählt die Portal-Sichtbarkeit und gibt frei; der Ersteller sieht den Hinweis auf die Freigabe durch eine zweite Person statt der Schaltfläche. Über Kopie öffnen gelangt man zum Dokument der Kopie.
* Eingangsadresse: Einstellungen, DMS, Eingangsadresse für Weiterleitungen. Sammelpostfach und erlaubte Absender (Adresse oder @domain, eine je Zeile) eintragen; die Adresse hat die Form belege+token@domain. Neues Token erzeugen macht die alte Adresse unwirksam. Ruft ein Mandant das gemeinsame Postfach für mehrere Mandanten ab, schaltet er die Verteilung ein: Nachrichten mit dem Token eines anderen Mandanten desselben Postfachs werden diesem übergeben, sofern der Absender dort erlaubt ist.
* Direkter Upload: Einstellungen, DMS, Schalter Direkter Upload im Browser (Standard aus). Voraussetzungen und CORS stehen im Runbook Objektspeicher, Abschnitt 9.

## Automatische Sperre bei Verfahren und Aufhebung von Sperren (U11)

* Hat die Buchhaltung auf einem offenen Posten eines Vertrags eine Mahnsperre mit Grund Prozess oder Insolvenz gesetzt, sind alle mit diesem Vertrag verknüpften Dokumente automatisch gegen Löschung gesperrt. Die Sperre endet, sobald die Mahnsperre aufgehoben ist.
* Eine Löschungssperre am Dokument oder am Vorgang hebt nur eine zweite Person auf, nicht die Person, die sie gesetzt hat.
* Den aktuellen Stand zeigt die API `GET /documents/{id}/retention-status` (Sperren, WEG-Dauerunterlage, Grund, warum nicht gelöscht wird).

## Aufbewahrung, Sperren und Fristbeginn nach Beschluss (V03)

* Im Dokumentdetail zeigt die Karte "Aufbewahrung und Sperren" das Fristende, jede Sperre mit Grund (manuell, am Vorgang, automatisch bei Rechtsstreit oder Insolvenz, WEG-Dauerunterlage), die Sperrart und den Grund, warum das Dokument nicht gelöscht wird. Bei einer manuellen Sperre erscheint der Hinweis, dass nur eine zweite Person sie aufhebt.
* Eine bestehende Sperre lässt sich nicht überschreiben. Zuerst hebt eine zweite Person sie auf, danach kann eine neue Sperre mit anderer Sperrart gesetzt werden.
* Gilt für das Profil die Startregel "Beschluss", ordnen Sie dem Dokument den Beschluss zu (Feld `retention_resolution_id` über die Dokumentänderung). Das Beschlussdatum bestimmt den Fristbeginn; ohne Beschluss bleibt das Dokument gesperrt.

## Aufbewahrung: Beschluss für den Fristbeginn wählen

Ist ein Dokument mit einem Rechtsträger verknüpft, zeigt die Karte "Aufbewahrung und Sperren" ein Auswahlfeld mit den Beschlüssen aus der Beschluss-Sammlung. Für die Startregel "Beschluss der Eigentümer" ist die Auswahl Voraussetzung, sonst bleibt das Dokument gesperrt. Die Frist berechnet das System; die Auswahl ändert keine Rechtslage und ist zu prüfen.

## Dokumenteingang: Zuordnung, Folgevorschläge und Direktablage (AA13)

- Der Eingangsvorschlag erkennt zusätzlich Einheit (zum Beispiel "Einheit 12"), den am Dokumentdatum
  gültigen Vertrag, die IBAN und die Kundennummer eines Kontakts. Beim Bestätigen werden Einheit und
  Vertrag mit verknüpft.
- Nach dem Bestätigen erscheinen Folgevorschläge je Dokumenttyp (Rechnung, Schadensfoto, Vertrag,
  Protokoll). Sie sind Vorschläge: Mit der Bestätigung werden nur Ticket oder Vertrag verknüpft,
  gebucht oder freigegeben wird nichts.
- Direktablage: Ist der Mandantenschalter eingeschaltet (Standard aus), wird ein eindeutig
  zugeordnetes Dokument nur mit dem Objekt verknüpft und als automatisch abgelegt gemeldet. Die
  Ablage lässt sich mit "Automatische Ablage zurücknehmen" widerrufen.
- Kontaktvorschau beim Import: je Zeile kann eine Rolle gewählt werden; beim Verknüpfen mit einem
  vorhandenen Kontakt können leere Felder ergänzt werden.

Vorlagen und erzeugte Dokumente (Version 1.57.0, 01.10.2026): Eine Vorlage kann auf Kontexte (Kontakt, Vertrag, Einheit, Objekt, Versammlung, Abrechnung, Ticket) beschränkt werden und auf eine Briefbogenvorlage verweisen. Die verwendeten Platzhalter werden beim Speichern ermittelt und an der Vorlage angezeigt. Die Vorlagenliste lässt sich nach Kontext filtern. Zu jedem erzeugten Brief zeigt `GET /generated-documents` die Vorlage mit Version, den Kontext, den Empfänger und den Versandnachweis. Die Bedienung in der CRM-Oberfläche folgt, bis dahin ist die Funktion über die API nutzbar.

Erzeugte Dokumente und Vorlagenkontext in der Oberfläche (AB05, 01.10.2026): Unter Dokumente, "Erzeugte Dokumente" listet die Seite die aus Vorlagen erzeugten Briefe mit Vorlage, Version, Kontext, Zustellung und Link zum Dokument. Filter: Vorlage und Zeitraum (von, bis). In "Briefe und Vorlagen" können die erlaubten Kontexte einer Vorlage angehakt und für die gewählte Version gespeichert werden, die verwendeten Platzhalter werden angezeigt. Am Auftrag (Seite des Auftrags) lässt sich der Verweis auf den Freigabe-Workflow pflegen. Es gibt noch keine Tabelle für Freigabeabläufe, der Verweis ist eine Kennung ohne Wirkung (AA05-01).

Verknüpfungsziele (Version 1.59.0): Ein Vermögensbericht und ein Abrechnungslauf können als Ziel einer Dokumentverknüpfung gewählt werden. Der Versandbrief und das Informationsblatt hängen direkt am Bericht beziehungsweise am Lauf.

## Volltext aus Paperless und Belegerfassung nach Ablage (Welle 17)

Ist für ein Dokument noch kein Text erkannt, zeigt die Detailseite den Hinweis "Texterkennung ausstehend". Sobald Paperless das Dokument verarbeitet hat, übernimmt die Plattform den Volltext beim nächsten Spiegellauf; danach ist das Dokument durchsuchbar und für den Assistenten lesbar.

Wird ein Eingangsvorschlag bestätigt und als Rechnung erkannt, erscheint die Schaltfläche "Beleg erfassen". Sie startet die Rechnungsauslesung als Vorschlag im Belegeingang. Unter Einstellungen, Fachliche Regeln lässt sich mit "Belegerfassung nach Ablage einer Rechnung" festlegen, dass dies bei der Bestätigung automatisch geschieht (Standard aus). Gebucht, freigegeben oder bezahlt wird dabei nichts.

Ein erneuter Import aus der Objektakte stellt ein Dokument, das im Papierkorb liegt, wieder her und protokolliert dies.

## Löschungssperre im Dokumentdetail setzen und aufheben (Welle 19, GAG-26)

* Mit dem Recht Dokumente bearbeiten zeigt die Karte "Aufbewahrung und Sperren" das Feld "Löschungssperre setzen": Art der Sperre (Rechtsstreit, Steuerverfahren, Beweissicherung, Rechtssache, Sonstiges) und Begründung mit 5 bis 500 Zeichen. Die Sperre wird protokolliert und gilt sofort.
* Besteht eine manuelle Sperre, erscheint stattdessen mit dem Recht Freigabe Dokumente das Feld "Löschungssperre aufheben" mit Pflichtbegründung. Hebt die Person auf, die die Sperre gesetzt hat, lehnt das System ab (Vier-Augen-Prinzip); die Meldung erscheint in der Karte.
* Sperren am Vorgang und automatische Sperren bei Rechtsstreit oder Insolvenz werden hier nur angezeigt, nicht aufgehoben.

## Importläufe der Objektakte, OCR-Cache leeren, Vorschaubilder übernehmen (Welle 19, GAG-12)

* Unter Einstellungen, Objektakte zeigt die Karte "Importläufe der objektakte-Übernahme" den Verlauf mit Datum, Status, Zahl der angelegten, geänderten und doppelten Datensätze sowie der Dokumente, die Text aus dem OCR-Cache tragen. Die Liste ist seitenweise (10 je Seite) und braucht das Leserecht Dokumente.
* "OCR-Cache leeren" (Recht Objektakte bearbeiten) entfernt nach einer Bestätigung den aus dem Cache übernommenen Text und setzt den Textstatus auf "ausstehend". Dokumente und Dateien bleiben unverändert; ein erneuter Cache-Upload füllt den Text wieder. Der Vorgang wird protokolliert.
* "Übernahme starten" (Recht Objektakte freigeben) startet die Übernahme der Vorschaubilder im Hintergrund; ein fehlgeschlagener Lauf wird fortgesetzt. Optional werden fehlende Bilder aus dem Original erzeugt (nur Bilddateien). Fortschritt und Zähler stehen darunter und lassen sich mit "Aktualisieren" nachladen.

## Dokumente verknüpfen, Download-Link, Spiegelung (GAI-417, Welle 21)

Auf der Dokumentenliste verknüpft der Abschnitt "Dokumente mit einem Objekt verknüpfen" (Schreibrecht Dokumente) mehrere Dokumente mit Objekt, Einheit, Vertrag oder Ticket. Das Ergebnis nennt je Dokument Erfolg oder Grund des Fehlschlags. Am Dokument erzeugt "Download-Link erzeugen" einen kurz gültigen signierten Link, "Spiegelung erneut anstoßen" wiederholt die Ablage in den angebundenen Systemen.

## Zahlungsdateien (gesperrt bis G2)

Lastschrift- und Zahlungsdateien liegen in der Kategorie "Zahlungsdatei (gesperrt bis G2)". Solange die Freigabe G2 nicht erteilt ist, lassen sie sich weder in der Dokumentenliste herunterladen noch über das Portal abrufen oder in Paperless und Google Drive spiegeln. Titel und Metadaten bleiben sichtbar. Ältere Dateien ordnet die Schaltfläche "Fehlende Standardkategorien ergänzen" der Kategorie zu.
