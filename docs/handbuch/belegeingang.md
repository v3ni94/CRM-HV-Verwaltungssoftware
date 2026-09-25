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
- **Buchen ist nicht auswählbar**: Freigabe durch eine zweite Person fehlt noch, oder die
  Rechnung ist bereits gebucht beziehungsweise storniert.
