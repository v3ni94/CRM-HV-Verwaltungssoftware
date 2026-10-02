# AE31: Vollmacht gegen eigene Stimme, Online-Daten im Protokollentwurf, Prüfpunkte zur Versammlungsform

- **ID:** AE31
- **Geltungsbereich:** Eigentümerversammlung (`mhvp.hoa.online_meeting`, `mhvp.hoa.online_rules`, `mhvp.hoa.protocol`, `mhvp.hoa.meetings` Stimmerfassung), Eigentümerportal (`mhvp.portal.owner_meetings`, Stimmabgabe), CRM Schaltermaske und Versammlungsseite
- **Anforderungstyp:** Produktschutz (konservativer Standard, Schalter), Fachliche Umsetzung (Protokollentwurf), Offene Entscheidung (Wirkung einer zweiten Stimme, Zulässigkeit der Versammlungsform, AD06-01 bis AD06-03)
- **Quellenstatus (Anhang C):** keine neue Rechtsregel. Die Regeln zu Vollmacht in Textform (R05), Stimmkanal (GA03-04) und virtueller Form (V13, M25-03, GA07-01) gelten unverändert. Dieses Modul entscheidet weder die Wirkung einer zweiten Stimme noch die Zulässigkeit der Versammlungsform.
- **Abnahmefall:** Anhang D, WEG-Versammlung (Stimmabgabe je Einheit, Verkündung); kein eigener Fall, Abnahme durch den Betreiber mit Rechtsberatung
- **Gate:** G4 (geschlossen) für Vollmacht und Stimmabgabe im Portal, unverändert; Mandantenschalter `hoa_online_meeting_setting.enabled` (Standard aus)
- **Offene Fragen:** AD06-01 bis AD06-03 (Vermerk "technisch vorbereitet (Welle 16, AE31)")
- **Änderungsgrund:** Priorität 25 des Betreibers vom 01.10.2026, Welle 16

## Regeln

| Nr. | Regel | Prüfung |
| --- | --- | --- |
| 1 | Mandantenregel `proxy_conflict_mode` für eine Einheit, die eine Stimme des Eigentümers und eine Stimme des Bevollmächtigten erhält. Standard `flag`: Die zuerst abgegebene Stimme bleibt gezählt, die zweite wird im Konfliktvorgang gespeichert und der Versammlungsleitung zur Prüfung vorgelegt. Keine Stimme wird verworfen oder automatisch geändert. | API, Unit |
| 2 | Variante `first_vote`: Die zweite Stimme für die Einheit wird abgewiesen (409), wie bisher. | API |
| 3 | Variante `proxy_priority` oder `own_priority`: Die bevorzugte Quelle ersetzt die andere Stimme, die Gegenrichtung wird abgewiesen (409). Die ersetzte Stimme bleibt mit Quelle und Wahl im Konfliktvorgang (Entscheidung `rule_second`). | API, Unit |
| 4 | Dieselbe Quelle zweimal für Einheit und TOP ist immer 409, ebenso eine Quelle, die an einem Konflikt der Einheit schon beteiligt war. Eine vom Stimmrecht ausgeschlossene Stimme bleibt unberührt (409). | API |
| 5 | Die Regel gilt für die Portalstimme und für die im CRM erfasste Stimme (Quelle Vollmacht, wenn die Anwesenheit einen Bevollmächtigten trägt). Die Auszählung (`_tally`) bleibt unverändert und zählt je Einheit eine Stimme. | API |
| 6 | Entscheidung der Versammlungsleitung (`POST /hoa/meetings/{id}/vote-conflicts/{conflict_id}/resolve`): `keep_first` bestätigt die gezählte Stimme, `apply_second` zählt die zweite Stimme, nur vor der Verkündung (sonst 409). Einmalig, mit Notiz und Zeitpunkt, beide Stimmen bleiben im Vorgang. Die Entscheidung ist haftungsrelevant und braucht die Klärung durch Rechtsberatung. | API |
| 7 | Die Übersicht `GET /hoa/meetings/{id}/online` führt Prüfpunkte zur Versammlungsform aus erfassten Angaben: Schalter, zulassender Beschluss mit Status, Gültigkeitsende, Orientierung Dreijahresgrenze, Konferenzlink. Zustände erfasst, zu prüfen, nicht erfasst, Hinweis. Sie sagt nicht, dass die Form zulässig ist. | API, Unit, CRM |
| 8 | Der Protokollentwurf enthält bei hybrider oder virtueller Form oder vorhandenen Portaldaten den Abschnitt "Online-Teilnahme" (Zusagen, Portalvollmachten, Wortmeldungen mit Zeit, Einheit und Notiz, Prüfpunkte), je TOP die online abgegebenen Stimmen mit Vollmachtsanteil und die Prüfhinweise zu Stimmkonflikten; offene Konflikte erscheinen im Entwurfshinweis. Eine Präsenzversammlung ohne Portaldaten bleibt im Wortlaut unverändert. | API (PDF) |

## Nicht entschieden

Ob die zweite Stimme gilt, welche Quelle Vorrang hat und wie die Versammlungsleitung zu entscheiden hat (AD06-02), ob die Online-Stimmabgabe bei hybrider Form ohne weiteren Beschluss zulässig ist und ob eine rein virtuelle Versammlung zulässig ist (AD06-01), Weisungen, Interessenkonflikt und Verwaltervollmacht (AD06-03). Die Varianten sind Mandantenschalter; der Betreiber wählt nach Rechtsberatung. Standard ist die Variante, die nichts verwirft.

## Tests

`apps/api/tests/unit/test_ae31_online_rules.py`, `apps/api/tests/integration/test_ae31_online_vote_rule.py`, `apps/web-crm/src/components/hoa/OnlineVoteRule.test.tsx`, `apps/web-portal/src/components/portal/OnlineMeetingPanel.test.tsx`.

## Nachtrag AF08 (Welle 17, GAE-14): Eindeutigkeit der gezählten Stimme

- Die Datenbank erlaubt je Abstimmungspunkt und Einheit genau eine gezählte Stimme
  (`uq_meeting_vote_item_contract`, Migration 0402). Konfliktvorgänge liegen in
  `meeting_vote_conflict` und bleiben unbeschränkt; der Konfliktpfad ist unverändert.
- Gleichzeitige Stimmen aus CRM und Portal: die zweite Einfügung scheitert am Index und erhält
  409; ein erneuter Versuch läuft in den Konfliktpfad.
- Die Migration prüft den Bestand vorab und bricht bei Dubletten mit Liste ab, ohne Daten zu
  löschen; die Bereinigung entscheidet die Versammlungsleitung dokumentiert.
- Quellenstatus: Produktschutz. Abnahmefall: `test_af08_unique_counted_vote_per_item_and_unit`.
