# Runbook: Content Security Policy mit Nonce (CRM und Portal)

Stand: 02.10.2026. Beleg: GAH-303, `apps/web-crm/src/lib/csp.ts`, `apps/web-crm/src/middleware.ts`, `apps/web-portal/src/middleware.ts`, ADR 0027.

## Mechanik

1. Die Middleware beider Next-Apps erzeugt je Anfrage einen Nonce (`createNonce`, 16 Zufallsbytes, Base64) und baut daraus die Richtlinie (`buildCsp`).
2. Nonce und Richtlinie gehen als Request-Header an das Rendering (`x-nonce`, `Content-Security-Policy`) und als Antwort-Header an den Browser (`middleware.ts`, Funktionen `middleware` und `forward`).
3. Next 15 liest den Nonce aus dem Request-Header und versieht eigene Inline-Skripte damit. Das Root-Layout liest `x-nonce` für das Theme-Skript. Eigene Inline-Skripte brauchen den Nonce aus `headers()`.
4. Folge: Jede Seite wird dynamisch gerendert, statische Auslieferung der HTML-Seiten entfällt.

## Richtlinie

| Direktive | Wert | Begründung |
| --- | --- | --- |
| `script-src` | `'self' 'nonce-...' 'strict-dynamic'`, kein `unsafe-inline` | Nur Skripte mit Nonce und von diesen nachgeladene Chunks laufen. |
| `style-src` | `'self' 'unsafe-inline'` | React `style`-Props, `next/font` und Tailwind-Laufzeitklassen erzeugen Inline-Stile ohne Nonce. Stil-Injektion ist kein Skriptausführungspfad (Kommentar in `csp.ts`). |
| `default-src`, `img-src`, `font-src`, `connect-src` | `'self'`, bei Bild und Schrift zusätzlich `data:` (Bild auch `blob:`) | Keine Fremdhosts. |
| `frame-ancestors`, `object-src` | `'none'` | Kein Einbetten, keine Plugins. |
| `base-uri`, `form-action` | `'self'` | |

Nur im Entwicklungsmodus kommen `'unsafe-eval'` (React-Entwicklungswerkzeuge, Fast Refresh) und `ws:`/`wss:` hinzu.

## Fehlersuche bei blockierten Skripten

1. Browserkonsole öffnen. Eine Verletzung erscheint als "Refused to execute inline script ... Content Security Policy".
2. Prüfen, ob die Antwort den Header `Content-Security-Policy` mit `nonce-` trägt (`curl -sI <URL>`). Fehlt er, greift der Matcher der Middleware nicht (statische Dateien sind bewusst ausgenommen, `config.matcher`).
3. Prüfen, ob Nonce im Header und im `nonce`-Attribut des Skripts übereinstimmen. Ein Zwischenspeicher (Proxy, CDN), der HTML cached, liefert einen alten Nonce: HTML nicht cachen.
4. Eigenes Inline-Skript: Nonce aus `headers()` (`NONCE_HEADER`) lesen und als `nonce` setzen. Alternativ in eine Datei auslagern.
5. Nach Änderungen an `csp.ts` den Test `apps/web-crm/src/lib/csp.test.ts` und im Portal den entsprechenden Test ausführen.

## Report-Mechanik

Im Code ist keine Berichtsadresse (`report-uri`, `report-to`) konfiguriert (Suche in `apps/web-crm/src` und `apps/web-portal/src` ohne Treffer). Verletzungen sind nur in der Browserkonsole sichtbar. Ein Sammelendpunkt ist nicht umgesetzt und wäre eine eigene Änderung mit Datenschutzprüfung.

## Prüfschritt nach Änderungen

Die Kernpfade mit Playwright (`make e2e`) im Browser durchlaufen und die Konsole auf CSP-Meldungen prüfen. Playwright wird vom Koordinator ausgeführt, in Entwicklungspaketen nicht.
