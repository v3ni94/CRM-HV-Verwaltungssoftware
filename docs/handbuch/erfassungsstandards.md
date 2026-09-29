# Erfassungsstandards

Die automatische Zuordnung von Mails und Tickets zu Kontakt, Objekt und Einheit funktioniert
nur, wenn alle Mitarbeitenden Stammdaten gleich erfassen. Diese Seite beschreibt die
verbindlichen Standards. Die Plattform zeigt Abweichungen beim Erfassen als Hinweis an und
listet bestehende Abweichungen unter **Einstellungen, Datenqualität**. Bestehende Daten werden
nie automatisch geändert.

Technische Grundlage: Regeln ES-01 bis ES-11 (`docs/rules/ES-erfassungsstandards.md`), Code in
`mhvp.dataquality.rules` (Server) und `src/lib/entry-standards.ts` (CRM).

## Grundsatz: Hinweis statt Sperre

| Stufe | Wirkung | Regeln |
| --- | --- | --- |
| Fehler | Speichern nicht möglich, auch nicht über die API | ES-01 |
| Warnung | Gelber Hinweis im Formular, Speichern bleibt möglich, Eintrag im Bericht Datenqualität | ES-02, ES-03, ES-05, ES-06, ES-07, ES-09, ES-10, ES-11 |
| Hinweis | Gelber Hinweis im Formular, Speichern bleibt möglich | ES-04, ES-08 (Vorname fehlt) |

Hart geprüft wird nur, was eindeutig falsch ist. Alle anderen Regeln sind Empfehlungen, weil es
berechtigte Ausnahmen gibt (zum Beispiel ein Objekt ohne Hausnummer oder ein Kontakt, von dem nur
der Nachname bekannt ist).

## Objekte

| Feld | Standard | Beispiel |
| --- | --- | --- |
| Straße | nur der Straßenname, ohne Hausnummer (ES-03) | Rheinpromenade |
| Hausnummer | eigenes Feld, Zusätze direkt angehängt, Bereiche mit Bindestrich | 13, 4a, 4a-6 |
| PLZ | in Deutschland genau fünf Ziffern (ES-01, hart) | 40789 |
| Ort | amtlicher Ortsname | Monheim am Rhein |
| Name | **Straße Hausnummer, PLZ Ort** (ES-04) | Rheinpromenade 13, 40789 Monheim am Rhein |

- Fehlen Straße, Hausnummer, PLZ oder Ort, erscheint eine Warnung (ES-02); die Zuordnung von
  Mails über die Anschrift braucht alle vier Angaben.
- Beim Anlegen schlägt das Formular den Namen aus der Anschrift vor; **Vorschlag übernehmen**
  setzt ihn in das Feld Name.
- Die PLZ Prüfung gilt nur für das Land DE. Für andere Länder wird die PLZ nicht geprüft.
- Die harte PLZ Prüfung greift beim Anlegen und wenn PLZ oder Land geändert werden. Ein
  bestehendes Objekt mit abweichender PLZ bleibt lesbar und in anderen Feldern änderbar; es steht
  im Bericht Datenqualität.

## Kontakte

Kontakte haben getrennte Felder für Vorname und Nachname. Die Anzeige **Name, Vorname** (zum
Beispiel "Schmidt, Anna") setzt die Plattform selbst zusammen; sie ist eine Anzeige und
Sortierregel und wird nie als Freitext eingegeben.

| Regel | Standard | Hinweis erscheint bei |
| --- | --- | --- |
| ES-05 | Nachname und Vorname in getrennten Feldern | Komma im Feld Nachname oder Vorname, etwa "Schmidt, Anna" |
| ES-06 | Vorname nicht im Feld Nachname | Vorname leer und Nachname aus mehreren Wörtern, etwa "Anna Schmidt" (Namenszusätze wie "von", "van", "de" am Anfang gelten als Teil des Nachnamens) |
| ES-07 | Firmen als Art **Firma** erfassen | Firmenbestandteil im Personennamen, etwa GmbH, AG, KG, GbR, UG, e. V., WEG, Hausverwaltung, Stadtwerke, Bank |
| ES-08 | Vorname bei Personen, Firmenname bei Firmen | Pflichtangabe leer |
| ES-11 | Eigentümer und Mieter mit E-Mail-Adresse | Rolle Eigentümer oder Mieter ohne E-Mail (nur im Bericht) |

- **Dubletten**: Beim Anlegen prüft das Formular wie bisher auf ähnliche Kontakte (Name, E-Mail,
  Telefon, IBAN) und zeigt Treffer vor dem Speichern an. Speichern ist danach trotzdem möglich.
- Ohne E-Mail-Adresse können eingehende Mails eines Eigentümers oder Mieters nicht automatisch
  zugeordnet werden (ES-11).

## Fristen

Fristen mit verantwortlicher Person sind die Fälligkeiten von Tickets (Feld **Fälligkeit**, die
verantwortliche Person ist der Bearbeiter des Tickets). Automatisch abgeleitete Fristen der
Fristenliste (Vertragsende, Eichfristen, Aufbewahrung) haben keine eigene verantwortliche Person;
für sie gelten diese Regeln nicht.

| Regel | Standard | Wirkung |
| --- | --- | --- |
| ES-09 | Fristdatum nicht in der Vergangenheit | Beim Anlegen muss ein vergangenes Datum ausdrücklich bestätigt werden (Kontrollkästchen); beim Ändern wird ein vergangenes Datum erst nach **Vergangenes Datum bestätigen** gespeichert |
| ES-10 | Jede Frist hat eine verantwortliche Person | Hinweis beim Anlegen; offene Tickets mit Fälligkeit ohne Bearbeiter stehen im Bericht Datenqualität |

Alle Fristen der Plattform sind Orientierung und bleiben zu prüfen; die Standards ersetzen keine
rechtliche Fristberechnung.

## Bericht Datenqualität

**Einstellungen, Datenqualität** listet alle Datensätze, die vom Standard abweichen, mit einem
Link **Öffnen** zum Datensatz:

1. Objekte mit fehlender oder abweichender Anschrift und Objektnamen außerhalb des Musters
   (beendete Objekte nicht).
2. Kontakte mit vermutlich vertauschten oder falsch erfassten Namen.
3. Eigentümer und Mieter ohne E-Mail-Adresse (gesperrte und gelöschte Kontakte nicht).
4. Offene Tickets mit Fälligkeit ohne verantwortliche Person.

Voraussetzung ist das Recht Kontakte lesen. Die Abschnitte Objekte und Fristen erscheinen nur mit
dem Recht Objekte lesen beziehungsweise Tickets lesen. Je Abschnitt werden höchstens 200 Einträge
angezeigt, die Gesamtzahl steht daneben. Der Bericht ändert keine Daten; korrigiert wird im
jeweiligen Datensatz.

Über die API: `GET /api/v1/data-quality/report` (Bericht) und `POST /api/v1/data-quality/check`
(Prüfung eines Entwurfs ohne Speichern, nur Hinweise).

## Fotos im Übergabeprotokoll (M31 WP2, 29.09.2026)

Das Foto zu einem Mangel oder Zähler wird direkt beim Anlegen des Eintrags aufgenommen
(Foto aufnehmen oder Aus Galerie wählen). Standard sind ein Übersichtsfoto je Raum und ein
Detailfoto je Mangel; das Zählerfoto zeigt Zählernummer und Stand lesbar. Fotos werden
serverseitig ohne Metadaten gespeichert (keine Ortsangabe, kein Aufnahmezeitpunkt aus der
Kamera); der Zeitpunkt im Protokoll ist der Upload.
