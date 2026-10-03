# ADR 0031: Mandantenschalter als Muster für offene Rechtsentscheidungen

- Status: Accepted
- Date: 2026-10-02

## Context

Mehrere Funktionen hängen an Entscheidungen, die weder Entwicklung noch Plattform treffen darf (Rechtslage, Steuer, Datenschutz, Haftung). CLAUDE.md Regel 3 verbietet erfundene Rechtsregeln und verlangt, dass offene Fragen in `docs/OPEN_QUESTIONS.md` stehen und die betroffene Aktion gesperrt bleibt. Bisher fehlte ein dokumentiertes Muster dafür (Befund GAI-516).

## Decision

Eine offene Entscheidung wird als Mandantenschalter mit konservativem Standard umgesetzt: aus, nichts bucht, nichts versendet, nichts löscht. Belege im Code:

1. Zweiter Faktor zurücksetzen: Schalter `mfa_admin_reset_enabled`, eigene Tabelle `auth_mfa_reset_setting`, Eintrag fehlt bedeutet aus (`core/auth/mfa_reset.py:48`, `:53`). Bei aus antworten Antrag und Freigabe mit `MHVP-AUTH-0016`.
2. Zinstagemethode im Mahnwesen: Schlüssel `dunning_interest_day_count` in `tenant_settings.sources`, unbekannte Werte fallen auf `act_365_fixed` zurück (`accounting/dunning.py:278` bis `:296`, Router `accounting/dunning_interest_routers.py`).
3. Webhook-Abschaltung: Spalte `tenant_settings.webhook_auto_disable_after` mit Check 1 bis 100, leer bedeutet aus (`platform/models.py:531`, `core/webhooks.py:405` ff.).

Regeln des Musters:

- Der Standard ist die Variante, die nichts Rechtsverbindliches auslöst. Die Empfehlung aus der Entscheidungsvorlage wird nur dann Standard, wenn sie nichts bucht, versendet oder löscht.
- Der Schalter wird vom berechtigten Mandantenrecht gesetzt, die Änderung wird als Ereignis protokolliert, vorher und nachher.
- Die Frage bleibt in `docs/OPEN_QUESTIONS.md` offen (Eigentümer, betroffenes Gate) mit dem Vermerk "technisch vorbereitet".
- Neue Schalter erscheinen in `apps/web-crm/src/lib/business-rules.ts` und in der Einstellungssuche.
- Ein Schalter ersetzt keine gültige Rechtsregel (CLAUDE.md Regel 3) und öffnet kein Gate (G1 bis G5 bleiben je Mandant geschlossen).

## Consequences

- Entscheidungen können nach Freigabe ohne Codeänderung aktiviert werden; der Rückbau ist das Ausschalten.
- Jede Variante braucht Tests für aus, an und Mandantentrennung.
- Viele Schalter erhöhen den Prüfaufwand; die Registry der Seite Fachliche Regeln hält sie auffindbar.

## Alternatives considered

- Umgebungsvariable je Installation: nicht je Mandant steuerbar, kein Audit.
- Feste Voreinstellung im Code: würde eine ungeklärte Rechtsfrage stillschweigend entscheiden.

## References

- `docs/OPEN_QUESTIONS.md` (AI07-02, AI09-01); CLAUDE.md Regel 3 und Abschnitt 14
