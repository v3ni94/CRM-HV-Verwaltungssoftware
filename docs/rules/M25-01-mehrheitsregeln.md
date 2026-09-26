# M25-01 Mehrheitsregeln je Beschlussgegenstand

Status: umgesetzt am 26.09.2026, Regeln fachlich freizugeben. Entscheidung des Betreibers vom
24.09.2026 (docs/OPEN_QUESTIONS.md, M25-01).

## Zweck

Die Auszählung eines Beschlusses wird automatisch gegen eine hinterlegte Mehrheitsregel
geprüft. Das Ergebnis ist nur Anzeige und Protokollvermerk. Der Beschlussstatus wird nie
automatisch geändert, die Verkündung bleibt bei der Versammlungsleitung.

## Regel (Tabelle `hoa_majority_rule`, Migration 0125, RLS je Mandant)

* `subject_kind`: economic_plan (Wirtschaftsplan), annual_statement (Jahresabrechnung),
  maintenance (Erhaltung), structural_change (bauliche Veränderung), manager_appointment
  (Verwalterbestellung), other (Sonstiges).
* `legal_entity_id` leer: Regel für alle Gemeinschaften des Mandanten; gesetzt: Override für
  eine GdWE. Der Override hat Vorrang. Je Geltung und Gegenstand ist eine aktive Regel erlaubt.
* `majority_type`: simple, qualified_2_3, qualified_3_4, unanimous, custom (mit
  `custom_numerator` und `custom_denominator`).
* `counting_basis`: heads (Köpfe), shares (Miteigentumsanteile), units (Einheiten).
* `source`: Pflicht, z. B. "Gemeinschaftsordnung § 7" oder "§ 25 Abs. 1 WEG, zu prüfen".
  Der Inhalt ist je Gemeinschaft fachlich zu prüfen; das System stellt keine Rechtslage fest.
* `approved_by`, `approved_at`: fachliche Freigabe durch eine zweite Person (nicht Anleger
  oder letzter Bearbeiter). Jede Änderung hebt die Freigabe auf. Löschen deaktiviert nur.

## Auswertung (`mhvp.hoa.majority.evaluate`)

* Einfache Mehrheit: mehr Ja als Nein.
* Qualifiziert und eigener Bruch: Ja mindestens Bruch mal (Ja plus Nein).
* Enthaltungen werden bei diesen Arten nicht gezählt. Ob dies der Regel der Gemeinschaft
  entspricht (etwa Bezug auf alle Stimmberechtigten statt auf die abgegebenen Stimmen), ist
  zu prüfen; sonst ist die Regel als eigener Bruch nicht abbildbar und bleibt manuell.
* Allstimmig: Ja gleich Gesamtzahl der Stimmberechtigten (`eligible`), kein Nein, keine
  Enthaltung. Fehlt die Gesamtzahl, lautet das Ergebnis "nicht prüfbar".
* "nicht prüfbar" außerdem bei fehlendem Beschlussgegenstand, fehlender oder unvollständiger
  Auszählung oder abweichender Zählbasis zwischen Auszählung und Regel.
* Fehlt eine Regel: Standardregel einfache Mehrheit nach Köpfen mit Hinweis
  "Standardregel, nicht fachlich freigegeben".

## Schnittstellen

* `GET|POST /api/v1/hoa/majority-rules/subject-rules`, `PUT|DELETE .../{id}`,
  `POST .../{id}/approve` (Schreiben mit accounting:approve).
* `POST /api/v1/hoa/resolutions` und `POST /api/v1/hoa/agenda/{id}/announce` nehmen
  `subject_kind` an; bei gesetztem Gegenstand wird `majority_check` gespeichert und das
  Ereignis `resolution.majority_checked` protokolliert.
* `GET /api/v1/hoa/resolutions/{id}/majority-check`: gespeicherte und aktuelle Prüfung.
* Oberfläche: Einstellungen, WEG (Tabelle der Regeln); Versammlung: Beschlussgegenstand je
  TOP wählen, Prüfergebnis nach Verkündung; Beschluss-Sammlung zeigt die Prüfung.

## Abgrenzung

Die ältere Tabelle `majority_rule` (Migration 0027, Regel je GdWE mit Bezug auf den
Tagesordnungspunkt und Vorschlag der Auszählung) bleibt unverändert bestehen.
