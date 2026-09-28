# A80-01 Zuordnungsprüfung: sichere Kette vom Kontakt zu Einheit und Objekt

| Field | Content |
| --- | --- |
| ID | `A80-01` (Zuordnungskette; die Rückfrage selbst steht in `docs/ASSUMPTIONS.md` A-068) |
| Title | Ist der Kontakt einer Mail oder eines Tickets sicher (automatisch oder durch ein Ja bestätigt) und hat er genau einen aktiven Mietvertrag oder genau eine aktive Eigentümerschaft einer Einheit, werden Einheit und Objekt automatisch übernommen, nur in ein leeres Feld. Mehrere Verträge oder Einheiten bleiben eine Rückfrage mit diesen Kandidaten; ein unsicherer Kontakt leitet nichts ab |
| Scope | `mhvp.communication.assignment` (`contact_sure_chain`) und `mhvp.communication.assignment_review` (`evaluate`; seit 28.09.2026 auch `apply_rule_assignment` über `_rule_contact_chain`), Mails (`Message.property_id`) und Tickets (`Ticket.property_id`, `Ticket.unit_id`); keine Geldwirkung, keine Rechtsgrundlage, reine Produktschutzregel gegen unnötige Rückfragen bei eindeutiger Lage |
| Source status | Kein Anhang-C-Eintrag nötig (organisatorische Regel ohne Rechtsbezug). Betreiberauftrag 27.09.2026 (Nachtrag zu A-068) |
| Acceptance case | Keiner in Anhang D. Tests `apps/api/tests/integration/test_a80_assignment_chain.py` (ein Mietvertrag, eine Eigentümerschaft, zwei Verträge bleiben Rückfrage, unsicherer Kontakt ohne Ableitung, bereits gesetztes Feld bleibt unverändert, erneute Prüfung nach Ja, Ereignis `assignment_review.auto`); `apps/api/tests/integration/test_a80_rule_assignment_chain.py` (Regel 6: Kontaktregel mit Kette an Ticket und Mail, zwei Verträge, gesetztes oder entschiedenes Feld, Mandantentrennung); bestehende `test_a80_assignment_review.py` unverändert grün |
| Implementation | Version 1.37.0, kein Migrationsbedarf (nutzt bestehende Tabellen `contract`, `assignment_review`); Regel 6 seit 28.09.2026 ohne Migration |
| Change reason | Betreiberauftrag 27.09.2026: Mails und Tickets sollen so weit wie möglich automatisch mit Mieter, Eigentümer, Einheit und Objekt verknüpft werden, ohne die bestehenden Sicherheitsregeln der Zuordnungsprüfung (A-068) zu lockern. Nacharbeit 28.09.2026 (Regel 6): Setzt eine angenommene Lernregel (M9-11) den Kontakt, blieben Objekt und Einheit bisher leer, weil die Regel-Engine nur eine Stufe ausführt; die Kette wird jetzt direkt im Anschluss angewendet |

## Regel

1. **Voraussetzung Kontakt sicher.** Der Kontakt gilt als sicher, wenn die laufende Prüfung ihn
   als `sure` einstuft (eindeutige Absenderadresse) oder eine frühere Rückfrage bereits mit Ja
   bestätigt wurde (`assignment_review.status` `accepted` oder zuvor gespeichert `auto`) und das
   Feld weiterhin diesen Kontakt trägt. Ein unsicherer oder noch offener Kontakt leitet nie
   Objekt oder Einheit ab (unverändert zu A-068).
2. **Eindeutiger Vertrag oder eindeutiges Eigentum.** `contact_sure_chain` liest die aktiven
   Verträge des Kontakts (`Contract` über `PartyMember`, `end_date` leer oder nicht vor dem
   Stichtag). Genau ein aktiver Mietvertrag ergibt dessen Einheit und Objekt (Grund
   "eindeutiger Vertrag"); genau eine aktive Eigentümerschaft einer Einheit ergibt ihre Einheit
   und ihr Objekt (Grund "eindeutiges Eigentum"). Treffen beide Fälle auf verschiedene Einheiten
   zu, oder liegen mehrere Verträge je Art vor, bleibt es bei der bestehenden Rückfrage mit allen
   Kandidaten (keine automatische Übernahme).
3. **Nur ein leeres Feld.** Die automatische Übernahme setzt Objekt und Einheit nur, wenn das
   jeweilige Feld noch leer ist. Ein bereits (manuell oder anders) gesetztes Feld bleibt
   unangetastet, auch wenn die Kette eine andere Einheit ergäbe; die Zuordnungsprüfung zeigt es
   dann als gewohnte Rückfrage oder `preset`. Trägt das Feld bereits genau den Wert der Kette
   (zum Beispiel von der Mail an das daraus erzeugte Ticket vererbt), bestätigt die Prüfung ihn
   erneut als `auto` mit demselben Grund, statt ihn als schwächeres `preset` auszuweisen.
4. **Erneute Prüfung nach Ja.** Bestätigt ein Mitglied die Kontakt-Rückfrage mit Ja, prüft die
   bestehende Nachprüfung von Objekt und Einheit (`decide`) die Kette erneut; hat der nun
   bestätigte Kontakt genau einen aktiven Vertrag oder eine Eigentümerschaft, wird dieser sofort
   übernommen.
5. **Protokoll unverändert.** Jede gespeicherte automatische Übernahme schreibt wie bisher genau
   einmal das Ereignis `assignment_review.auto` mit `dimension`, `chosen_id` und `reason`
   ("eindeutiger Vertrag" / "eindeutiges Eigentum"), bei Tickets zusätzlich einen Ticketverlaufs-
   eintrag (unverändert zu A-068).
6. **Kontakt durch eine Lernregel (28.09.2026).** Setzt eine angenommene Lernregel (M9-11,
   Aktion `assign_record`, Dimension Kontakt) den Kontakt, wendet `apply_rule_assignment` im
   selben Schritt dieselbe Kette an (`contact_sure_chain`), ohne die Tiefe der Regel-Engine zu
   erhöhen. Objekt und Einheit werden nur in ein leeres Feld übernommen, für das kein Mitglied
   in der Zuordnungsprüfung entschieden hat; die Einheit nur, wenn das Objekt der Kette
   entspricht (ein anders gesetztes Objekt lässt die Einheit leer). Die Zeile lautet `auto`
   mit dem Grund der Kette, das Ereignis `assignment_review.auto` trägt zusätzlich `rule_id`
   und das Kennzeichen `automation` (löst keine weitere Regel aus). Mehrere Verträge oder
   Einheiten ändern nichts; eine offene Rückfrage bleibt offen. Das Ergebnis im Regelprotokoll
   nennt die ergänzten Dimensionen.
