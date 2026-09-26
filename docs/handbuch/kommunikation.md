# Kommunikation (Telefonie, Zustellungen, ausgehende Webhooks)

Stand 26.09.2026, Version 1.22.1. E-Mail und Postfächer stehen im Kapitel Mail, Tickets im
Kapitel Tickets.

## Telefonie-Anrufliste

### Zweck

Die Telefonanlage meldet Anrufereignisse (begonnen, beendet, verpasst) an die Plattform.
Die Plattform ordnet die Rufnummer einem Kontakt zu, führt je Anruf eine Anrufnotiz und
schlägt bei verpassten Anrufen oder offenen Tickets einen Rückruf vor. Gesprächsinhalte,
Aufzeichnungen oder Transkripte werden nie angenommen oder gespeichert.

### Voraussetzungen

- Einstellungen, Telefonie: Geheimnis (HMAC, mindestens 16 Zeichen) hinterlegt und Webhook
  aktiv (Recht Mandanteneinstellungen ändern). Ohne Geheimnis lässt sich der Webhook nicht
  aktivieren; das Geheimnis wird nach dem Speichern nie wieder angezeigt.
- Der Anbieter oder die Telefonanlage sendet die Ereignisse signiert an den auf der
  Einstellungsseite angezeigten Endpunkt. Die Wahl des Anbieters und die Auftragsverarbeitung
  für die Rufnummernverarbeitung sind Betreiberentscheidung (offener Punkt M23-06); bis dahin
  bleibt der Eingang ohne Wirkung.
- Anrufliste lesen: Recht Kommunikation lesen. Ohne Recht Kontakte lesen erscheinen
  Rufnummern maskiert (zum Beispiel +4921****99). Anrufnotiz bearbeiten und Anruf zuordnen:
  Kommunikation ändern. Rückruf-Ticket anlegen: Tickets anlegen.

### Schritt für Schritt

1. Anrufe erscheinen am Kontakt im Reiter Kommunikation, Abschnitt Anrufe, mit Ereignis
   (Begonnen, Beendet, Verpasst), Richtung (eingehend, ausgehend), Zeitpunkt, Dauer und
   Notiz. Die Liste des ganzen Mandanten steht über die Schnittstelle bereit
   (`GET /api/v1/communication/calls`, Filter Kontakt, Ereignis, Vorschlagsstatus).
2. Zuordnung: Bei genau einer passenden Rufnummer im Kontaktbestand ist der Kontakt
   zugeordnet. Bei mehreren Treffern zeigt die Plattform bis zu zehn Kandidaten; die
   Zuordnung erfolgt von Hand (Anruf einem Kontakt zuordnen). Ohne Treffer bleibt der Anruf
   unbekannt.
3. Anrufnotiz: Freitext je Anruf, jederzeit änderbar.
4. Rückruf-Vorschlag: Bei einem verpassten Anruf oder wenn der zugeordnete Kontakt ein
   offenes Ticket hat, zeigt die Zeile Vorschlag Rückruf. Ticket Rückruf anlegen erzeugt ein
   Ticket mit Quelle Telefon und Kontakt; ein offenes Ticket wird als übergeordnetes Ticket
   verknüpft. Verwerfen schließt den Vorschlag. Ein Ticket entsteht nie automatisch.

### Grenzen

- Nur Rufnummer, Richtung, Zeitpunkt, Dauer und Referenz der Anlage werden gespeichert.
- Rufnummern, die nicht lesbar sind (zum Beispiel anonym), bleiben als Text ohne Zuordnung.
- Ein Anruf ist keine Zustellung und keine Fristauslösung.

## Zustellungen und Kommunikationshistorie

Je Kontakt zeigt die Kommunikationshistorie Mails, Zustellungen, Anrufe und Termine in
zeitlicher Reihenfolge. Zustellungen (Brief, E-Mail, Portal) werden mit Zustellweg
vorbereitet, als Serienversand je Zustellweg zusammengefasst und mit Nachweis (Versand oder
Zugang mit Datum und Beleg) erfasst. Der Nachweis ist eine Eintragung durch eine Person;
die Plattform leitet daraus keine Fristen ab.

## Ausgehende Webhooks (Abonnements des Mandanten)

### Zweck

Fremdsysteme (zum Beispiel Buchhaltung oder Einzugsdienste) erhalten Ereignisse der
Plattform als signierte Meldung, sobald sie eintreten. Die Meldung enthält nur Kennungen,
Feldnamen, Nummern, Daten und Beträge; nie IBAN, Namen, Anschriften, E-Mail-Adressen,
Telefonnummern oder Dokumentinhalte. Details holt das Fremdsystem über die Schnittstelle mit
eigenem Schlüssel und eigenen Rechten.

### Voraussetzungen

Abonnements werden im CRM unter Einstellungen, Webhooks gepflegt (Karte sichtbar mit dem
Recht Mandanteneinstellungen bearbeiten; die Schnittstelle prüft zusätzlich die Rechte
Webhooks lesen, anlegen, ändern und löschen, die Administratoren besitzen) oder über die
Schnittstelle (`/api/v1/tenant/webhooks`). Ziel-URL nur https und öffentlich erreichbar.

### CRM-Seite Einstellungen, Webhooks

- Liste aller Abonnements mit Ziel-URL, Beschreibung, Ereignistypen, Status aktiv oder
  inaktiv und letzter Zustellung (Status, Antwortcode, Zeitpunkt).
- Neues Abonnement: Ziel-URL (nur https, private Netzwerkadressen werden abgewiesen),
  Beschreibung, Ereignistypen aus dem Katalog mit Erläuterung oder alle Ereignisse. Nach dem
  Anlegen zeigt die Seite das Geheimnis genau einmal mit Kopierknopf; nach dem Ausblenden
  ist es nicht mehr abrufbar, bei Verlust ist ein neues Abonnement anzulegen.
- Deaktivieren und Aktivieren je Abonnement; Löschen nach Rückfrage (das Zustellprotokoll
  wird mit gelöscht, die Ereignisse der Plattform bleiben erhalten).
- Protokoll je Abonnement: die letzten 20 Zustellungen mit Status, Antwortcode, Zahl der
  Versuche, nächstem Versuch, Zustellzeitpunkt und Fehlertext; Erneut zustellen für
  fehlgeschlagene oder zugestellte Einträge.
- Eine Testzustellung bietet die Schnittstelle nicht. Beim Anlegen eines weiteren
  Abonnements entsteht das Ereignis `webhook_subscription.created`, an dem sich die
  Zustellung an bestehende Abonnements prüfen lässt.

### Ablauf

1. Abonnement anlegen mit Ziel-URL, Ereignistypen (Liste oder alle) und Beschreibung. Die
   Antwort enthält das Geheimnis genau einmal; es ist beim Empfänger zur Signaturprüfung zu
   hinterlegen.
2. Zustellung erfolgt automatisch jede Minute mit Kopfzeilen für Ereignistyp,
   Zustell-ID und Signatur (HMAC SHA-256 über Zeitstempel und Inhalt). Eine Antwort 2xx gilt
   als zugestellt; sonst Wiederholung nach 1 Minute, 5 Minuten, 30 Minuten, 2 Stunden,
   6 Stunden und 24 Stunden, danach Status fehlgeschlagen.
3. Zustellprotokoll je Abonnement einsehen; Erneut zustellen löst eine manuelle
   Wiederholung aus. Abonnement ändern (aktiv, Ereignistypen).

### Ereigniskatalog (Auswahl)

| Typ | Auslöser |
| --- | --- |
| `contact.created`, `contact.updated`, `contact.deleted` | Kontakt über die Schnittstelle oder das CRM angelegt, geändert (nur Feldnamen), gelöscht |
| `contact.mandate_iban_changed` | IBAN einer Bankverbindung mit SEPA-Mandat geändert |
| `invoice.issued` | Verwalterhonorar als XRechnung ausgestellt (Nummer, Datum, Beträge) |
| `admin_fee_invoice.xrechnung_stored` | XRechnung im DMS abgelegt |
| `tenant_settings.updated` | Mandanteneinstellungen geändert |

Verbindlich ist der Katalog in `docs/integrations/webhooks.md`. Ereignisse zu Rechnungseingang,
Buchungen und Bankumsätzen folgen erst mit den Freigabestufen G1 und G2. Kontaktänderungen
aus Importen erzeugen derzeit kein Ereignis.

### Abgrenzung zu Regel-Webhooks

Die Aktion Webhook senden in der Automatisierung (Kapitel Automatisierung) ruft ein Ziel je
Regellauf genau einmal ohne Wiederholung auf. Für Fremdsysteme, die jede Meldung sicher
erhalten müssen, sind die Abonnements dieses Kapitels vorgesehen.

## Häufige Fehler

- **Telefonanlage erhält 401**: Signatur, Zeitstempel (höchstens fünf Minuten Abweichung),
  Mandant oder Aktivierung stimmen nicht; Einstellungen, Telefonie prüfen.
- **Rufnummern in der Anrufliste maskiert**: Recht Kontakte lesen fehlt.
- **Webhook-Abonnement abgewiesen (Ziel unzulässig)**: Nur https und keine privaten
  Netzwerkadressen.
- **Zustellung steht auf fehlgeschlagen**: Empfänger hat sechs Versuche nicht mit 2xx
  beantwortet; Erneut zustellen nach Behebung beim Empfänger.
