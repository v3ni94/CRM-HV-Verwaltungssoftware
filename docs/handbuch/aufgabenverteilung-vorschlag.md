# Aufgabenverteilung Mail und Tickets: Vorschlag

**Vorschlag zur Entscheidung durch die Geschäftsführung.** Stand: 28.09.2026. Nicht in Kraft,
bis die Geschäftsführung ihn freigibt. Enthält keine Namen; die Besetzung der Rollen legt die
Geschäftsführung fest.

## Ziel

Jede eingehende Mail wird am selben Tag einem Objekt, einem Kontakt und einer zuständigen
Person zugeordnet. Fachliche Bearbeitung und Freigabe liegen bei verschiedenen Personen, wo die
Software ein Vier-Augen-Prinzip vorsieht oder wo Geld, Fristen oder Rechtsfolgen betroffen
sind.

## Grundlagen in der Software

- Jede neue Mail in einem verbundenen Postfach erzeugt ein Ticket (Kapitel [Mail](mail.md),
  [Tickets](tickets.md)).
- Die automatische Bearbeiterzuweisung nutzt Postfach, Anrede, Signatur, Kompetenz und
  bisherige Zuordnung; sie ist ein Vorschlag. Kompetenzen pflegt man unter Einstellungen,
  Benutzer und Rollen, Kompetenzen bearbeiten.
- Rechte werden je Rolle vergeben (Einstellungen, Rollen und Rechte). Systemrollen sind nicht
  änderbar; eigene Rollen legt man mit Rolle anlegen (Code, Name) an und weist Rechte zu.
- Rechte haben die Form Bereich und Aktion, zum Beispiel `contacts:approve`. Aktionen: read,
  create, update, delete, approve, export.
- Löschen (`*:delete`) hat nur der Mandantenadministrator (Regel `docs/rules/M2-07.md`).

## Systemrollen im CRM (Auszug aus `mhvp.core.auth.permissions`)

| Systemrolle | Wesentliche Rechte |
| --- | --- |
| Mandantenadministrator, Administrator | alle Rechte des Mandanten außer Freigabestufen genehmigen |
| Standard | Stammdaten, Verträge, Dokumente lesen, anlegen, ändern; Buchhaltung lesen und schreiben; Tickets einschließlich `tickets:approve`; Kommunikation; SLA; WEG; Objektakte einschließlich Regelpflege; Messdienst Sachbearbeitung |
| Sachbearbeiter ohne Löschen | Stammdaten, Verträge, Dokumente; Tickets und Kommunikation lesen, anlegen, ändern; Objektakte Prüffälle |
| Sachbearbeiter ohne Buchhaltung | wie Standard ohne Buchhaltung und ohne Regelpflege Objektakte |
| Buchhalter ohne Onlinebanking | Kontakte schreiben; Objekte und Verträge lesen; Dokumente; Buchhaltung einschließlich `accounting:approve` und Export |
| Buchhalter mit Onlinebanking | wie vor, zusätzlich Banking einschließlich `banking:approve` |
| Technischer Sachbearbeiter | Objekte und Dokumente schreiben, Kontakte lesen, Tickets, Kommunikation |
| Hausmeister | Objekte lesen, Tickets |
| Nur Lesezugriff, Nur Lesezugriff Stammdaten, Support | lesend |
| Freigabe | zweite Person der Vier-Augen-Freigabe von Bankverbindungen (`contacts:approve`); Kontakte, Objekte, Verträge, Dokumente lesen; keine Schreibrechte auf Stammdaten |
| Steuerberater | Buchhaltung lesen und exportieren, begrenzt auf gewählte Rechtsträger |

Wichtig: Die Freigaberechte `contacts:approve` (IBAN), `contracts:approve` (Importverträge,
Mieterhöhung), `communication:approve` (Mailfreigabe) und `hoa:approve` sind in keiner
Sachbearbeiter- oder Buchhalterrolle enthalten, nur in den Administratorrollen.

## Vorgeschlagene Funktionsrollen

### 1. Posteingang und Zuordnung

Aufgaben:
- Mail, Posteingang und Übersicht, Tickets täglich bis zu einer festgelegten Uhrzeit sichten.
- Je Ticket Objekt, Einheit und Kontakt verknüpfen, Kategorie prüfen, Bearbeiter zuweisen
  (Vorschlag der Zuweisung bestätigen oder ändern).
- Rechnungen in den Belegeingang geben, Dubletten zusammenführen, Werbung und Irrläufer mit
  Erledigungsart Kein Handlungsbedarf abschließen.
- Einfache Auskünfte mit Antwortvorlagen, sofern freigegeben.

CRM-Rolle: Sachbearbeiter ohne Löschen. Kompetenz: Posteingang.

### 2. Objektbetreuung WEG

Aufgaben: Tickets der WEG-Objekte, Eigentümerkommunikation, Versammlungen, Beschlüsse,
Einsichtsanfragen, Maßnahmen und Versicherungsfälle, Eigentümerwechsel
([Anleitung](anleitung-eigentuemerwechsel.md)), Verwalterwechsel
([Anleitung](anleitung-verwalterwechsel.md)).

CRM-Rolle: Sachbearbeiter ohne Buchhaltung (enthält WEG `hoa`). Kompetenz je Objekt oder
Objektgruppe.

### 3. Mietverwaltung

Aufgaben: Tickets der Miet- und SEV-Objekte, Mieterwechsel und Übergaben
([Anleitung](anleitung-mieterwechsel.md)), Mieterhöhungen vorbereiten
([Anleitung](anleitung-mieterhoehung.md)), Kautionsabrechnung als Entwurf, Stammdatenpflege.

CRM-Rolle: Sachbearbeiter ohne Buchhaltung oder Sachbearbeiter ohne Löschen. Kompetenz je
Objekt.

### 4. Technik

Aufgaben: Schadensmeldungen, Aufträge an Dienstleister, Wartungen, Zähler, Energieausweis.

CRM-Rolle: Technischer Sachbearbeiter. Hausmeister nur mit Rolle Hausmeister.

### 5. Buchhaltung

Aufgaben: Belegeingang, Rechnungsprüfung, zweite Freigabe von Rechnungen, Bankabgleich,
Mahnwesen als Vorschau, Kautionen, Abrechnungsvorbereitung. Alles bleibt hinter G1 bis G4.

CRM-Rolle: Buchhalter ohne Onlinebanking; Buchhalter mit Onlinebanking nur für die Person, die
Bankverbindungen der Rechtsträger einrichtet.

### 6. Freigaben und Vier-Augen-Prinzip

Aufgaben: alle Freigaben, die eine zweite Person verlangen, gesammelt über Übersicht, Start,
Spalte Freigaben.

| Freigabe | Recht | Von der Software erzwungen |
| --- | --- | --- |
| Neue oder geänderte IBAN eines Kontakts | `contacts:approve` | ja, andere Person als die Erfassende |
| Mail- und Ticketantworten im Freigabemodus | `communication:approve` | ja, je nach Einstellung |
| Mieterhöhung freigeben | `contracts:approve` | ja, andere Person als die Anlegende |
| Importverträge freigeben | `contracts:approve` | Recht ja |
| Rechnung freigeben (zweite Person) | `accounting:approve` | ja |
| Mahnlauf freigeben | Buchhaltungsfreigabe | ja, zweite Person |
| Lastschrift- und Zahlungsläufe | Buchhaltungs- und Bankingfreigabe | ja, zwei Personen, hinter G2 |
| Löschvorschläge | Vier-Augen-Prinzip | ja |
| Kündigungen, Zahlungszusagen, Anerkenntnisse, Fristzusagen | Geschäftsführung | nein, organisatorisch |

Vorschlag: eine eigene Rolle Freigabe anlegen (Einstellungen, Rollen und Rechte, Rolle anlegen)
mit `contacts:approve`, `communication:approve`, `contracts:approve` und Leserechten auf
Kontakte, Verträge, Dokumente und Tickets. Die Rolle erhalten mindestens zwei Personen, damit
Vertretung möglich ist und niemand eigene Erfassungen freigeben muss. Die Personen der
Buchhaltung erhalten diese Rolle nicht für Vorgänge, die sie selbst erfasst haben; die Software
verhindert das bei IBAN und Mieterhöhung ohnehin.

## Regeln für Mail und Tickets

1. Zuordnung vor Bearbeitung: kein Ticket ohne Objekt oder begründete Kennzeichnung nicht
   objektbezogen.
2. Neue Mitarbeiter und Auszubildende erhalten die Freigabepflicht für Ticketantworten
   (Einstellungen, Benutzer und Rollen, Freigabepflicht für Ticketantworten, Grund, Befristet
   bis).
3. Freigabemodus der Postfächer (Einstellungen, Postfächer): Vorschlag Nur externe Empfänger
   freigeben; Entscheidung der Geschäftsführung.
4. Vertretungen für die Mailfreigabe unter Einstellungen, Postfächer hinterlegen.
5. Fälligkeit am Ticket setzen, wenn eine Frist läuft; Fristen mit Rechtsbezug der
   Geschäftsführung vorlegen.
6. Abschluss nur mit Erledigungsart und Erledigungsnotiz.
7. Bankdaten aus Mails nie übernehmen, nur nach Anleitung
   [Bankverbindung](anleitung-bankverbindung.md).

## Kennzahlen zur Steuerung

Übersicht, Auswertung Tickets: Durchsatz, Rückstand, Reaktionszeiten je Bearbeiter und
Postfach ([Auswertung Tickets](auswertung-tickets.md)). Vorschlag: wöchentliche Durchsicht durch
die Geschäftsführung.

## Offene Entscheidungen der Geschäftsführung

- Besetzung der sechs Funktionsrollen und Vertretungen.
- Anlage der Rolle Freigabe und Zuordnung der Freigaberechte.
- Freigabemodus je Postfach.
- Uhrzeit für die tägliche Sichtung des Posteingangs.
- Zuschnitt der Kompetenzen je Objekt oder Objektgruppe.
