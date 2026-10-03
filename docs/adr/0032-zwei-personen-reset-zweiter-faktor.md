# ADR 0032: Zwei-Personen-Reset des zweiten Faktors

- Status: Accepted, hinter Mandantenschalter (Entscheidung AI09-01 offen)
- Date: 2026-10-02

## Context

Verliert ein Mitglied seinen zweiten Faktor, braucht es einen Weg zurück in das Konto. Ein einseitiger Reset durch einen Administrator wäre ein Missbrauchs- und Übernahmerisiko. Offen ist, ob Wiederherstellungscodes, Admin-Reset oder beides gelten sollen (AI09-01).

## Decision

Variante Admin-Reset mit Vier-Augen-Prinzip (`core/auth/mfa_reset.py`):

1. Antrag und Freigabe sind getrennte Schritte (`POST /auth/mfa-reset/requests`, `.../{id}/approve`). Beide brauchen `members:update`.
2. Die freigebende Person muss eine andere sein als die antragstellende und als die betroffene (`mfa_reset.py:298`, `:300`, `MHVP-AUTH-0017`). Den eigenen Faktor kann niemand per Antrag zurücksetzen (`:215`).
3. Nur ein Antrag je Mitglied offen (`:228`); entschiedene Anträge sind nicht mehr änderbar (`MHVP-AUTH-0018`).
4. Begründung ist Pflicht (mindestens 10 Zeichen, `:104`); der Identitätsnachweis bleibt Pflicht der Administratoren, die Plattform prüft ihn nicht.
5. Erst die Freigabe wirkt: TOTP aus, Passkeys, vertraute Geräte und Refresh-Tokens widerrufen (`_reset_factors`, `:263`). Danach Anmeldung per Passwort und Neueinrichtung bei Pflicht (M2-04).
6. Ereignisse für jeden Schritt, Audit `auth.mfa_reset`, Benachrichtigung an Antragsteller und betroffene Person.
7. Standard aus (Mandantenschalter nach ADR 0031).

## Consequences

- Ein einzelner Administrator kann den Faktor nicht allein zurücksetzen; in Kleinstmandanten mit nur einer berechtigten Person gibt es keinen Notweg (Runbook `zweiter-faktor-zuruecksetzen.md`).
- Die Entscheidung über Wiederherstellungscodes bleibt offen und wird unabhängig vorbereitet.
- Sicherheitsrelevante Wirkung: Der Reset setzt das Konto auf Passwort-Niveau zurück, bis der Faktor neu eingerichtet ist.

## Alternatives considered

- Reset durch einen Administrator allein: schneller, aber ohne Kontrolle.
- Nur Wiederherstellungscodes: kein Administratoreingriff, aber Verlust der Codes bleibt ungelöst.

## References

- `docs/runbooks/zweiter-faktor-zuruecksetzen.md`; M2-04 (Neueinrichtung)
