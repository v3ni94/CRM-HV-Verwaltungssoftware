# Interne Sicherheitspruefung, 27.09.2026 (M27-02, Vorbereitung Pentest und G5-Nachweise)

Bezug: `docs/MASTER-PROMPT.md` Kapitel 16 (Sicherheit). Diese Pruefung ist keine externe
Penetrationstestierung und keine Zertifizierung (0.2); sie bereitet die G5-Nachweise
(Drittmandanten) vor und benennt den Umfang fuer einen externen Pentest.

## 1. Abhaengigkeiten

| Werkzeug | Ergebnis |
| --- | --- |
| `uv run --with pip-audit pip-audit` (apps/api) | ausgefuehrt, keine bekannten Schwachstellen (`mhvp` selbst wird als lokales Paket nicht auf PyPI gefunden, das ist erwartet) |
| `pnpm audit --prod` (Workspace) | ausgefuehrt, keine bekannten Schwachstellen |

Status: **erledigt, keine Befunde**. Beide Laeufe sind vom 27.09.2026 und beziehen nur
Produktionsabhaengigkeiten ein (`--prod`); `gitleaks` war im Container nicht installiert, siehe
Abschnitt 6.

## 2. HTTP-Sicherheitsheader und CORS

Befund 1 (mittel, **behoben**): Die FastAPI-App setzte keine Sicherheitsheader auf
Anwendungsebene, sondern verliess sich vollstaendig auf Traefik (`infra/traefik/dynamic/
middlewares.yml`, `infra/compose.prod.yaml`). Ein direkter Zugriff auf die API (Fehlkonfiguration
der Edge, lokale Entwicklung ohne Traefik, Health-Checks) haette dann ohne
`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy` oder
`Permissions-Policy` geantwortet.
Behebung: `apps/api/src/mhvp/core/security_headers.py` (neue Middleware
`SecurityHeadersMiddleware`), additiv in `apps/api/src/mhvp/main.py` eingehaengt. Da die API nur
JSON liefert, ist die CSP maximal streng (`default-src 'none'; frame-ancestors 'none'`). Test:
`apps/api/tests/unit/test_m27_security_headers.py`.

Befund 2 (niedrig, **behoben**): Die Traefik-Middleware `security-headers` und das
Produktions-Compose setzten `frameDeny`, `contentTypeNosniff`, `referrerPolicy` und (nur prod)
HSTS, aber keine `Permissions-Policy`. Ergaenzt in
`infra/traefik/dynamic/middlewares.yml` und `infra/compose.prod.yaml`
(`customResponseHeaders`/`customresponseheaders`).

Befund 3 (niedrig, **behoben**): Beide Next.js-Apps (`apps/web-crm`, `apps/web-portal`) setzten
keine eigene `headers()`-Funktion. Ergaenzt in beiden `next.config.ts` als
Verteidigung in der Tiefe (gleiche Header wie Traefik, zusaetzlich eine anwendungsseitige CSP mit
`frame-ancestors 'none'`, `base-uri 'self'`, `form-action 'self'`).

CORS: Die API setzt keine `CORSMiddleware`. Das ist beabsichtigt und **kein Befund**: Beide
Next.js-Apps sprechen die API ausschliesslich serverseitig an
(`apps/web-crm/src/lib/api-server.ts`, `apps/web-portal/src/lib/api-server.ts`), es gibt keinen
Browser-Origin, der direkt gegen die API faehrt. Sollte kuenftig ein Browser-Client (z. B. eine
SPA oder ein Drittanbieter-Portal) direkt gegen die API sprechen muessen, ist eine explizite
Origin-Allowliste ueber `CORSMiddleware` in `mhvp.main` nachzuruesten (Offene Entscheidung, siehe
`docs/OPEN_QUESTIONS.md`).

## 3. Ratenbegrenzung

Bereits vorhanden und geprueft: `apps/api/src/mhvp/core/ratelimit.py`
(`RateLimitMiddleware`, Redis-Fixed-Window, ein Befund aus einer frueheren Pruefung 1.22 ist dort
bereits vermerkt und behoben). Sie deckt global alle Endpunkte ausser `/api/v1/health` ab, mit
getrennten Limits fuer anonym (IP-basiert, damit Login, Passwort-Reset, Magic Link und oeffentliche
Webhooks erfasst sind) und authentifiziert (Mandant plus Akteur). Zusaetzlich begrenzt Traefik
selbst (`api-ratelimit`/`${PREFIX}-ratelimit`, 100/1s mit Burst 200) an der Kante.
Status: **kein neuer Befund**, Ratenbegrenzung deckt die geforderten Faelle bereits ab.

## 4. Upload-Haertung

Bereits vorhanden und geprueft: `apps/documents/services.check_upload` prueft Leerdatei,
Groessenlimit (`document_max_bytes`), MIME-Allowlist (`ALLOWED_MIME_TYPES`,
`apps/api/src/mhvp/documents/text.py`) und Magic-Byte-Uebereinstimmung
(`sniff_matches`). SVG ist **nicht** in der Allowlist enthalten, also kein Vektor fuer
eingebettetes Skript ueber Bild-Uploads. Dateinamen werden auf 255 Zeichen gekuerzt
(`apps/api/src/mhvp/documents/services.py`); eine explizite Pruefung auf Pfad-Traversal-Zeichen
(`../`, Nullbyte) im Anzeige-Dateinamen fehlt.
Status: **offen, niedrig** (Befund 4): Der gespeicherte Blob-Key wird nicht aus dem
Original-Dateinamen gebildet (kein Traversal-Risiko im Storage), aber ein roher Dateiname mit
Steuerzeichen kann in `Content-Disposition` beim Download landen. Empfehlung: Dateinamen beim
Speichern zusaetzlich auf druckbare Zeichen ohne `/`, `\` und Steuerzeichen normalisieren. Nicht in
diesem Task behoben (fremde Datei `documents/services.py`, gemeinsame Datei, minimal invasiv statt
in dieser Welle geaendert; Owner: Team Dokumente, kein Gate betroffen, siehe
`docs/OPEN_QUESTIONS.md`).

## 5. Sitzungs- und Token-Hygiene

Geprueft, **keine Befunde**: Access- und Refresh-Token liegen ausschliesslich in
`httpOnly`, `SameSite=Strict`, `Secure` (ausser localhost) Cookies
(`apps/web-crm/src/lib/session.ts`, `apps/web-portal/src/lib/session.ts`, Tests
`lib.test.ts`). Der Server refresht transparent einmal bei 401
(`apps/*/src/lib/api-server.ts`). Refresh-Token-Rotation und Ablaufzeiten liegen in
`apps/api/src/mhvp/core/auth/routers.py` (`RefreshToken.expires_at`, Token-Familien). Ein
serverseitiges Logout (Invalidieren des Refresh-Tokens) ist vorhanden. Keine Aenderung noetig.

## 6. Secrets-Scan

`gitleaks` ist im Container nicht installiert (offline nicht nachinstallierbar geprueft,
**nicht ausgefuehrt**). Ersatzweise Muster-Grep nach AWS-Keys, privaten Schluesseln, `sk-`- und
Slack-Token-Praefixen ueber Quellcode und YAML: keine echten Treffer, nur ein
Test-Fixture (`apps/api/tests/unit/test_m40_metering_adapters.py`, offensichtlich ein
Beispielwert) sowie Fundstellen in Drittbibliotheken (`moto`, `Pillow`) im `.venv`. Keine
Zugangsdaten im Klartext im eigenen Code gefunden.
Status: **Musterpruefung erledigt, `gitleaks`-Lauf nicht ausgefuehrt** (Empfehlung: `gitleaks` im
Setup-Skript oder CI-Image ergaenzen, damit ein vollstaendiger History-Scan moeglich ist).

## Empfehlung fuer den externen Pentest-Umfang

- Authentifizierung/Autorisierung: Login, MFA, Passwort-Reset, Magic Link, Token-Rotation,
  Mandantentrennung (RLS) ueber die Fachmodule hinweg.
- Portal-Endpunkte (Eigentuemer, Beirat, Formulare, Mandate) auf horizontale Rechteausweitung.
- Datei-Uploads (Dokumente, Import) mit praeparierten Dateien (Magic-Byte-Mismatch,
  Zip-Bomben, sehr grosse Dateien nahe dem Limit).
- Oeffentliche Webhooks (Paperless, Gmail-Push, Objektakte) auf Signatur-/Replay-Schutz.
- Ratenbegrenzung und Traefik-Header unter Last und bei Redis-Ausfall (Fail-open-Verhalten
  bewusst pruefen, siehe `apps/api/src/mhvp/core/ratelimit.py`).
- CSP/Header-Wirksamkeit im Browser (kein Inline-Skript ausser den deklarierten Ausnahmen).

## Betreiberentscheidungen

- Offene Entscheidung OE-M27-02-01: CORS-Allowlist nachruesten, sobald ein Browser-Client
  direkt gegen die API spricht (Owner: Betreiber/Architektur, kein Gate betroffen, da aktuell
  kein solcher Client existiert).
- Offene Entscheidung OE-M27-02-02: Dateinamen-Normalisierung fuer `Content-Disposition`
  (Owner: Team Dokumente, kein Gate betroffen).
- Offene Entscheidung OE-M27-02-03: `gitleaks` in Setup/CI ergaenzen fuer vollstaendigen
  Secrets-Scan (Owner: Plattform/CI, kein Gate betroffen).
