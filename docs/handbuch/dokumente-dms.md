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
