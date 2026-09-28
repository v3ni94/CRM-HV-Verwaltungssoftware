# Handlungsanweisung: Eigentümerwechsel

Stand: 28.09.2026. Gilt für WEG-Objekte (Vertragsart Eigentum) und für Objekte der
Verwaltungsart WEG mit SEV. Erfassungsregeln: [Erfassungsstandards](erfassungsstandards.md).

## Zweck

Ein Sondereigentum geht auf einen neuen Eigentümer über (Kauf, Ersterwerb, Erbfolge,
Zwangsversteigerung, Schenkung, Sonstiges). Das bisherige Eigentumsverhältnis wird beendet, das
neue angelegt, der Erwerber erhält ein eigenes Debitorenkonto; alte offene Posten bleiben beim
Veräußerer (Master-Prompt 6.9.2, Fall D15). Eine Umschreibung alter Rückstände auf den Erwerber
nimmt die Software nicht vor.

## Wann anwenden

- Mitteilung über einen Verkauf, Grundbuchauszug mit Eigentumsumschreibung, Erbschein,
  Zuschlagsbeschluss.
- Nicht anwenden bei reinen Namens- oder Anschriftänderungen desselben Eigentümers (dann
  [Stammdaten](anleitung-stammdaten.md)) und nicht bei Mieterwechseln
  ([Mieterwechsel](anleitung-mieterwechsel.md)).

## Rechtliche Voraussetzungen

Rechtlich zu prüfen durch Rechtsanwalt: [Platzhalter] Welcher Stichtag für Rechte und Pflichten
gegenüber der Gemeinschaft maßgeblich ist (Eigentumsübergang laut Grundbuch oder Nutzen und
Lasten laut Kaufvertrag), wer Schuldner laufender Hausgelder und der späteren
Abrechnungsspitze ist, ob eine Sonderrechtsnachfolge mit Haftung für Rückstände vorliegt,
Behandlung von Erbfall und Zwangsversteigerung, Zustimmungserfordernisse nach der
Gemeinschaftsordnung.

Stand der Regeln: Der Master-Prompt beschreibt in Regel W07 (Abschnitt 7) die fachliche
Trennung von Eigentumsübergang, Nutzen und Lasten, Vorschussschuldner und Anspruchsinhaber der
Abrechnung. Die Regel ist fachlich freizugeben; der Rechtsprechungsabgleich ist offener
Freigabepunkt P01. In `docs/rules/` gibt es dazu keine freigegebene Regeldatei. Bis dahin
keine Aufteilung von Beträgen zwischen Veräußerer und Erwerber nach eigener Annahme vornehmen.

## Voraussetzungen im CRM

- Recht `contracts:update` für den Eigentümerwechsel, `contacts:create` für den Erwerber.
- Freigabestufe G4 (WEG-Abrechnung) bleibt geschlossen; der Wechsel erzeugt keine rechtlich
  maßgebliche Abrechnung.
- Nachweis liegt vor (Grundbuchauszug, Notarmitteilung, Erbschein oder Zuschlag).

## Ablauf in der Software

### 1. Unterlagen ablegen

Verwaltung, DMS, Suche im Archiv, Abschnitt Dokument hochladen: Objekt und Einheit wählen,
Titel zum Beispiel `Eigentümerwechsel WE 07, Grundbuchauszug, 15.09.2026`. Ablage in
05 Eigentümerakte, Ausweis- und Vollmachtsunterlagen in 01 Legitimationsunterlagen (siehe
[Objektordner](anleitung-objektordner.md)).

### 2. Erwerber als Kontakt anlegen

Übersicht, Kontakte, Kontakt anlegen. Rolle Eigentümer. Vorher über die Suche (`Strg+K`)
prüfen, ob der Erwerber bereits existiert (zum Beispiel als Eigentümer einer anderen Einheit).
Bei mehreren Erwerbern je Person ein Kontakt; Bevollmächtigte im Abschnitt Bevollmächtigte und
Zustellregel des Kontakts hinterlegen.

### 3. Eigentümerwechsel erfassen

Auf der Vertragsseite des bisherigen Eigentums (Verträge, Vertrag öffnen) oder auf der
Einheitenseite (Vermietung, Einheit) im Abschnitt Eigentümerwechsel auf Eigentümerwechsel
erfassen klicken. Der Abschnitt erscheint nur bei offenen Eigentumsverhältnissen und nur mit
dem Recht `contracts:update`. Der Dialog fragt ab:

| Feld | Bedeutung |
| --- | --- |
| Erwerber | Kontakt suchen oder über Neuen Kontakt anlegen als Person oder Unternehmen anlegen; die Vertragspartei wird automatisch ermittelt oder angelegt |
| Eigentumsübergang (Grundbuch) | Pflicht; muss nach dem Beginn des bisherigen Eigentums liegen |
| Nutzen und Lasten | optional, laut Kaufvertrag, nicht nach dem Eigentumsübergang |
| Erwerbsart | Kauf, Ersterwerb, Erbfolge, Zwangsversteigerung, Schenkung, Sonstiges |
| Sollbeträge übernehmen | Standard an: die am Übergang gültigen Zahlungen (Hausgeld, Rücklage), der Zahlungsplan und die Umlagewerte werden ab dem Übergang unverändert auf den neuen Vertrag kopiert |
| Sonderrechtsnachfolge | Kennzeichen, rechtlich zu prüfen |
| SEV | nur bei Verwaltungsart WEG mit SEV wählbar, vorbelegt aus dem bisherigen Eigentum |
| Nachweis | Datei (Grundbuchauszug, Notarmitteilung, Erbschein); wird mit Einheit und neuem Vertrag verknüpft |
| Notiz | Text zum neuen Vertrag, zum Beispiel Urkundennummer |

Vorschau zeigt vor der Bestätigung: das bisherige Eigentum endet am Vortag, das neue beginnt
am Übergang, offene Posten bleiben beim Veräußerer, und welche Beträge ab dem Übergang
übernommen werden. Die Vorschau ändert nichts. Eigentümerwechsel erfassen führt den Wechsel
aus und öffnet den neuen Vertrag.

Die Schnittstelle `POST /api/v1/contracts/{id}/ownership-transfer` (Felder `new_party_id`
oder `new_contact_id`, `title_transfer_date`, `benefit_burden_date`, `acquisition_kind`,
`special_succession_liability`, `sev_enabled`, `carry_over_amounts`, `notes`, `document_id`)
und die Vorschau `GET /api/v1/contracts/{id}/ownership-transfer/preview` bleiben für
Integrationen verfügbar.

Kein Ersatzweg über Vertrag anlegen: Ein zweites Eigentum für dieselbe Einheit, solange das
bisherige offen ist, lehnt die Plattform ab (überlappende Eigentumszeiträume sind durch die
Datenbank ausgeschlossen, Master-Prompt 6.9.2). Den Wechsel deshalb nicht über ein neues
Vertragsformular nachbilden.

### 4. Hausgeld und Zahlungsplan am neuen Vertrag prüfen

Mit Sollbeträge übernehmen trägt der neue Vertrag Hausgeld, Erhaltungsrücklage, Zahlungsplan
und Umlagewerte in der am Übergang gültigen Höhe. Das ist eine Datenübernahme, keine
Aussage darüber, wer welche Vorschüsse schuldet (siehe Rechtliche Voraussetzungen). Sieht der
beschlossene Wirtschaftsplan andere Beträge vor, diese am neuen Vertrag erfassen (Kapitel
[WEG](weg.md), Vorschüsse übernehmen, oder Schnittstelle). Wurde die Übernahme abgewählt,
sind die Beträge am neuen Vertrag anzulegen. Solange G1 geschlossen ist, entstehen daraus
keine produktiven Buchungen.

### 5. SEPA-Mandat und Bankverbindung

Mandate des Veräußerers gelten nicht für den Erwerber. Neues Mandat und Bankverbindung beim
Erwerber erfassen, siehe [Bankverbindung](anleitung-bankverbindung.md); Freigabe durch eine
zweite Person.

### 6. Portal und Kommunikation

- Portalzugang des Veräußerers prüfen (Kontakt, Reiter Kommunikation, Abschnitt
  Portalzugang); Einladung für den Erwerber dort erzeugen.
- Bei SEV: Mietverträge der Einheit laufen auf den SEV-Eigentümer als Vermieter. Wie Mieter zu
  informieren sind und ob Verträge anzupassen sind, ist rechtlich zu prüfen durch Rechtsanwalt
  [Platzhalter].

### 7. Fristen und Wiedervorlagen

Kein eigener Fristtyp. Ticket zur Einheit mit Titel `Eigentümerwechsel <Einheit>` und
Fälligkeit anlegen, zum Beispiel für die Anforderung fehlender Unterlagen oder die
Nachbearbeitung der Abrechnung. Fristen mit Rechtsbezug: rechtlich zu prüfen durch Rechtsanwalt
[Platzhalter], Vorfrist mindestens 7 Tage.

## Zu verknüpfende Datensätze

| Datensatz | Was |
| --- | --- |
| Einheit | Grundbuchauszug, Kaufvertragsauszug, Erbschein |
| Vertrag (alt) | endet automatisch; keine Änderung der offenen Posten |
| Vertrag (neu) | Erwerber, Erwerbsart, Stichtage, übernommene Sollbeträge, Nachweis, Notiz |
| Kontakt Erwerber | Legitimation, Mandat, Vollmacht |
| Kontakt Veräußerer | bleibt erhalten; nicht löschen, offene Posten bleiben dort |

## Freigaben

| Schritt | Wer | Durch die Software erzwungen |
| --- | --- | --- |
| Eigentümerwechsel erfassen | Person mit `contracts:update` | Recht ja, zweite Person nein |
| Bankverbindung Erwerber | zweite Person mit `contacts:approve` | ja |
| Abweichende Stichtage, Sonderhaftung, Erbfall, Zwangsversteigerung | Geschäftsführung nach rechtlicher Prüfung | nein |

## Checkliste

- [ ] Nachweis des Eigentumsübergangs abgelegt
- [ ] Erwerber angelegt, Dublettenprüfung beachtet
- [ ] Eigentümerwechsel mit Eigentumsübergang, Nutzen und Lasten, Erwerbsart erfasst
- [ ] Sonderrechtsnachfolge geprüft und gekennzeichnet
- [ ] Sollbeträge übernommen oder am neuen Vertrag erfasst und gegen den Wirtschaftsplan geprüft
- [ ] Mandat und Bankverbindung des Erwerbers erfasst und freigegeben
- [ ] Portalzugang Veräußerer geprüft, Erwerber eingeladen
- [ ] Ticket mit Fälligkeit für Nacharbeiten angelegt
- [ ] Rechtliche Punkte geprüft

## Häufige Fehler

- Datum Nutzen und Lasten als Eigentumsübergang eingetragen.
- Rückstände des Veräußerers auf den Erwerber umgebucht.
- Veräußerer als Kontakt gelöscht oder überschrieben statt neuen Kontakt anzulegen.
- Bestehenden Eigentumsvertrag über Bearbeiten auf den Erwerber umgestellt: Vertragspartner ist
  fest und nicht änderbar.
- Mandat des Veräußerers weiter verwendet.

## Lücken in der Software

- Sollbeträge sind am Vertrag in der Oberfläche nicht direkt änderbar; abweichende Beträge nach
  dem Wechsel über WEG, Vorschüsse übernehmen oder die Schnittstelle erfassen.
- Regel W07 (Adressierung der Abrechnungsspitze, Schuldner) nicht freigegeben, P01 offen.
- Kein Fristtyp Eigentümerwechsel, keine Checkliste.
- Keine automatische Information von Beirat, Messdienstleister oder Mietern.
