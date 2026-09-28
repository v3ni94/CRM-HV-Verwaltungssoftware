# Handlungsanweisung: Bankverbindung neu anlegen oder ändern

Stand: 28.09.2026 (Nachtrag: Bankverbindungen am bestehenden Kontakt, Rolle Freigabe). Gilt für
Bankverbindungen von Kontakten (Eigentümer, Mieter, Dienstleister) und für die Kontakte der
Rechtsträger (Gemeinschaft, Eigentümer, Verwaltung). Angebundene Bankkonten der Rechtsträger
siehe Abschnitt Konten der Rechtsträger. Regel: `docs/rules/M3-02-sepa-mandate.md`;
Entscheidung M5-01 in `docs/OPEN_QUESTIONS.md` (umgesetzt am 26.09.2026), Nachtrag M5-04
(28.09.2026). Erfassungsregeln: [Erfassungsstandards](erfassungsstandards.md).

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
- Freigeben oder Ablehnen: `contacts:approve`, in der Vorbelegung Mandantenadministrator,
  Administrator und die Systemrolle Freigabe (nur Freigabe und Lesen, keine Schreibrechte auf
  Stammdaten; gedacht für die Buchhaltung, Zuweisung unter Einstellungen, Benutzer). Die
  freigebende Person muss eine andere sein als die erfassende; ein zweites Benutzerkonto
  derselben Person zählt nicht. Plattformadministratoren geben keine IBAN frei.
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

### 2b. Bestehender Kontakt: Bankverbindung hinzufügen

Kontaktseite, Reiter Bankverbindungen, Schaltfläche Bankverbindung hinzufügen (Recht
`contacts:update`). Felder wie unter 2a: IBAN (Prüfziffer wird sofort geprüft), BIC, Bank,
Kontoinhaber, Bezeichnung, Kontotyp, Standardkonto, Gültig ab, Gültig bis. Speichern. Die
Bankverbindung steht im Status zur Freigabe; die übrigen Bankverbindungen des Kontakts bleiben
unverändert. Ein SEPA-Mandat wird an der bestehenden Bankverbindung geführt (Abschnitt 4).

Das Formular Kontakt bearbeiten zeigt vorhandene Bankverbindungen weiterhin nur maskiert und
lässt sie unverändert; Bankverbindungen werden ausschließlich im Reiter Bankverbindungen
gepflegt.

### 2c. Bestehender Kontakt: IBAN ändern (neue Version)

Reiter Bankverbindungen, an der freigegebenen Bankverbindung Ändern. Das Formular ist mit
Bank, BIC, Kontoinhaber, Bezeichnung und Kontotyp der bisherigen Bankverbindung vorbelegt; neue
IBAN und Gültig ab eintragen (Gültig ab muss nach dem Gültig ab der bisherigen liegen).
Speichern. Die neue IBAN steht im Status zur Freigabe und trägt den Hinweis ersetzt
(bisherige IBAN). Bis zur Freigabe bleibt die bisherige Bankverbindung unverändert gültig.
Mit der Freigabe endet die bisherige Bankverbindung am Tag vor dem neuen Gültig ab und gibt
das Kennzeichen Standardkonto an die neue Version ab. Die bisherige IBAN bleibt als Historie
sichtbar und wird nie überschrieben. Bei aktivem SEPA-Mandat auf der bisherigen
Bankverbindung entsteht mit der Freigabe ein angehefteter Vermerk; das Mandat wird nicht
automatisch widerrufen (Abschnitt 4).

Je Bankverbindung ist nur eine offene Änderung möglich; eine zweite Änderung oder Beendigung
wird abgewiesen, bis die erste entschieden ist.

### 2d. Bestehender Kontakt: Bankverbindung beenden

Reiter Bankverbindungen, an der freigegebenen Bankverbindung Beenden: Gültig bis und Vermerk
(zum Beispiel Rückfrage beim Kontakt), Beendigung speichern. Zwei Fälle:

- Sofort wirksam: die erfassende Person hat `contacts:approve` und der Kontakt ist kein
  Rechtsträger. Hinweis Bankverbindung beendet zum Datum.
- Zur Freigabe: die erfassende Person hat kein `contacts:approve`, oder der Kontakt ist ein
  Rechtsträger (Mitglied der Partei einer Gemeinschaft, eines Vermieters oder eines
  SEV-Eigentümers, oder Kontakttyp Verwaltung). Die Bankverbindung zeigt Beendigung zum Datum
  zur Freigabe; eine zweite Person bestätigt oder lehnt ab (Abschnitt 3). Die eigene
  Erfassung zeigt selbst beantragt, Freigabe durch eine andere Person.

Weitere Wege bleiben bestehen: Vorschlag aus dem Portal (Reiter Portal-Freigaben, Nachweis
prüfen, Übernehmen, IBAN danach zur Freigabe) und Schnittstelle (`POST
/api/v1/contacts/{id}/bank-accounts`, `.../replace`, `.../end`; `PUT /api/v1/contacts/{id}`
mit vollständiger Liste `bank_accounts` schreibt alle Bankverbindungen neu und ist nur für
Schnittstellenzugänge gedacht). Keine IBAN im Notizfeld oder in Ticketnotizen erfassen.

### 3. Freigabe durch eine zweite Person

Übersicht, Start, Spalte Freigaben, Kachel Bankverbindungen, oder Kontaktseite, Reiter
Bankverbindungen, Abschnitt Freigabe:

1. Nachweis öffnen und IBAN, Kontoinhaber und Kontakt vergleichen.
2. Freigeben: Hinweis IBAN freigegeben. Bei einer neuen Version (Hinweis ersetzt) endet damit
   die bisherige Bankverbindung am Tag vor dem neuen Gültig ab.
3. Oder Ablehnen: Begründung der Ablehnung (Pflicht), Ablehnung bestätigen. Die Begründung wird
   protokolliert.
4. Offene Beendigung (Beendigung zum Datum zur Freigabe): Vermerk lesen, Bestätigen oder
   Ablehnen mit Begründung. Erst mit der Bestätigung erhält die Bankverbindung Gültig bis.

Die eigene Erfassung zeigt selbst erfasst beziehungsweise selbst beantragt, Freigabe durch
eine andere Person. Die Kachel Bankverbindungen auf der Startseite zählt offene IBAN und
offene Beendigungen zusammen.

### 4. Folgeschritte

- Erst nach Freigabe ist die IBAN in SEPA-Mandaten, Lastschrift- und Zahlungsläufen und im
  Rechnungsabgleich nutzbar. Eine Rechnung mit abweichender IBAN meldet der Belegeingang.
- Ändert sich die IBAN eines aktiven Mandats, vermerkt die Plattform das am Mandat; ob ein neues
  Mandat einzuholen ist, entscheidet die Geschäftsführung.
- Einzug und Überweisung bleiben bis G2 gesperrt.

## Konten der Rechtsträger

Zwei Ebenen:

1. Bankverbindungen am Kontakt des Rechtsträgers (Gemeinschaft, Vermieter, SEV-Eigentümer,
   Verwaltung selbst): Erfassung, Änderung und Beendigung wie oben über die Kontaktseite. Jede
   Änderung, auch die Beendigung und auch durch eine Person mit `contacts:approve`, wartet auf
   eine zweite Person (Vier-Augen-Prinzip in der Software erzwungen). Als Rechtsträger
   erkennt die Software Kontakte, die Mitglied der Partei eines Rechtsträgers sind oder den
   Kontakttyp Verwaltung tragen.
2. Angebundene Bankkonten: Konten der Gemeinschaft oder des Eigentümers werden unter
   Einstellungen, Bank (finAPI) oder FinTS lesend angebunden und auf der Objektseite im
   Abschnitt Bankkonten des Objekts zugeordnet (Als Standard setzen, Standard des
   Rechtsträgers). Die Anmeldung erfolgt über das Formular der Bank. Für Zuordnung und
   Standardkonto gibt es weiterhin keine Vier-Augen-Freigabe in der Software; sie sind
   organisatorisch durch die Geschäftsführung freizugeben (`docs/OPEN_QUESTIONS.md` M5-04).

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
| Beendigung einer Bankverbindung durch eine Person ohne `contacts:approve` | zweite Person mit `contacts:approve` | ja |
| Beendigung einer Bankverbindung am Kontakt eines Rechtsträgers | zweite Person mit `contacts:approve` | ja |
| Abweichende IBAN auf Rechnung | nur nach Rückruf beim Aussteller, gesondert protokolliert | ja |
| Angebundenes Bankkonto eines Rechtsträgers (Zuordnung, Standardkonto) | Geschäftsführung | nein |

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
- Für diese Bankverbindung wartet bereits eine Änderung auf Freigabe: die offene neue Version
  oder Beendigung zuerst entscheiden.
- Diese IBAN ist beim Kontakt bereits hinterlegt: vorhandene Bankverbindung verwenden.
- Bankverbindung ist bereits beendet: beendete oder abgelehnte Bankverbindungen sind nicht
  änderbar, neue Bankverbindung hinzufügen.
- Lastschrift nutzt die neue IBAN nicht: Freigabe fehlt.
- IBAN aus KI-Vorschlag übernommen: KI-Vorschläge enthalten nie eine Übernahme von Bankdaten.

## Lücken in der Software

- Angebundene Bankkonten der Rechtsträger (Zuordnung, Standardkonto) ohne Vier-Augen-Freigabe
  in der Software (`docs/OPEN_QUESTIONS.md` M5-04).
- Kein Feld für den Rückfragevermerk an der Bankverbindung selbst (Vermerk nur beim Mandat und
  bei der Beendigung); Rückfrage bis dahin als Ticket oder Notiz am Kontakt ohne IBAN.

Geschlossen am 28.09.2026: Oberfläche zum Hinzufügen, Ändern und Beenden am bestehenden
Kontakt; Vier-Augen-Freigabe für Bankverbindungen der Rechtsträger-Kontakte; Systemrolle
Freigabe.
