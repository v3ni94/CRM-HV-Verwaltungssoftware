# Handlungsanweisung: Bankverbindung neu anlegen oder ändern

Stand: 28.09.2026. Gilt für Bankverbindungen von Kontakten (Eigentümer, Mieter, Dienstleister).
Bankkonten der Gemeinschaft oder des Eigentümers (Rechtsträger) siehe Abschnitt Konten der
Rechtsträger. Regel: `docs/rules/M3-02-sepa-mandate.md`; Entscheidung M5-01 in
`docs/OPEN_QUESTIONS.md` (umgesetzt am 26.09.2026). Erfassungsregeln:
[Erfassungsstandards](erfassungsstandards.md).

## Zweck

Jede neue oder geänderte IBAN ist ein Betrugs- und Zahlungsrisiko. Die Plattform verwendet eine
IBAN erst, wenn eine zweite Person sie freigegeben hat (Vier-Augen-Prinzip). Diese Anleitung
beschreibt Erfassung, Nachweis, Freigabe und Ablehnung.

## Wann anwenden

- Neuer Kontakt mit Bankverbindung, SEPA-Lastschriftmandat eines Mieters oder Eigentümers.
- Mitteilung einer neuen IBAN per Brief, Mail, Portal oder auf einer Rechnung.

Grundsatz: Eine IBAN aus einer E-Mail oder einer Rechnung ist kein Nachweis. Vor der Erfassung
beim Kontakt über eine bereits bekannte Telefonnummer oder Anschrift rückfragen und die
Rückfrage vermerken.

## Voraussetzungen

- Erfassen: `contacts:create` (neuer Kontakt) beziehungsweise `contacts:update`.
- Freigeben oder Ablehnen: `contacts:approve`, in der Vorbelegung nur Mandantenadministrator und
  Administrator. Die freigebende Person muss eine andere sein als die erfassende; ein zweites
  Benutzerkonto derselben Person zählt nicht. Plattformadministratoren geben keine IBAN frei.
- Nachweis im Original (Schreiben mit Unterschrift, unterschriebenes Mandat, Vermerk über die
  Rückfrage).

## Ablauf in der Software

### 1. Nachweis ablegen

Verwaltung, DMS, Suche im Archiv, Dokument hochladen (Objekt und gegebenenfalls Einheit); ein
Mandat als PDF wird direkt im Formular an der Bankverbindung hochgeladen. Ablage 01 Legitimationsunterlagen bei Mandaten und Vollmachten,
sonst in der Mieter- oder Eigentümerakte.

### 2a. Neuer Kontakt mit Bankverbindung

Übersicht, Kontakte, Kontakt anlegen, Abschnitt Bankverbindungen, Hinzufügen:

- Bezeichnung, Kontotyp, Standardkonto (genau ein Konto)
- IBAN (ohne Leerzeichen), BIC, Bank, Kontoinhaber
- Gültig ab, Gültig bis
- Bei Lastschrift: SEPA-Lastschrift aktiv, Mandatsreferenz, Datum der Erteilung, Erteilungsart,
  Mandatsart und entweder Mandat als PDF oder Vermerk. Ohne Datum der Erteilung, Erteilungsart
  und Nachweis lässt sich die SEPA-Freigabe nicht speichern.

Speichern. Die Bankverbindung steht im Status zur Freigabe.

### 2b. Bestehender Kontakt: neue oder geänderte IBAN

Die Oberfläche erlaubt an einem bestehenden Kontakt keine neue Bankverbindung: im Formular
Kontakt bearbeiten erscheinen vorhandene Bankverbindungen nur maskiert mit dem Hinweis
Bankverbindungen bleiben beim Speichern unverändert. Wege:

1. Vorschlag aus dem Portal: Hat der Kontakt die IBAN oder ein Mandat über das Portal
   mitgeteilt, erscheint sie auf der Kontaktseite unter Vorschläge aus dem Portal
   (Stammdatenänderungen, Art Bankverbindung, oder SEPA-Lastschriftmandate). Nachweis prüfen,
   Übernehmen. Die IBAN steht danach im Status zur Freigabe.
2. Schnittstelle: Eine Person mit Schnittstellenzugang schreibt die Bankverbindungen des
   Kontakts neu (`PUT /api/v1/contacts/{id}` mit vollständiger Liste `bank_accounts`). Bekannte
   IBAN behalten ihren Freigabestand, jede neue IBAN steht im Status zur Freigabe. Konten, auf
   die ein SEPA-Mandat verweist, lassen sich auf diesem Weg nicht ersetzen.
3. Solange keiner der beiden Wege verfügbar ist: Ticket zum Kontakt mit Nachweis an den
   Administrator; keine IBAN im Notizfeld oder in Ticketnotizen erfassen.

### 3. Freigabe durch eine zweite Person

Übersicht, Start, Spalte Freigaben, Kachel Bankverbindungen, oder Kontaktseite, Reiter
Bankverbindungen, Abschnitt Freigabe:

1. Nachweis öffnen und IBAN, Kontoinhaber und Kontakt vergleichen.
2. Freigeben: Hinweis IBAN freigegeben.
3. Oder Ablehnen: Begründung der Ablehnung (Pflicht), Ablehnung bestätigen. Die Begründung wird
   protokolliert.

Die eigene Erfassung zeigt selbst erfasst, Freigabe durch eine andere Person.

### 4. Folgeschritte

- Erst nach Freigabe ist die IBAN in SEPA-Mandaten, Lastschrift- und Zahlungsläufen und im
  Rechnungsabgleich nutzbar. Eine Rechnung mit abweichender IBAN meldet der Belegeingang.
- Ändert sich die IBAN eines aktiven Mandats, vermerkt die Plattform das am Mandat; ob ein neues
  Mandat einzuholen ist, entscheidet die Geschäftsführung.
- Einzug und Überweisung bleiben bis G2 gesperrt.

## Konten der Rechtsträger

Konten der Gemeinschaft oder des Eigentümers werden unter Einstellungen, Bank (finAPI) oder
FinTS lesend angebunden und auf der Objektseite im Abschnitt Bankkonten des Objekts zugeordnet
(Als Standard setzen, Standard des Rechtsträgers). Für diese Konten gibt es keine
Vier-Augen-Freigabe der IBAN in der Software; die Anmeldung erfolgt über das Formular der Bank.
Neue Konten und Standardkonten sind organisatorisch durch die Geschäftsführung freizugeben.

## Zu verknüpfende Datensätze

| Datensatz | Was |
| --- | --- |
| Kontakt | Bankverbindung, Nachweis, Mandat |
| Vertrag | SEPA-Mandat und Kennzeichen Lastschrift (nur mit aktivem Mandat) |
| Ticket | Mitteilung und Rückfragevermerk |

## Fristen

Kein Fristtyp. Offene Freigaben stehen auf der Startseite. Für Rückfragen beim Kontakt Ticket
mit Fälligkeit anlegen.

## Freigaben

| Schritt | Wer | Durch die Software erzwungen |
| --- | --- | --- |
| Neue oder geänderte IBAN eines Kontakts | zweite Person mit `contacts:approve` | ja |
| Abweichende IBAN auf Rechnung | nur nach Rückruf beim Aussteller, gesondert protokolliert | ja |
| Konto eines Rechtsträgers | Geschäftsführung | nein |

## Checkliste

- [ ] Nachweis im Original vorhanden und abgelegt
- [ ] Rückfrage über bekannte Kontaktdaten erfolgt und vermerkt
- [ ] IBAN ohne Leerzeichen, Kontoinhaber vollständig
- [ ] Bei Lastschrift: Mandatsreferenz, Datum der Erteilung, Erteilungsart, Nachweis
- [ ] Freigabe durch eine zweite Person
- [ ] Mandat und Vertrag geprüft

## Häufige Fehler

- IBAN ungültig: Eingabe ohne Leerzeichen mit Länderpräfix wiederholen.
- Freigabe abgewiesen: dieselbe Person hat erfasst, oder die Bankverbindung wartet nicht mehr auf
  Freigabe.
- Lastschrift nutzt die neue IBAN nicht: Freigabe fehlt.
- IBAN aus KI-Vorschlag übernommen: KI-Vorschläge enthalten nie eine Übernahme von Bankdaten.

## Lücken in der Software

- Keine Oberfläche, um an einem bestehenden Kontakt eine Bankverbindung hinzuzufügen, zu ändern
  oder zu beenden; nur Portalvorschlag oder Schnittstelle.
- Keine Vier-Augen-Freigabe für Bankkonten der Rechtsträger.
- `contacts:approve` in der Vorbelegung nur bei Administratorrollen; für die Buchhaltung ist eine
  eigene Rolle anzulegen, wenn sie freigeben soll.
- Kein Feld für den Rückfragevermerk an der Bankverbindung (nur Vermerk beim Mandat).
