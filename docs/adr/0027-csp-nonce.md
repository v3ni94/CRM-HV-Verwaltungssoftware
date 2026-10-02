# ADR 0027: Content Security Policy mit Nonce je Anfrage

- Status: Accepted
- Date: 2026-10-02

## Context

Beide Next-Apps (CRM und Portal) lieferten Inline-Skripte aus. Eine Richtlinie mit `script-src 'unsafe-inline'` schützt nicht gegen eingeschleusten Skriptcode (Befund GAH-303, Masterprompt Kapitel 16). Nachtrag zu GAI-516.

## Decision

1. Die Middleware beider Apps erzeugt je Anfrage einen Nonce und setzt die Richtlinie als Antwort-Header und als Request-Header für das Rendering (`apps/web-crm/src/lib/csp.ts`, `apps/web-crm/src/middleware.ts`, `apps/web-portal/src/middleware.ts`).
2. `script-src` erlaubt `'self'`, den Nonce und `'strict-dynamic'`, kein `'unsafe-inline'`. `'unsafe-eval'` nur im Entwicklungsmodus.
3. `style-src` behält `'unsafe-inline'`, weil React-Style-Props, `next/font` und Tailwind-Laufzeitklassen Inline-Stile ohne Nonce erzeugen. Begründung im Kommentar von `csp.ts`.
4. Eigene Inline-Skripte nur mit Nonce aus `headers()`.

## Consequences

- Alle Seiten werden dynamisch gerendert (der Header-Zugriff macht sie dynamisch), statische HTML-Auslieferung und HTML-Caching durch Zwischenstufen entfallen.
- Inline-Stile bleiben ein bekannter Restpunkt. Eine Umstellung auf Nonce für Stile wäre mit Next und Tailwind aufwendig und ist nicht geplant.
- Es gibt keine Berichtsadresse; Verletzungen sind nur in der Browserkonsole sichtbar. Betrieb und Fehlersuche: `docs/runbooks/csp-nonce.md`.
- Ein Test sichert den Aufbau der Richtlinie (`apps/web-crm/src/lib/csp.test.ts`).

## Alternatives considered

- Hash-basierte Richtlinie: scheitert an den von Next erzeugten, wechselnden Inline-Skripten.
- `'unsafe-inline'` für Skripte: kein Schutz, verworfen.

## References

- `docs/MASTER-PROMPT.md` Kapitel 16
- `docs/runbooks/csp-nonce.md`
