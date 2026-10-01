# Playwright Kernpfade gegen das Backend, 01.10.2026 (Welle 15, Paket AD08)

Zweck: Ausführung aller `*.backend.spec.ts` von CRM und Portal gegen eine echte API, erstmals auch `core-paths-ga01.backend.spec.ts` (GA01-06). Dies ist ein Testprotokoll, keine fachliche Abnahme und keine rechtliche Bestätigung.

## Umgebung

- API: uvicorn auf 127.0.0.1:8108, Datenbank mhvp_p8, Redis 6380/8, Migration bis head (0355, darunter 0353 AD08 noop, down_revision 0352), Seed mit eigenem Admin (ohne TOTP), S3 per moto auf 9108.
- CRM auf Port 3008, Portal auf Port 3108, Build je mit NEXT_DIST_DIR=.next-ad08 (Build vor dem Lauf, Stand des Arbeitsbaums zu diesem Zeitpunkt).
- Projekte chromium und phone, ein Worker, Rate Limit 6000 pro Minute wie in scripts/e2e-backend.sh.
- Nicht ausgeführt: Projekte tablet und tablet-landscape.

## Ergebnis

| App | bestanden | fehlgeschlagen | übersprungen | Laufzeit |
| --- | --- | --- | --- | --- |
| CRM (63 Tests, Lauf 1) | 57 | 2 | 4 | 5,0 Minuten |
| CRM nach Korrektur der Spec | 58 | 1 | 4 | Einzelläufe der Datei core-paths-ga01 |
| Portal (Lauf 2, nach Locale-Korrektur) | 18 | 0 | 0 | 32 Sekunden |

Hinweis zur Laufzeit: Der erste CRM-Versuch scheiterte vollständig (Seed-Admin und Test-Admin stimmten nicht überein, Testumgebung), der erste Portal-Lauf scheiterte mit 12 von 18 Fehlschlägen an der englischen Oberfläche (siehe unten). Beide Läufe sind in den Zahlen oben nicht enthalten.

## Übersprungene Tests (Bedingungen im Spec, kein Fehler)

- core-paths: Objekt deaktivieren und reaktivieren (verlangt Superadmin-Seed).
- wave-2026-09-27: Postfach Seite 2 (zu wenige Nachrichten), Kaution Abrechnungs-PDF (keine Kaution im Seed).
- waves-2-3-pages: Postfach Kompaktansicht (keine Nachricht im Seed).

## Korrigierte Specs und Konfiguration

1. `apps/web-crm/e2e/core-paths-ga01.backend.spec.ts`, Test Objekt anlegen: "Objekt anlegen" ist die summary eines details Elements, kein Button (Selektor angepasst); Warten auf das Ende der Mandantenwahl vor dem ersten goto; Verwaltungsart über Rolle combobox statt Label (das Label trifft auch die Navigation gleichen Namens). Danach bestanden.
2. `apps/web-crm/e2e/core-paths-ga01.backend.spec.ts`, Test Vertragsformular: Objektfeld über Rolle combobox mit längerem Timeout. Der Test schlägt weiterhin fehl, aus Produktgrund (siehe Befund).
3. `apps/web-portal/playwright.config.ts`: `locale: "de-DE"`, weil das Portal die Sprache seit GB14-01 aus Accept-Language ableitet und die Specs deutsche Texte prüfen. Ohne die Einstellung scheitern 12 von 18 Tests an englischen Beschriftungen.

## Produktbefund

- PB-AD08-01: Die Seite Vertrag anlegen (`/vertraege/neu`) lädt Objekte mit `/api/v1/properties?page_size=500`. Die API erlaubt höchstens 200 und antwortet 422, die Seite zeigt dann eine leere Objektliste, auch mit `?objekt=<id>`. Der Vertrag lässt sich im Browser nicht anlegen. Gleiches Muster in `apps/web-crm/src/app/(app)/einstellungen/benutzer/page.tsx`. Reproduktion: `GET /api/v1/properties?page_size=500` liefert 422, `page_size=200` liefert 200; Spec core-paths-ga01, Test Vertragsformular. Nicht behoben (Produktcode), Zuständigkeit Vertrag und Einstellungen.

## Sonstige Beobachtungen

- Die Migration 0353 fehlte bei Lauf 1 (Kette riss bei 0352 auf 0354); als noop angelegt.
- `next start` meldet eine Warnung wegen `output: standalone`; der Lauf funktioniert, die Konfiguration für CI sollte geprüft werden.
- tsconfig.json beider Apps wurde durch next build verändert und auf den Stand HEAD zurückgesetzt.
