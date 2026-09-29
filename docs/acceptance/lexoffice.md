# Abnahmelauf Lexware Office (Testkonto)

Nicht ausgeführt (Stand 29.09.2026, docs/OPEN_QUESTIONS.md LEXO-13). Der Betreiber stellt ein
Testkonto und einen Schlüssel bereit; kein Schalter wird produktiv aktiviert, bevor dieser Lauf
mit Datum dokumentiert ist. Erwartete Ergebnisse sind fest vorgegeben.

| Nr | Prüfung | Erwartung |
| --- | --- | --- |
| 1 | `GET /v1/voucherlist?voucherType=invoice&voucherStatus=any&voucherNumber=RE-1019` mit den Rechnungen RE-1019 und RE-10190 im Konto | die API liefert beide (Teilzeichenkette), die Plattform zeigt nach dem exakten Nachfilter genau einen Treffer |
| 2 | `PUT /v1/contacts/{id}` mit einem Objekt, in dem `note` fehlt | `note` ist danach leer, deshalb sendet die Plattform immer das vollständig gelesene Objekt; im Abnahmelauf mit einem Testkontakt bestätigen |
| 3 | `GET /v1/invoices/{id}/file` für eine Rechnung im Status draft | 409, die Plattform meldet "noch nicht abgeschlossen" |
| 4 | `POST /v1/contacts` ohne `person.lastName` und `POST /v1/invoices` ohne `lineItems` | 406 mit `IssueList` (Kontakte) und `details[]` (Rechnungen); die Fehlermeldung der Plattform enthält Feld und Verstoß, keinen Freitext |
| 5 | 504 Verhalten | Existenzprüfung vor der Wiederholung (Kontakt über `?email=`, Entwurf über die Belegliste) |
| 6 | Organisation ohne Rechnungsfunktion | `businessFeatures` ohne INVOICING, die Schalter Rechnungskopien und Rechnungsentwürfe sind gesperrt |
| 7 | `GET /v1/profile` | `organizationId`, `companyName`, `taxType`, `smallBusiness`, `businessFeatures` vorhanden und an der Konfiguration sichtbar |
| 8 | `GET /v1/recurring-templates` | nur lesend; ein POST wird nicht versucht |
| 9 | Anfragelimit | 30 Warteschlangeneinträge über zwei Konfigurationen derselben Organisation erzeugen kein 429 |
