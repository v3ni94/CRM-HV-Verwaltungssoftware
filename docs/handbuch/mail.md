# Mail

## Zweck

Der Bereich Mail zeigt die verbundenen Postfächer (nur Lesezugriff auf den Empfang; jede
neue Mail erzeugt ein Ticket). Antworten, Rechnungserfassung und Weiterleitungen laufen
als Entwurf über eine Vier-Augen-Freigabe, bevor tatsächlich versendet wird.

## Reiter

Posteingang, Entwürfe, Freigaben (wartende Vier-Augen-Freigaben) und Gesendet. Filter
nach Status und Postfach stehen oben in der Liste zur Verfügung.

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
aus E-Mails. Eine automatische Erfassung ohne diesen Schritt ist zurückgestellt.

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
