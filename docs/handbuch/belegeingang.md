# Belegeingang

## Zweck

Der Rechnungseingang (Menü Rechnungen) erfasst Eingangsrechnungen, prüft sie in
getrennten Schritten und bucht sie erst nach Freigabe. Rechnungsfreigabe, Buchung und
Zahlungsfreigabe sind bewusst getrennte Vorgänge; automatische Prüfungen liefern nur
Hinweise, keine Entscheidung.

## Erfassung

Eine Rechnung entsteht auf drei Wegen:

- Rechnung erfassen: manuelle Eingabe von Buchungskreis, Aussteller, Rechnungsnummer,
  Datum, Netto, Steuersatz, Kostenkonto, Auftrags- oder Vertragsbezug.
- Aus Dokument erfassen: PDF hochladen, die KI liest Aussteller, Nummern, Daten, Beträge
  und Objekthinweis als Vorschlag aus (Feld Vorschlag prüfen und ergänzen).
- Aus der Mail-Ansicht über Als Rechnung erfassen (siehe Kapitel Mail) oder aus Paperless
  per Dokumentnummer.

Eine automatische Erfassung ohne diesen Prüfschritt gibt es nicht.

## Belegeingang (KI-Entwürfe)

Der Belegeingang (Menü Rechnungen, Schaltfläche Belegeingang) sammelt alle Belege, die
die KI als Entwurf vorgeschlagen hat. Ein Entwurf ist keine Rechnung und keine Buchung.
Erst Rechnung als Entwurf anlegen legt nach der Feldprüfung einen offenen, ungebuchten
Rechnungsentwurf im Rechnungseingang an. Die Schaltfläche Belegeingang zeigt die Anzahl
der offenen Entwürfe.

Ein Belegentwurf entsteht auf vier Wegen:

- Beleg hochladen (PDF) direkt im Belegeingang.
- Aus Paperless holen per Dokumentnummer.
- Aus der Mail-Ansicht: unter einer eingegangenen Mail steht je Anhang die Schaltfläche
  Als Rechnung erfassen. Nach dem Start erscheint der Link Entwurf im Belegeingang öffnen,
  der direkt zur Feldprüfung führt. Der Entwurf bleibt mit der Mail verknüpft (Quelle
  Mail-Anhang).
- Aus der Ticket-Ansicht: der Abschnitt Anhänge aus E-Mails listet die Anhänge aller
  eingegangenen Mails des Tickets. PDF- und Bildanhänge erhalten dieselbe Schaltfläche
  Als Rechnung erfassen; andere Dateitypen sind als kein Beleg (Dateityp) gekennzeichnet.

Für ein Dokument kann nur ein offener Entwurf bestehen. Ein zweiter Start meldet den
vorhandenen Entwurf (Rechnungserfassung nicht möglich: Für dieses Dokument liegt bereits
ein offener Belegentwurf vor).

### Entwurfsliste

Die Liste zeigt je Entwurf Erfasst am, Aussteller, Betrag (Brutto), Datum
(Rechnungsdatum), Objektvorschlag, Sicherheit, Quelle (Upload, Mail-Anhang, Paperless)
und Status. Die Sicherheit ist die niedrigste Feldsicherheit des Entwurfs; ein niedriger
Wert bedeutet, dass mindestens ein Feld am Original zu prüfen ist. Die Liste ist nach
Eingang sortiert, der neueste Entwurf steht oben. Der Filter Offene zeigt Entwürfe, die
noch ausgewertet werden, zur Prüfung stehen oder fehlgeschlagen sind; Alle zeigt auch
übernommene und verworfene Entwürfe.

### Feldprüfung

Je Feld stehen Vorschlag, Sicherheit, Quelle (KI, Plattform, kein Wert), Hinweis und der
geprüfte Wert nebeneinander. Der geprüfte Wert ist das, was übernommen wird; er kann
frei geändert werden. Buchungskreis, Sachkonto und Aussteller (Kontakt) sind Pflicht.
Entwurf verwerfen schließt den Entwurf mit optionalem Grund; eine Rechnung entsteht dann
nicht.

Die IBAN wird im Belegeingang nur maskiert angezeigt und nie aus dem Vorschlag
übernommen. Wer eine IBAN übernehmen will, trägt sie aus dem Original ein und bestätigt
das Häkchen Ich habe die IBAN mit dem Originalbeleg verglichen und bestätige sie. Ohne
Häkchen bleibt Rechnung als Entwurf anlegen gesperrt; eine IBAN ohne Bestätigung lehnt
die Schnittstelle ab.

## Belegeingang aus Paperless automatisch

Paperless kann neue Dokumente nach dem Verarbeiten (Post-Consume) an das CRM melden.
Der Endpunkt `POST /api/v1/documents/webhooks/paperless` braucht keine Anmeldung, aber
je Meldung eine HMAC-Signatur mit dem Webhook-Geheimnis des Mandanten (Einstellungen,
DMS-Anbindung, Post-Consume-Webhook). Jede gültige Meldung legt das Paperless-Dokument
einmal als Dokument im CRM an (Kennung: Paperless-Dokumentnummer); Wiederholungen legen
nichts doppelt an, eine erneut gesendete identische Meldung wird als Wiederholung
abgewiesen.

Ein Belegentwurf entsteht daraus nur, wenn der Schalter Belegeingang aus Paperless
automatisch aktiv ist (Standard aus). Dann wird je gemeldetem Dokument ein Entwurf in die
Warteschlange gestellt, genauso wie bei Aus Paperless holen. Der Entwurf ist ein Vorschlag
zur Prüfung, keine Rechnung und keine Buchung; die Feldprüfung, die IBAN-Bestätigung und
die Freigabe bleiben unverändert. Eine XRechnung wird ohne KI-Aufruf gelesen, für PDF und
Bilder läuft die KI-Extraktion im Kostenrahmen des Mandanten.

Einrichtung in Paperless (Post-Consume-Skript): Zeitstempel (Unix-Sekunden) in der
Kopfzeile X-MHVP-Timestamp, Mandant (Kurzname oder ID) in X-MHVP-Tenant oder als
Pfadsegment, Signatur `sha256=<hex>` in X-MHVP-Signature über die Zeichenkette
`<Zeitstempel>.` gefolgt vom Rohinhalt der Meldung, Inhalt als JSON mit `document_id`
(Paperless-Nummer) und optional `title`. Meldungen älter als fünf Minuten werden
abgewiesen.

## KI-Erfassung und Prüfung

Jeder KI-Vorschlag zeigt die Sicherheit der Erkennung in Prozent, erkannte
Ausstellerkandidaten sowie Hinweise, zum Beispiel bei möglicher Dublette. Fremdwährung
wird erkannt und die Anlage gesperrt, bis der Betrag in EUR geprüft ist.

## IBAN-Bestätigung

Die von der KI erkannte IBAN wird nur maskiert angezeigt und nie automatisch übernommen.
Die vollständige IBAN ist von Hand aus dem Originalbeleg einzutragen (Pflichtfeld IBAN
aus dem Original eintragen). Weicht die eingetragene IBAN von einer bereits bekannten
IBAN des Ausstellers ab, verlangt Abweichende IBAN bestätigen eine ausdrückliche
Bestätigung, dass der Rückruf beim Aussteller erfolgt ist. Ohne diese Bestätigung bleibt
die Rechnung nicht buchbar.

## Prüfschritte

Drei Prüfschritte je Rechnung: Vollständigkeit, sachliche Prüfung, rechnerische und
steuerliche Prüfung. Jeder Schritt erhält ein Ergebnis (ohne Beanstandung, mit Vorbehalt,
Rückfrage, beanstandet) mit Begründung. Der Reifegrad der Rechnung (Prüfstatus) fasst
alle Schritte zusammen, bis mit Vorbehalt oder ohne Beanstandung abgeschlossen wird.

## Freigabe und Buchung

Rechnung freigeben verlangt eine zweite Person, die die geprüfte Version bestätigt.
Buchen legt die Buchung endgültig fest (Buchen? Korrektur nur per Storno); nach dem
Buchen ist eine Änderung nur noch über eine Stornierung und gegebenenfalls eine neue
Buchung möglich, nie durch Überschreiben. Produktive Buchführung bleibt bis zur
Freigabestufe G1 gesperrt (siehe CLAUDE.md, Freigabestufen).

## Was ist Vorschlag, was verbindlich

KI-Erfassung, Objekthinweis, Ausstellerkandidaten und alle Hinweise der Prüfschritte
sind Vorschläge. Verbindlich wird eine Rechnung erst mit der Freigabe durch die zweite
Person und der anschließenden Buchung.

## Häufige Fehler

- **Rechnung lässt sich nicht anlegen (Fremdwährung erkannt)**: Betrag zunächst in EUR
  klären, dann erneut erfassen.
- **IBAN-Bestätigung wird verlangt**: Die eingetragene IBAN weicht vom bekannten Stand
  ab; ohne Rückruf beim Aussteller und Bestätigung ist keine Buchung möglich.
- **Als Rechnung erfassen im Ticket fehlt**: Nur PDF- und Bildanhänge (PNG, JPEG) aus
  eingegangenen Mails erhalten die Schaltfläche; andere Dateitypen und Anhänge eigener
  Antworten nicht.
- **Rechnung als Entwurf anlegen bleibt gesperrt**: Sachkonto, Aussteller (Kontakt) oder
  ein Pflichtfeld fehlt, oder eine IBAN wurde eingetragen, aber nicht bestätigt.
- **Buchen ist nicht auswählbar**: Freigabe durch eine zweite Person fehlt noch, oder die
  Rechnung ist bereits gebucht beziehungsweise storniert.
