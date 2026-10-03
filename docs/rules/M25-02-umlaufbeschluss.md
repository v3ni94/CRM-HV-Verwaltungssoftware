# M25-02 Umlaufbeschluss mit abgesenkter Mehrheit

Status: technisch umgesetzt am 27.09.2026, fachlich und rechtlich nicht freigegeben. Schalter je
Mandant `tenant_settings.hoa_circular_lower_majority_enabled` (Migration 0166), Standard aus.

## Quellenstatus (Anhang C)

Zu prüfen durch Rechtsanwalt. Einschätzung ohne Gewähr: Der Umlaufbeschluss verlangt nach
§ 23 Abs. 3 WEG die Zustimmung aller Wohnungseigentümer in Textform; die Eigentümer können
nach Einschätzung des Betreibers für einen einzelnen Gegenstand beschließen, dass die
Mehrheit der abgegebenen Stimmen genügt (Absenkungsbeschluss). Ob und in welchem Umfang das
gilt, welche Anforderungen an den Absenkungsbeschluss, die Frist, die Textform und die
Feststellung bestehen und wie die Gemeinschaftsordnung einwirkt, ist nicht geprüft. Das
System stellt keine Rechtslage fest; der Vermerk im Beschluss lautet ausdrücklich "zu
prüfen".

## Anforderungstyp

Fachliche Umsetzung mit offener Entscheidung (Betreiber mit Rechtsberatung, betrifft G4).
Kein Geldfluss; der Beschluss ist ein Eintrag in der Beschluss-Sammlung.

## Regel (`POST /hoa/circular-resolutions`, Modul `mhvp.hoa.meetings`)

* `allowed_majority`: `unanimous` (Standard, Verhalten wie bisher) oder `simple`.
* `simple` nur, wenn alle Bedingungen erfüllt sind, sonst Fehler mit Code:
  * Schalter des Mandanten an (`MHVP-HOA-0001`, 403).
  * `enabling_resolution_id` verweist auf einen Beschluss derselben Gemeinschaft aus der
    Beschluss-Sammlung mit Status positiv, bestandskräftig oder rechtskräftig, Datum nicht nach
    dem Umlaufbeschluss und selbst nicht mit abgesenkter Mehrheit gefasst (`MHVP-HOA-0002`,
    422). Beschlüsse anderer Mandanten sind durch RLS unsichtbar und führen zum selben Fehler.
  * `vote_deadline_at` (Fristende der Stimmabgabe) und `subject_kind` (Beschlussgegenstand
    für die Mehrheitsregel des Mandanten, M25-01) sind Pflicht.
* Zählbasis: Mehrheitsregel des Mandanten je Beschlussgegenstand (`hoa_majority_rule`,
  Override je GdWE, sonst Standardregel einfache Mehrheit nach Köpfen mit Hinweis). Köpfe:
  eine Stimme je Eigentümerperson unabhängig von der Zahl der Einheiten (wie Versammlung),
  Miteigentumsanteile: Gewicht aus dem Verteilerschlüssel MEA, Einheiten: eine Stimme je
  Einheit. Bewertung über `mhvp.hoa.majority.evaluate`; Enthaltungen zählen nicht.
* Textform-Nachweis: Gesamtnachweis `evidence_document_id` bleibt Pflicht. Je Stimme
  optional `channel` (email, portal, letter, other), `received_at` (Zeitstempel) und ein
  eigenes Dokument. Stimmen mit Eingang nach dem Fristende werden nicht gezählt und als
  verspätet vermerkt; bei Allstimmigkeit gelten sie als fehlend.
* Ergebnisfeststellung: Status positiv oder negativ, `majority_basis` mit Verweis auf den
  zulassenden Beschluss (Nr. und Datum), angewandter Regel und dem Vermerk "zu prüfen";
  `majority_check` als Protokollvermerk; `votes.protocol` (festgestellt am, durch, Ergebnis,
  Frist, zulassender Beschluss); Ereignis `resolution.circular_determined`.
* Portal: die Beschluss-Sammlung des Eigentümers zeigt das gewichtete Ergebnis. Eine
  Stimmabgabe über das Portal ist nicht umgesetzt; der Kanal `portal` dokumentiert nur eine
  außerhalb erfasste Portalabstimmung.

## Abnahmefall (Anhang D, Ergänzung)

Eigentümer A hält Einheiten 01 und 02 (MEA 400 und 300), Eigentümer B Einheit 03 (MEA 300).
Köpfe: A ja, B nein ergibt 1 : 1, abgelehnt. MEA: 700 : 300, positiv gefasst. Stimme von B
nach Fristende: nicht gezählt, verspätet 1. Ohne Schalter 403, ohne zulassenden Beschluss
422, fremder Beschluss 422 (`tests/integration/test_m25_02_circular.py`).

## Änderungsgrund

Betreiberauftrag 27.09.2026 (Masterprompt WEG-Versammlung, M25-02): Bedarf für
Umlaufbeschlüsse mit einfacher Mehrheit nach Absenkungsbeschluss.

## Nachtrag 03.10.2026 (GAM-809): Pflichtfelder des Regelformats

| Feld | Inhalt |
| --- | --- |
| ID | M25-02 |
| Geltungsbereich | Umlaufbeschlüsse der Gemeinschaft des Wohnungseigentums je Mandant, nur mit Schalter `tenant_settings.hoa_circular_lower_majority_enabled` (Standard aus) und zulassendem Beschluss; betrifft G4 |
| Quellenstatus | siehe Abschnitt Quellenstatus (Anhang C) oben: zu prüfen durch Rechtsanwalt, keine Rechtslage festgestellt |
| Abnahmefall | siehe Abschnitt Abnahmefall oben, `apps/api/tests/integration/test_m25_02_circular.py` |
| Änderungsgrund | siehe Abschnitt Änderungsgrund oben |
