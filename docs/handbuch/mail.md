# Mail

## Zweck

Der Bereich Mail zeigt die verbundenen Postfächer (nur Lesezugriff auf den Empfang; jede
neue Mail erzeugt ein Ticket). Antworten, Rechnungserfassung und Weiterleitungen laufen
als Entwurf über eine Vier-Augen-Freigabe, bevor tatsächlich versendet wird.

## Reiter

Posteingang, Entwürfe, Freigaben (wartende Vier-Augen-Freigaben) und Gesendet. Filter
nach Status und Postfach stehen oben in der Liste zur Verfügung. Die Liste zeigt je Mail
eine Vorschau statt des Volltexts. Mails, deren Ticket erledigt, abgeschlossen oder abgelehnt
ist, sind standardmäßig ausgeblendet; der Umschalter Erledigte anzeigen blendet sie ein
(seit 1.23.0). Ein gesetzter Statusfilter zeigt immer genau die gewählten Mails.

## Archivierung bei Ticketabschluss

Ist am Postfach die Einstellung Erledigt archiviert Mail aktiv, archiviert die Plattform die
zum Ticket gehörenden Mails im Gmail-Postfach, sobald das Ticket erledigt, abgeschlossen oder
abgelehnt ist. Dazu speichert der Abruf seit 1.23.0 die Gmail-Kennung jeder Nachricht;
fehlende Kennungen der Eingangsmails der letzten 90 Tage werden beim nächsten Abruf
nachgetragen, damit die Archivierung auch für ältere Mails greift. Die Archivierung läuft erst
nach dem gespeicherten Statuswechsel; schlägt sie fehl, bleibt die Mail im Posteingang und der
Abschluss des Tickets bleibt bestehen.

## Telefonassistenz (Hallo Heidi)

Gesprächsprotokolle der KI-Telefonassistenz kommen als Mail ins Postfach und werden als
Anruf erkannt (Absendermuster, Kennwort im Betreff oder Kennwort im Text mit beschrifteter
Rufnummer). Die Erkennung und die Muster sind je Mandant unter Einstellungen, Postfächer,
Telefonassistenz einstellbar. Was aus dem Protokoll wird (Zuordnung von Anrufer, Objekt und
Einheit, Vorschlag Telefonnummer ergänzen mit Antwortentwurf), beschreibt das Kapitel
Tickets, Abschnitt Anrufe über die Telefonassistenz.

## Vorbereitung

Zu jeder eingehenden Mail berechnet die Plattform im Panel Vorbereitung einen Vorschlag:
zugeordneter Kontakt, Rolle (Eigentümer/Mieter), Einheit und Objekt, passende
Objektdokumente aus Paperless und Google Drive (gezielt aus dem Ordner bzw. der
Objektnummer des betroffenen Objekts, keine Auflistung ganzer Aktenbestände) sowie ein
Antwortentwurf. Vorbereiten löst die Berechnung aus, Neu vorbereiten wiederholt sie.
Übernehmen legt aus dem Vorschlag einen Entwurf an, Korrigieren speichert die Korrektur
als gelernten Wissenseintrag (siehe Kapitel Einstellungen, KI und Wissensbasis).

## Rechnung erfassen

Aus einem Mailanhang heraus über Als Rechnung erfassen: Je Anhang einer eingegangenen
Mail startet die Schaltfläche einen Belegentwurf im Belegeingang (Quelle Mail-Anhang).
Die KI liest Aussteller, Nummern, Daten, Beträge, Skonto und Objektbezug als Vorschlag
mit Sicherheit je Feld aus. Nach dem Start erscheint der Link Entwurf im Belegeingang
öffnen, der direkt zur Feldprüfung führt. Übernommen wird der Entwurf erst dort nach der
Prüfung durch eine Person; die IBAN wird maskiert angezeigt und muss aus dem Original
eingetragen und bestätigt werden (siehe Kapitel Belegeingang). Nur PDF, Bild oder
Textanhänge sind möglich. Dieselbe Schaltfläche steht in der Ticket-Ansicht unter Anhänge
aus E-Mails. Ist unter Einstellungen, DMS-Anbindung der automatische Belegeingang aktiv,
entsteht für PDF-Anhänge mit Rechnungsmerkmal beim Postfachabruf selbsttätig ein
Belegentwurf; die Prüfung durch eine Person bleibt unverändert (Kapitel Belegeingang).

## Weiterleitung

Rechnungen der eigenen Gesellschaft (nicht objektbezogen) lassen sich an die
Buchhaltungsadresse weiterleiten, wenn der Absender auf der hinterlegten Positivliste
steht. Jede Weiterleitung braucht eine Freigabe; Korrekturen werden gelernt.

## Vier-Augen-Freigabe

Ein Entwurf (Antwort, Weiterleitung, Systemtext) geht über Zur Freigabe an einen
Freigabeberechtigten. Dieser sieht Absender, Betreff und Text und wählt Freigeben und
senden oder Ablehnen mit Ablehnungsgrund. Nur nach Freigabe wird tatsächlich versendet;
bis dahin bleibt die Nachricht Entwurf bzw. wartet auf Freigabe. Wer den Entwurf erstellt
hat, darf ihn in der Regel nicht selbst freigeben (Vier-Augen-Prinzip).

## Ticketbezug und Kennung TNR#

Jede aus einem Ticket oder aus dem Postfach zu einem Ticket erstellte Antwort trägt im
Betreff die Kennung TNR#<Ticketnummer> (zum Beispiel "AW: Heizung kalt TNR#412"). Antworten
des Empfängers werden über die Thread-Kopfzeilen oder, bei bekanntem Absender, über die
Kennung dem Ticket zugeordnet. Stammt eine Mail mit Kennung von einer nicht am Ticket
beteiligten Adresse, zeigt die Nachricht den Hinweis "Mögliche Zuordnung zu TNR#..." mit
Link zum Ticket; die Zuordnung bleibt eine Entscheidung des Bearbeiters. Kopie-Empfänger
(Cc) werden getrennt gespeichert und in der Antwort vorbelegt. Einzelnachrichten, Threads
und Anhänge sind nur für Benutzer lesbar, die für das jeweilige Postfach freigeschaltet
sind (Standardpostfach, Freigabe unter Einstellungen, Postfächer, oder Administrator).
Aus dem Ticket führt "Im Postfach öffnen" direkt zur Nachricht (/mail?message=...).

## Was ist Vorschlag, was verbindlich

Vorbereitung, KI-Vorschlag (Kategorie, Dringlichkeit, Zusammenfassung, passendes
Playbook) und Rechnungserfassung sind stets Vorschläge. Verbindlich wird ein Text erst
mit Freigeben und senden durch einen Freigabeberechtigten. Fristgebundene oder
haftungsrelevante Erklärungen in einer Mail (Kündigung, Anerkenntnis, Zahlungszusage)
sind vor der Freigabe der Geschäftsführung vorzulegen.

## Häufige Fehler

- **Rechnungserfassung nicht möglich**: Die Mail zeigt den Grund direkt an
  (Rechnungserfassung nicht möglich: {Grund}), zum Beispiel ein nicht lesbarer Anhang.
- **Entwurf lässt sich nicht freigeben**: Der Freigebende ist zugleich Ersteller, oder das
  Recht zur Freigabe fehlt; Zuständigkeit unter Einstellungen, Benutzer und Kompetenzen
  prüfen.
- **Keine neuen Mails im Posteingang**: Das Postfach ist inaktiv oder zeigt Fehler
  (Einstellungen, Postfächer); Abruf erfolgt alle zwei Minuten automatisch, Jetzt abrufen
  löst ihn sofort aus.
