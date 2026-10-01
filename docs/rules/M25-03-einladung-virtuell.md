# M25-03 Einladungsfrist und virtuelle oder hybride Versammlung

Status: technisch umgesetzt am 27.09.2026, fachlich und rechtlich nicht freigegeben.
Mandanteneinstellungen `tenant_settings.hoa_invitation_weeks` (Entwurfswert 3) und
`tenant_settings.hoa_virtual_meetings_enabled` (Standard aus), Migration 0187.

## Quellenstatus (Anhang C)

Zu prüfen durch Rechtsanwalt (V13). Einschätzung ohne Gewähr: Für die Einberufung der
Eigentümerversammlung wird im WEG eine Frist von drei Wochen genannt, mit Ausnahme bei
besonderer Dringlichkeit (Verweis bisher § 24 Abs. 4 WEG, R05). Nicht geprüft sind: ob die
Frist mit Absendung oder Zugang beginnt, wie Tage gezählt werden, welche Anforderungen an die
Dringlichkeit bestehen und ob die Gemeinschaftsordnung längere Fristen vorsieht. Für die
virtuelle Versammlung geht der Betreiber davon aus, dass sie einen Beschluss der Eigentümer
voraussetzt, dessen Wirkung zeitlich begrenzt sein kann; Voraussetzungen, Mehrheit, Dauer
und die Anforderungen an Einwahl, Teilnahme und Stimmabgabe sind nicht geprüft. Das System
stellt keine Rechtslage fest; alle Werte tragen den Vermerk "zu prüfen".

## Anforderungstyp

Fachliche Umsetzung mit offener Entscheidung (Betreiber mit Rechtsberatung, betrifft G4).
Kein Geldfluss; Fristen sind Orientierung (M1-09), keine Notfristen.

## Regel (Modul `mhvp.hoa.meeting_rules`, ergänzend `mhvp.hoa.meetings`)

### Einladungsfrist

* Einstellung je Mandant `GET/PUT /hoa/meeting-settings` (`invitation_weeks` 1 bis 12,
  Standard 3; Recht `tenant_settings:*`). Änderung wird als Ereignis protokolliert.
* Spätestes Versanddatum = Versammlungstag minus Wochen; Ausgabe `latest_invitation_at` an
  jeder Versammlung (Planung im CRM) und Kalendereintrag `hoa_invitation_deadline`
  "Einladung spätestens" für geplante Versammlungen (Quelle `derived_dates` im Arbeitsplatz,
  Objektbezug über die GdWE).
* Prüfung bei `POST /hoa/meetings/{id}/invite`: liegt `invited_at` nach dem spätesten
  Versanddatum, ist die Erfassung nur mit `urgency_reason` möglich (Warnung als 422 mit
  Datum). Die Unterschreitung und der Grund werden an der Versammlung gespeichert
  (`invitation_short_notice`, `invitation_short_notice_reason`), im Detail als
  `short_notice_note` ausgegeben und im Protokollentwurf als "Vermerk zur Einladungsfrist"
  gedruckt.

### Virtuelle und hybride Versammlung

* Form am Datensatz (`mode`: presence, hybrid, virtual). Virtuell nur mit Schalter des
  Mandanten (`MHVP-HOA-0003`, 403) und mit zulassendem Beschluss derselben Gemeinschaft aus
  der Beschluss-Sammlung mit Status positiv, bestandskräftig oder rechtskräftig sowie
  eingetragenem Gültigkeitsende (`virtual_basis_valid_until`, aus dem Beschlusstext, nicht
  berechnet), das nicht vor dem Versammlungstag liegt (`MHVP-HOA-0004`, 422). Hybrid bleibt
  ohne Schalter möglich (Annahme A-061). Beschlussgrundlage an einer Präsenzversammlung ist
  unzulässig.
* Einwahldaten `PUT /hoa/meetings/{id}/dial-in` (Link, Zugangsdaten), verschlüsselt
  gespeichert, nur bei hybrider oder virtueller Form, nicht nach Abschluss. Ausgabe nur im
  Eigentümerportal `GET /portal/meetings` (Rolle owner, eigene GdWE, nach Einladung); die
  CRM-Ausgabe zeigt nur, ob Daten hinterlegt sind (`has_dial_in`). Die Einladung enthält den
  Hinweistext (`invitation_notice`), nie die Zugangsdaten.
* Teilnahmenachweis `GET /hoa/meetings/{id}/attendance-list`: je Eigentümer der Kanal
  Präsenz, online, Vollmacht oder abwesend aus der erfassten Anwesenheit; Protokollentwurf
  unterscheidet "anwesend (Präsenz)" und "anwesend (online)".

## Abnahmefall (Anhang D, Ergänzung)

Versammlung 10.12.2026, Frist 2 Wochen: spätester Versand 26.11.2026; Einladung am 30.11.2026
ohne Grund 422, mit Grund erfasst und im Protokoll vermerkt. Kalendereintrag am 26.11.2026 nur
für den eigenen Mandanten. Virtuell ohne Schalter 403, ohne Beschluss, ohne Gültigkeitsende
oder mit Gültigkeitsende vor dem Termin 422. Einwahldaten sieht der Eigentümer der GdWE im
Portal, der Mieter erhält 403, der Eigentümer eines anderen Mandanten sieht nichts
(`tests/integration/test_m25_03_meeting_invitation_virtual.py`,
`tests/unit/test_m25_meeting_rules.py`).

## Änderungsgrund

Betreiberauftrag 27.09.2026 (Masterprompt WEG-Versammlung, M25-03, V13): Einladungsfrist je
Mandant statt Konstante, virtuelle und hybride Form mit Beschlussgrundlage und Einwahldaten.

## Ergänzung AE12 (Welle 16): Stichtag Übergangsregel und Fristhinweise

- ID: M25-03 / GA07-01. Geltungsbereich: Mandanteneinstellung `hoa_virtual_basis_transition_date` (Datum, leer = nicht eingetragen) und Versammlungsdetail virtueller Versammlungen.
- Quellenstatus: Anhang C offen (AA06-02). Das Datum trägt der Betreiber ein, es ist kein Rechtstext und ändert weder Sperre noch Prüfung. Die Dreijahressperre bleibt allein am Schalter `hoa_virtual_basis_term_lock_enabled` (Standard aus).
- Verhalten: Das Versammlungsdetail liefert `virtual_basis_deadlines` (Beschlussdatum, Dreijahresgrenze, Gültigkeitsende, Resttage, Stichtag, Hinweis zum Stichtag) als Orientierung, gekennzeichnet "zu verifizieren". Der Online-Versammlungsschalter (AD06) ist in der CRM-Maske des Objekts bedienbar, Standard aus.
- Abnahmefall: tests/integration/test_ae12_virtual_transition.py. Änderungsgrund: Prioritätenliste Punkt 12.
