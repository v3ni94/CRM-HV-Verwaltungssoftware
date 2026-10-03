# Runbook: Zweiten Faktor zurücksetzen (Admin-Reset, Vier-Augen)

Beleg: `apps/api/src/mhvp/core/auth/mfa_reset.py`, Entscheidung AI09-01, ADR 0032. Dies ist eine
technische Betriebsanleitung, keine Rechtsberatung.

## Voraussetzung

- Mandantenschalter `mfa_admin_reset_enabled`, Standard aus (`mfa_reset.py:48`, Tabelle
  `auth_mfa_reset_setting`, Migration 0442). Ist er aus, antworten Antrag und Freigabe mit
  `MHVP-AUTH-0016` (`MFA_RESET_DISABLED`) (`mfa_reset.py:220`, `:296`).
- Schalter setzen: `PUT /api/v1/auth/mfa-reset/settings` (`mfa_reset.py:162`), im CRM unter
  Einstellungen (Komponente `MfaResetAdmin.tsx`). Die Änderung braucht die Geschäftsführung.
- Zwei verschiedene Mitglieder mit dem Recht `members:update`.

## Ablauf

1. Identität prüfen. Die Plattform prüft die Person nicht; der Nachweis ist Pflicht der
   Administratoren (Rückruf unter bekannter Nummer oder persönliche Vorsprache). Das Ergebnis
   steht im Pflichtfeld `reason` (mindestens 10 Zeichen, `mfa_reset.py:104`).
2. Antragsteller: `POST /api/v1/auth/mfa-reset/requests` mit `membership_id` und `reason`.
   Abgelehnt wird der Antrag für das eigene Konto (`:215`, "Den eigenen zweiten Faktor bitte
   selbst verwalten") und bei bereits offenem Antrag (`:228`).
3. Zweite Person: `POST .../requests/{id}/approve` (oder `/reject`). Sie darf weder die
   antragstellende Person noch die betroffene Person sein (`:298`, `:300`, Code
   `MFA_RESET_FOUR_EYES`, `MHVP-AUTH-0017`).
4. Erst die Freigabe setzt zurück (`mfa_reset.py:263` und `:303`): TOTP aus und Geheimnis entfernt,
   alle Passkeys widerrufen, alle vertrauten Geräte und alle Refresh-Tokens des Benutzers
   widerrufen. Antragsteller und betroffene Person erhalten eine Benachrichtigung, das Audit
   enthält `auth.mfa_reset`.
5. Die Person meldet sich mit dem Passwort an. Verlangt die Mandantenrichtlinie einen zweiten
   Faktor, führt die Anmeldung in die Neueinrichtung (M2-04).

## Notfall ohne zweite Person

Es gibt im Code keinen Pfad, der die Vier-Augen-Regel umgeht. Ist nur ein Administrator
erreichbar, bleibt der Zugang gesperrt, bis eine zweite berechtigte Person verfügbar ist. Ein
direkter Eingriff in die Datenbank ist keine zulässige Abkürzung; er ginge am Audit vorbei und
braucht die Freigabe der Geschäftsführung und des Betreibers (Vorfall nach `incident.md`).
Offene Entscheidung: Wiederherstellungscodes als Alternative (AI09-01, `docs/OPEN_QUESTIONS.md`).

## Prüfung nach dem Reset

Antrag steht auf `approved` (`GET .../requests`), Ereignisse `auth.mfa_reset_approved`, Eintrag
`auth.mfa_reset` im Audit, Benutzer kann sich neu registrieren.
