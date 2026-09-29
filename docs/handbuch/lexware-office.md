# Lexware Office

Anbindung an Lexware Office (früher lexoffice) je Gesellschaft. Einstieg: Einstellungen,
Schnittstellen, Lexware Office. Lesen mit `tenant_settings:read`, ändern mit
`tenant_settings:update`, Kontakte zuordnen mit `contacts:update`, Rechnungsentwürfe und
Dauerrechnungen mit `accounting:create`, Rechnungskopien am Ticket mit `tickets:update`
(Abruf zusätzlich `communication:update`).

## Einrichtung

1. Reiter Organisationen: je Gesellschaft eine Organisation anlegen (Hausverwaltung Müller
   GmbH, Müller Holding AG, Einzelunternehmen Timo Müller) oder die Standardorganisation ohne
   Gesellschaft. Bezeichnung, API Schlüssel (wird nach dem Speichern nur noch als "endet auf"
   angezeigt), Postfach für Rechnungskopien.
2. Auftragsverarbeitung: Datum des AVV mit Haufe Lexware und Vermerk erfassen. Ohne Datum
   lässt sich die Anbindung nicht aktivieren.
3. Verbindung testen. Der Test liest das Profil der Organisation und merkt sich deren
   Kennung. Ein späterer Schlüssel einer anderen Organisation wird abgelehnt, solange
   Verknüpfungen bestehen.
4. Schalter setzen: Anbindung aktiv, Kontaktänderungen übertragen, Namensänderungen
   übertragen, Rechnungskopien abrufen, Rechnungsentwürfe anlegen. Die beiden letzten
   Schalter stehen nur Organisationen mit Rechnungsfunktion offen.
5. Reiter Rechnungsarten: Maklerrechnungen, Beratung und Hausverwaltung je einer Gesellschaft
   zuordnen. Die Hausverwaltung ist mit der verwaltenden Gesellschaft vorbelegt, die anderen
   Arten werden vom Betreiber gesetzt.

Bis zur Freigabe von ADR 0013 durch die Geschäftsführung bleiben die Funktionsschalter aus
(docs/OPEN_QUESTIONS.md LEXO-06).

## Kontakte zuordnen

Reiter Kontakte zuordnen: "Abgleich starten" liest die Kunden und Lieferanten (oder alle
Kontakte) aus Lexware Office und schlägt Zuordnungen vor. Gründe: Kundennummer, E-Mail
identisch, Name und PLZ, nur Name. Jede Zeile wird von einer Person entschieden:

- Verknüpfen: der CRM Kontakt gehört zum Lexware Kontakt; der Stand wird gelesen, nichts wird
  geschrieben.
- In Lexware Office anlegen: nur für CRM Kontakte ohne Gegenstück, mit gewählter Rolle.
- Im CRM anlegen: für Lexware Kontakte ohne CRM Kontakt (Name, E-Mail; keine Bankdaten).
- Nicht abgleichen: die Zeile bleibt ohne Wirkung.

Mehrdeutige Zeilen zeigen die Kandidaten. Der Filter "Abweichend" listet verknüpfte Kontakte,
deren CRM Stand nach einem Import oder einer Massenaktion nicht übertragen wurde; "Abweichende
abgleichen" stellt sie nach Bestätigung in die Warteschlange.

## Adressänderung

Nach einer im CRM angewandten Änderung (Bearbeiten des Kontakts, angenommener Vorschlag aus
einer E-Mail) wird die Adresse, die primäre E-Mail und das primäre Telefon an jede verknüpfte
Organisation übertragen. Am Ticket erscheint "Lexware Office: übertragen am TT.MM.JJJJ" oder
"Lexware Office: fehlgeschlagen, Grund". Namen werden nur mit dem Schalter "Namensänderungen
übertragen" gesendet; sonst zeigt die Zuordnung "Name weicht ab".

Konflikte: wurde der Datensatz in Lexware Office zwischenzeitlich geändert, überschreibt die
Plattform nichts. Die Zuordnung zeigt CRM Stand, Lexware Stand und letzten Stand
nebeneinander; "CRM Stand übertragen" sendet den CRM Stand, "Lexware Stand behalten" übernimmt
den Lexware Stand als neue Basis. Das CRM wird nie aus Lexware Office verändert. Mehrfach
belegte Listen, Person zu Firma und archivierte Kontakte sind in Lexware Office zu pflegen
(Deeplink an der Zeile).

## Rechnungskopie

Bittet ein Kontakt per E-Mail um eine bereits gestellte Rechnung ("Rechnung RE-1019 nochmals
zusenden"), entsteht am Ticket eine Anfrage mit der wörtlich erkannten Rechnungsnummer.
Manuell: `POST /integrations/lexoffice/tickets/{ticket}/invoice-copies` mit der Nummer
(Telefon, Schalter). Die Plattform sucht die Rechnung in jeder Organisation mit
Rechnungskopien und prüft: der anfragende Kontakt (Kontakt der Mail oder des Tickets) muss der
verknüpfte Rechnungsempfänger sein. Die Absenderadresse ist nur ein Hinweis. Abweichungen
werden korrigiert ("Anfragenden Kontakt korrigieren") oder der Empfänger aus der Anfrage heraus
verknüpft.

Nach dem Abruf liegt die PDF (bei E-Rechnungen auch die XML) im DMS unter "Rechnung (Lexware
Office)" und ein Antwortentwurf an die bekannte primäre E-Mail des Empfängers aus dem Postfach
der rechnungsstellenden Gesellschaft. Der Empfänger des Entwurfs ist gesperrt; die Freigabe
erfolgt durch eine zweite Person. Rechnungen, die in Lexware Office noch Entwurf sind, werden
nicht abgerufen.

## Rechnungsentwurf

`POST /integrations/lexoffice/invoice-drafts/preview` und `.../invoice-drafts` mit
Rechnungsart (oder Organisation), Kontakt, Belegdatum, Steuerart, Positionen, Leistungszeitraum
und Texten. Die Gesellschaft ergibt sich aus der Rechnungsart. Der Entwurf wird in Lexware
Office angelegt und dort fertiggestellt (Deeplink in der Antwort). Nicht verknüpfte Kontakte
werden als Adresse im Text übertragen.

## Dauerrechnungen

Laufende Verwaltervergütungen bleiben Dauerrechnungen in Lexware Office. Die API stellt
Dauerrechnungen nur lesend bereit. Wird ein Verwalterhonorar am Objekt erfasst, erscheint im
Reiter Dauerrechnungen eine Vorbereitung mit Debitor, Beträgen, Intervall, Beginn und Text
sowie einer Checkliste für die Anlage in Lexware Office. Nach der Anlage wird die ID der
Vorlage erfasst; der Deeplink führt zur Vorlage.

## Warteschlange

Jede Übertragung ist ein Eintrag mit Versuchen nach Plan (1 min, 5 min, 30 min, 2 h, 6 h,
24 h). Fehlgeschlagene Einträge können erneut eingeplant werden. Wird der Schlüssel
abgelehnt, hält die Organisation an, bis ein neuer Schlüssel hinterlegt und getestet ist.
Fehlertexte enthalten Status, Feld und Verstoß, nie Inhalte.

## Was nie übertragen wird

IBAN, BIC, Mandate, Steuernummern, Umsatzsteuer-IDs, Notizen, interne Beschreibungen,
Rollen und Nummern aus dem CRM, Dokumente außer der angeforderten Rechnungsdatei (die in die
Plattform kommt, nicht hinaus).

## Rechte je Rolle

| Aufgabe | Recht |
| --- | --- |
| Organisationen lesen | `tenant_settings:read` |
| Organisationen, Rechnungsarten, Warteschlange | `tenant_settings:update` |
| Kontakte zuordnen, Konflikte, Suche | `contacts:update` |
| Status am Kontakt | `contacts:read` |
| Läufe | `accounting:read` |
| Rechnungsentwürfe, Dauerrechnungen | `accounting:create` |
| Rechnungskopie anfordern, korrigieren, ablehnen | `tickets:update` |
| Rechnungskopie abrufen | `tickets:update` und `communication:update` |
