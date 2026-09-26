# M30 SSO: Anmeldung externer Dienste über das CRM (OIDC)

Stand 25.09.2026. Anlass: Die Statusseite status.mueller-holding.ag (Repository objektakte,
Verzeichnis monitoring/) soll ohne eigenes Passwort erreichbar sein, sobald jemand im CRM
angemeldet ist. Browser-Cookies gelten je Host, die CRM-Sitzung (crm.mueller-holding.ag) ist auf
einer anderen Domain nicht lesbar. Der Weg führt deshalb über den vorhandenen OIDC-Anbieter der
Plattform (ADR 0006 Nr. 7, `mhvp.core.auth.oidc`).

## Ausgangslage

Der Anbieter beherrschte den Authorization-Code-Fluss mit PKCE, aber nur mit Bearer-Token: die
Autorisierungsanfrage kam nicht aus dem Browser, und Relying Parties ließen sich nur per SQL
eintragen. Für einen Browser fehlten die Brücke von der Sitzung zum Bearer-Aufruf und ein Weg,
Clients samt Secret zu registrieren.

## Umsetzung

1. **Browser-Brücke** `apps/web-crm/src/app/oidc/authorize/route.ts`: nimmt die
   OIDC-Parameter entgegen, liest das Sitzungs-Cookie, ruft die API mit Bearer auf und reicht
   die Umleitung mit `code` und `state` an die Relying Party durch. Ohne Sitzung wird die
   Anmeldeseite angezeigt, die mit `next` hierher zurückkehrt. Ein fehlender Mandant führt nicht
   nach `/mandant` (Middleware), weil Relying Parties nur die Identität brauchen.
2. **Discovery**: `authorization_endpoint` zeigt auf `{MHVP_WEB_CRM_URL}/oidc/authorize`,
   solange `MHVP_WEB_CRM_URL` gesetzt ist. Token, Userinfo und JWKS bleiben bei der API.
3. **Registrierung** `python -m mhvp.core.auth.oidc_clients` (create, list, rotate-secret,
   deactivate, activate). Das Secret wird einmalig ausgegeben und als SHA-256 gespeichert;
   Redirect-URIs nur mit https (http nur für localhost). Public Clients (`--public`) nutzen
   PKCE ohne Secret.
4. **Relying Party Statusseite**: oauth2-proxy vor der Statusseite (Repository objektakte,
   `monitoring/docker-compose.yml`, Profil `sso`) mit ForwardAuth in Traefik; Anleitung dort in
   `docs/betrieb/statusseite.md`, hier `docs/runbooks/oidc-relying-parties.md`.

## Berechtigung

Jeder aktive CRM-Benutzer darf sich bei einer registrierten Relying Party anmelden (Annahme
A-039). Die Relying Party sieht `sub`, `email`, `name` und `tenant_id` (falls gewählt). Eine
Freigabe je Benutzer oder Rolle ist nicht umgesetzt; wird sie gebraucht, ist sie in der
Autorisierungsanfrage (API) zu ergänzen, nicht in der Brücke.

## Tests

- `apps/api/tests/unit/test_oidc_discovery.py`: Discovery mit und ohne CRM-URL.
- `apps/api/tests/unit/test_oidc_clients.py`: Prüfung von client_id und redirect_uri, Parser.
- `apps/api/tests/integration/test_m30_oidc_clients.py`: Registrierung über die CLI,
  vertraulicher Client (Secret Pflicht, Rotation, Deaktivierung) im vollständigen Code-Fluss.
- `apps/web-crm/src/app/oidc/authorize/route.test.ts`: Parameterprüfung, Anmeldeumleitung,
  Sitzungsauffrischung, Durchreichen der Umleitung, Fehlerfälle.

## Offen

- M30-01: Betrieb der Relying Party Statusseite (Client anlegen, Secrets, Traefik-Profil) liegt
  beim Betreiber, siehe Runbook.

## Stand 26.09.2026

Zusammenfassung aus den Nachträgen dieses Plans, dem `CHANGELOG.md` (1.19.0 bis 1.22.1) und der Lückenliste `docs/plans/LUECKENLISTE-2026-09-26.md`; keine neuen Sachverhalte.

* Im Code: Browserbrücke `apps/web-crm/src/app/oidc/authorize/route.ts`, Discovery mit `MHVP_WEB_CRM_URL`, CLI `python -m mhvp.core.auth.oidc_clients`, Runbook `docs/runbooks/oidc-relying-parties.md`.
* Tests wie oben; unverändert offen: M30-01 (Betrieb der Relying Party Statusseite beim Betreiber), keine Freigabe je Benutzer oder Rolle (Annahme A-039).
