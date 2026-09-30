# Fristen (Deadlines)

## Zweck

Das Menü Fristen listet wichtige Termine aus den Stammdaten und bietet eine zentrale Übersicht über Fälligkeiten und Stichtage. Die Liste ist eine Orientierungshilfe und ersetzt keine rechtliche Fristberechnung (Regel WS-01).

Fristen kommen aus mehreren Quellen:

- Verträge (Vertragsende, Kündigungsfrist, Kündigung)
- Zähler (Eichfrist)
- Bankzustimmungen (Ablaufdatum von Aggregator-Zustimmungen)
- Dokumente (Aufbewahrungsfrist endet)
- Dienstleisterverträge (Kündigungsfristen und Anläufe)
- Beschlüsse (Beschlussfrist virtuelle Versammlung)
- Benutzer erfasste Fristen (Fristtyp aus dem Katalog)
- Wartungen (fällige und überfällige)
- Terminierungen (Kalender, Mieterhöhungsfälle, Tickets)

## Vorbedingungen

- Berechtigung `workspace:read`

## Bedienung

Das Menü zeigt oben Links zu Fristen-Seiten; darunter die Tabelle mit Spalten:

- **Termin**: Fälligkeit der Frist oder des Termins.
- **Typ**: Art der Frist (z. B. Vertragsende, Kündigung, Eichfrist); eigene Fristen als „Eigene Frist".
- **Bezug**: Kontext (Vertrag, Einheit, Objekt, Meter, Wartung, etc.). Ein Klick öffnet den Datensatz.
- **Verantwortlich**: bei eigenen Fristen die eingetragene Person.
- **Status**: offen oder erledigt (Regel WS-01).

Filter oben:

- **Typ** (optional): nur ein Fristtyp oder alle zeigen.
- **Status**: offen, erledigt oder alle.
- **Zeitraum** (optional): von / bis (ISO 8601 Format). Vorgabe: heute bis +90 Tage.

Fristen und Termine werden auf der Startseite zusammengefasst (Abschnitt „Heute" und „Nächste sieben Tage"). Vorfristbenachrichtigungen kommen vom Tagesjob (Einstellungen, Tagesjobs, Vorfrist-Tage, Vorgabe 30 Tage).

## Eigene Fristen

Regel WS-01: Auf Tickets, Verträgen, Einheiten, Objekten und Mieterhöhungsfällen kann im Abschnitt „Fristen" eine benutzerdefinierte Frist angelegt werden:

- **Fristtyp** aus dem Katalog des Mandanten (Einstellungen, Fristtypen).
- **Auslösedatum**: Starttag der Berechnung.
- **Fälligkeit**: Enddatum (berechnet aus der Dauer des Typs oder eingetragen; immer zu verifizieren).
- **Verantwortlich**: Person oder Rolle (Erfassungsstandard ES-10).

Die Frist wird in die Fristenliste und den Kalender übernommen. Die Vorfrist benachrichtigt die verantwortliche Person.

Fristtypen, Dauer und Vorfrist-Tage pflegt die Geschäftsführung unter Einstellungen, Fristtypen. Die Typen Verwalterwechsel, Kautionsabrechnung und Mieterhöhung sind ohne Dauer angelegt; die Dauer ist nach rechtlicher Prüfung festzulegen.

## Grenzen

Die berechneten Termine sind Orientierung; für Notfristen und rechtlich maßgebliche Fristen ist eine manuelle Prüfung erforderlich. Berechnete Vorfristenanlässe folgen der Konfiguration, nicht einer Gesetzesregel.

Im Parallelbetrieb mit Immoware24 werden Fristen nur in der Plattform geführt (kein Rückschreiben).
