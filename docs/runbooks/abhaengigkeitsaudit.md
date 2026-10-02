# Runbook: Abhängigkeitsaudit in der CI

Stand: 02.10.2026. Beleg: GAH-310, `.github/workflows/ci.yml` (Job `dependency-audit`), `scripts/dependency_audit.py`, `.github/audit-allowlist.txt`.

## Ablauf

1. Der Job `dependency-audit` läuft vor dem Image-Build (`needs` des Build-Jobs). Er startet `python3 scripts/dependency_audit.py`.
2. Python: `uv export --locked` aus `apps/api/uv.lock`, danach `uvx pip-audit` auf der exportierten Liste. Frontend: `pnpm audit --prod` auf `pnpm-lock.yaml`.
3. Ein Werkzeug- oder Netzfehler (Auditdienst nicht erreichbar) ist nur eine Warnung. Ein Befund, der nicht auf der Ausnahmeliste steht, beendet den Lauf mit Exit 1.

## Umgang mit einem Befund

1. Befund lesen: Paket, Version, Kennung (GHSA, CVE, PYSEC).
2. Bevorzugt aktualisieren: Abhängigkeit in `apps/api/pyproject.toml` oder `package.json` anpassen, Lockfile neu erzeugen, Tests laufen lassen. Aktualisierung nur mit grüner CI (ADR 0001, Punkt 2).
3. Ist keine fixende Version verfügbar oder nicht kompatibel, kann der Betreiber eine befristete Ausnahme eintragen. Ein Eintrag je Zeile in `.github/audit-allowlist.txt`: Kennung, dann ` # Grund, Verantwortlicher, Prüfdatum TT.MM.JJJJ`. Eine Ausnahme ist eine Risikoentscheidung des Betreibers, kein Dauerzustand.
4. Zum Prüfdatum erneut prüfen: Gibt es ein Update, Eintrag entfernen. Sonst Frist mit Begründung verlängern.

## Offene Ausnahme

`PYSEC-2026-4141` (pyjwt 2.14.0), eingetragen am 02.10.2026, Bewertung und Update durch den Betreiber offen (OPEN_QUESTIONS AI12-02). Prüftermin bis 16.10.2026. Eintragung mit Vorfrist (zum Beispiel 09.10.2026) im Kalender wird empfohlen.

## Lokal prüfen

```sh
python3 scripts/dependency_audit.py
```

Voraussetzung: `uv`, `pnpm` und Netzzugang. Ohne Netz meldet das Skript eine Warnung statt eines Befunds.
