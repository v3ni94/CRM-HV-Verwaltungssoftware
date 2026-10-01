# AD06: Online-Versammlung im Eigentümerportal (technisch vorbereitet)

- **ID:** AD06
- **Geltungsbereich:** Eigentümerversammlung (`mhvp.hoa.online_meeting`, `mhvp.hoa.meetings`), Eigentümerportal (`mhvp.portal.owner_meetings`), Portalseite Versammlungen, CRM Versammlungsseite
- **Anforderungstyp:** Fachliche Umsetzung (Abschnitt 14, Eigentümer Phase 4), Produktschutz (Schalter, Gate), Offene Entscheidung (Zulässigkeit, AD06-01 bis AD06-03)
- **Quellenstatus (Anhang C):** keine neue Rechtsregel. Die bestehenden Regeln zu Vollmacht in Textform (R05), Stimmkanal (GA03-04), virtueller Form (V13, M25-03, GA07-01) gelten unverändert. Die Zulässigkeit einer rein virtuellen Versammlung prüft dieses Modul nicht.
- **Abnahmefall:** Anhang D, WEG-Versammlung (Stimmabgabe je Einheit, Verkündung); kein eigener Fall für die Online-Teilnahme, Abnahme durch den Betreiber
- **Gate:** G4 (geschlossen) für Vollmacht und Stimmabgabe im Portal; Mandantenschalter `hoa_online_meeting_setting.enabled` (Standard aus) für alle Portalschritte
- **Offene Fragen:** AD06-01 bis AD06-03
- **Änderungsgrund:** Befund GA11-03, Welle 15, Stand 01.10.2026

## Regeln

| Nr. | Regel | Prüfung |
| --- | --- | --- |
| 1 | Alle Portalschritte (Zusage, Wortmeldung, Vollmacht, Widerruf, Stimme) brauchen den Mandantenschalter; aus ergibt 403 MHVP-HOA-0031. Das CRM öffnet oder schließt die Abstimmung ebenfalls nur bei eingeschaltetem Schalter. | API |
| 2 | Vollmacht erteilen und online abstimmen sind rechtlich wirksame Schritte und brauchen zusätzlich G4 (403 MHVP-GATE). Der Widerruf ist immer möglich. | API |
| 3 | Online-Teilnahme nur bei hybrider oder virtueller Form und Status eingeladen oder durchgeführt. | API |
| 4 | Zusage: Anwesenheit mit Kanal online je eigener Einheit, Zeitpunkt `portal_confirmed_at`. Die tatsächliche Anwesenheit bestätigt weiter die Verwaltung. | API |
| 5 | Vollmacht: für eine eigene Einheit, an eine Einheit eines anderen Eigentümers derselben GdWE oder an die Verwaltung, mit Zeitraum (ab, optional bis) und Vollmachtsdokument als eigener Portal-Upload (R05 Textform als Nachweis). Nie gelöscht, Widerruf mit Zeitpunkt. | API |
| 6 | Stimme: eine je Einheit und TOP (zweite Stimme 409), Kanal online, nur solange der TOP geöffnet ist (sonst 409), nur nach eigener Zusage, für eigene Einheiten und Einheiten mit wirksamer Vollmacht an eine eigene Einheit am Versammlungstag. Gesperrt bei Störung, Abschluss, verkündetem, vertagtem oder ohne Abstimmung geführtem TOP. | API |
| 7 | Ergebnis im Portal erst nach der Verkündung; vorher nur, ob die eigenen Einheiten abgestimmt haben. Keine laufende Zählung. | API, Portal |
| 8 | Video über den von der Verwaltung hinterlegten externen Konferenzlink (`dial_in_url`); kein eigener Videostack. | Portal |
| 9 | Wortmeldung mit Zeitstempel, eine offene je Konto, im CRM als erledigt oder zurückgezogen abgearbeitet. | API, CRM |
| 10 | Andere Eigentümer erscheinen im Portal nur mit Einheitennummer, ohne Namen (Datenminimierung). | Portal |

## Nicht entschieden

Zulässigkeit der rein virtuellen Versammlung und der Beschlussgrundlage (GA07-01, V13), Wirkung einer Portalerklärung als Textform, Verhältnis von Vollmacht und persönlicher Stimmabgabe des Vollmachtgebers, Ausübung einer Verwaltervollmacht (im CRM über die bestehende Anwesenheit mit Vollmacht). Siehe AD06-01 bis AD06-03.

## Tests

`apps/api/tests/integration/test_ad06_online_meeting.py`, `apps/web-portal/src/components/portal/OnlineMeetingPanel.test.tsx`, `apps/web-crm/src/components/hoa/OnlineParticipation.test.tsx`.
