# Handlungsanweisung: Mieterhöhung

Stand: 28.09.2026. Gilt für Wohnraummietverträge der Mietverwaltung und der SEV.
Erfassungsregeln: [Erfassungsstandards](erfassungsstandards.md).

## Zweck

Eine Mieterhöhung wird als Mieterhöhungsfall im CRM vorbereitet, rechnerisch geprüft, von einer
zweiten Person freigegeben und nach Zustimmung in die Miethistorie übernommen. Schreiben,
Nachweise und Fristen sind am Fall und am Vertrag nachvollziehbar.

## Wann anwenden

- Anpassung an die ortsübliche Vergleichsmiete (Grundlage Mietspiegel, Vergleichswohnungen,
  Gutachten).
- Modernisierung, Index- oder Staffelmiete: im CRM als Grundlage auswählbar, aber ohne
  automatische Prüfung.

## Rechtliche Voraussetzungen

Rechtlich zu prüfen durch Rechtsanwalt: [Platzhalter] Zulässigkeit, Wartefrist, Kappungsgrenze,
Begründung, Form, Zustimmungsfrist, Wirksamkeitszeitpunkt und Klagefrist im Einzelfall.

Stand der Regeln im CRM: Die Parameter sind in `docs/rules/M26-rent-law.md` registriert
(Quellenstatus: Ergänzung zu Anhang C beantragt, Werte am Gesetzestext abgeglichen, Status
Entwurf bis zur Freigabe je Regel durch den Betreiber). Kappungsgebiete NRW sind in derselben
Regeldatei mit Quelle hinterlegt. Die Werte wirken im CRM erst, wenn sie unter Plattform,
Mietrecht: Regelwerk freigegeben sind; sonst zeigt der Fall den Hinweis Regelwerk nicht
vollständig freigegeben, keine automatische Prüfung. Die Regeldatei nennt ausdrücklich Punkte,
die nicht automatisch geprüft werden (Abschnitt Known gaps). Das Musterschreiben ist ein
Entwurf mit Platzhaltern und vor Verwendung rechtlich zu prüfen.

## Voraussetzungen im CRM

- Recht `contracts:create` zum Anlegen, `contracts:approve` für alle Prozessschritte
  (Freigeben, Versand erfassen, Zustimmung erfassen, Ablehnung erfassen, In Miethistorie
  übernehmen, Verwerfen). `contracts:approve` haben in der Vorbelegung nur
  Mandantenadministrator und Administrator.
- Am Mietvertrag ist zum Wirksamkeitsdatum eine Miete erfasst (sonst Fehlermeldung Keine Miete
  zum Stichtag erfasst). Die Miete steht auf der Vertragsseite im Abschnitt Sollbeträge
  ([Verträge](vertraege.md), Sollbeträge und Zahlungsplan).
- Keine Mieterhöhungssperre am Vertrag (Feld Mieterhöhungssperre bis).
- Freigabestufe G3 ist für Versand erfassen erforderlich und derzeit geschlossen.

## Ablauf in der Software

### 1. Fall anlegen

Verwaltung, Vermietung, Abschnitt Mieterhöhungen:

1. Mietvertrag wählen.
2. Grundlage: Mietspiegel, Vergleichswohnungen, Modernisierung, Index oder Staffel.
3. Zielmiete netto und Wirksam ab.
4. Für die Kappungsprüfung: Ausgangsmiete (Kappung), Kappungsgrenze in %; für den Vergleich:
   Vergleichsmiete je m², Quelle der Werte.
5. Begründungsmittel: Mietspiegel (Bezeichnung und Stand des Mietspiegels),
   Sachverständigengutachten (Gutachten als Dokument) oder Vergleichswohnungen (Anschrift und
   Miete je m² je Wohnung, Weitere Vergleichswohnung).
6. Anlegen und rechnerisch prüfen.

Der Fall öffnet sich unter `/vermietung/mieterhoehung/<Fall>` mit Aktuelle Miete, Erhöhung,
Obergrenze laut erfasster Kappung, Erfasste Vergleichsmiete, Prüfung nach freigegebenem
Regelwerk, Frühester Zeitpunkt nach Wartefrist und den rechnerischen Hinweisen. Status
Entwurf.

### 2. Schreiben vorbereiten

Abschnitt Schreiben (Entwurf) zeigt ein Musterschreiben mit Platzhaltern. Text auf den
Briefbogen der Hausverwaltung Müller GmbH übernehmen, rechtlich prüfen lassen, das Ergebnis der
Prüfung als Dokument hochladen (Verwaltung, DMS, Suche im Archiv, Dokument hochladen mit
Einheit; Titel zum Beispiel `Mieterhöhung WE 03, rechtliche Prüfung, 20.09.2026`).

### 3. Freigeben (zweite Person)

Eine andere Person als die Anlegende klickt Freigeben (zweite Person). Die Plattform lehnt die
Freigabe ab, wenn die Prüfung offene Hinweise hat oder dieselbe Person freigibt. Status
freigegeben.

### 4. Versand erfassen

Versand erfassen verlangt die Auswahl der Dokumentierten rechtlichen Prüfung des Schreibens.
Der Schritt ist gesperrt, solange G3 geschlossen ist. Bis dahin:

- Den Versand außerhalb der Software nur nach Freigabe durch die Geschäftsführung vornehmen.
- Auf der Fallseite im Abschnitt Zugangsdatum den Zugang des Schreibens beim Mieter erfassen
  (Recht `contracts:approve`). Der Status des Falls ändert sich nicht; erst mit freigegebenem
  Regelwerk zeigt der Fall daraus abgeleitete Hinweise.
- Versandweg und Zugangsnachweis im Ticket zur Einheit festhalten und den Zugangsnachweis als
  Dokument ablegen (04 Mieterakte).

### 5. Zustimmung oder Ablehnung

Nach Versand im CRM: Zustimmung erfassen mit Nachweis der Zustimmung (Dokument) oder Ablehnung
erfassen. Bei Ablehnung Vorgang an die Geschäftsführung und den Rechtsanwalt; Frist für
weitere Schritte rechtlich zu prüfen durch Rechtsanwalt [Platzhalter].

### 6. In Miethistorie übernehmen

In Miethistorie übernehmen legt ab Wirksam ab eine neue Mietzeile mit Grund Erhöhung an und
verknüpft den Zustimmungsnachweis. Die Plattform bricht ab, wenn sich die Miete seit Anlage des
Falls geändert hat. Status übernommen.

### 7. Verwerfen

Fälle im Status Entwurf oder freigegeben lassen sich verwerfen. Verworfene Fälle bleiben
sichtbar.

## Zu verknüpfende Datensätze

| Datensatz | Was |
| --- | --- |
| Vertrag | Mieterhöhungsfall, neue Mietzeile |
| Einheit | Schreiben, rechtliche Prüfung, Zugangsnachweis, Zustimmung (Dokumente mit Einheit) |
| Kontakt Mieter | Ticket, Korrespondenz |

## Fristen

Auf der Fallseite, Abschnitt Fristen, Frist anlegen: Fristtyp Mieterhöhung (Auslöser Zugang
des Mieterhöhungsschreibens) ist vorbelegt, das Auslösedatum wird aus dem Zugangsdatum
übernommen. Fälligkeit aus der Dauer des Fristtyps (Einstellungen, Fristtypen, zu verifizieren)
oder eintragen, verantwortliche Person wählen. Die Frist erscheint in Übersicht, Fristen und im
Kalender.

- Die Zustimmungsfrist ist rechtlich zu prüfen durch Rechtsanwalt [Platzhalter]; die Software
  gibt keine Dauer vor.
- Kalendertermin für die Wiedervorlage vor dem Wirksamkeitstermin.
- Frühester Zeitpunkt nach Wartefrist aus dem Fall ist Orientierung und zu prüfen.

## Freigaben

| Schritt | Wer | Durch die Software erzwungen |
| --- | --- | --- |
| Freigeben | zweite Person mit `contracts:approve` | ja, Vier-Augen-Prinzip |
| Versand | Geschäftsführung, nach rechtlicher Prüfung | ja, G3 und Nachweis erforderlich |
| Zustimmung, Übernahme | Person mit `contracts:approve` | Recht ja, zweite Person nein |
| Regelwerk freigeben | Betreiber als Plattformadministrator | ja |

## Checkliste

- [ ] Miete zum Stichtag am Vertrag erfasst, keine Sperre
- [ ] Fall mit Grundlage und Begründungsmittel angelegt
- [ ] Rechnerische Hinweise geklärt
- [ ] Schreiben rechtlich geprüft, Prüfung abgelegt
- [ ] Freigabe durch zweite Person
- [ ] Versand nach Freigabe der Geschäftsführung, Zugangsnachweis abgelegt
- [ ] Zugangsdatum erfasst, Frist Mieterhöhung mit Verantwortlichem angelegt
- [ ] Zustimmung oder Ablehnung erfasst
- [ ] Neue Miete übernommen, Mieter informiert über geänderten Zahlbetrag

## Häufige Fehler

- Fall für einen Eigentumsvertrag: nur für Mietverträge möglich.
- Freigabe durch die anlegende Person: wird abgelehnt.
- Musterschreiben ohne rechtliche Prüfung versandt.
- Erhöhung parallel in Immoware24 und im CRM erfasst, ohne Abgleich.
- Grundlage Modernisierung, Index oder Staffel gewählt und automatische Prüfung erwartet.

## Lücken in der Software

- Versand erfassen bis G3 gesperrt; die Schritte Zustimmung und Übernahme des Falls sind damit
  im CRM nicht erreichbar. Die neue Miete lässt sich nach Zustimmung des Mieters von Hand auf
  der Vertragsseite im Abschnitt Sollbeträge als neuer Stand ab Wirksam ab mit Grund Erhöhung
  erfassen (Zustimmungsnachweis als Dokument zur Einheit ablegen); der Fall selbst bleibt im
  Status freigegeben und wird nicht automatisch abgeglichen. Parallel im führenden System
  pflegen, solange der Parallelbetrieb läuft.
- Dauer des Fristtyps Mieterhöhung noch nicht hinterlegt (WS-01-Q1); bis dahin Fälligkeit je
  Frist eintragen.
- Musterschreiben ohne Briefbogen-PDF.
- Keine automatische Prüfung für Modernisierung, Index- und Staffelmiete.
- Regelwerk wirkt erst nach Freigabe je Regel durch den Betreiber; laut Regeldatei bis dahin
  Entwurf. Den aktuellen Status zeigt System, Plattform, Mietrecht: Regelwerk.
