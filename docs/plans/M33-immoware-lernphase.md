# M33: Lernphase Immoware24

## Ziel

Der Immoware Hub (`/home/user/IMMOWARE24`) wird stillgelegt. Sein Modul Learning wird im CRM
neu implementiert, ohne Anbindung an den Hub. Die Lernphase erkundet lesend Struktur und
Feldnutzung des bereits vorhandenen Immoware24-Spiegels (`mhvp.immoware`, M32) je Art (WebDAV,
CardDAV, CalDAV) und vergleicht jeden Lauf mit dem letzten erfolgreichen Lauf gleicher Art.
Reine Erkenntnisgewinnung für die spätere Ausgestaltung des Spiegels, kein Schreibpfad Richtung
Immoware24.

## Datenmodell

`immoware_learning_run` (tenant-gebunden, RLS wie alle Immoware-Tabellen):

- `kind`: `webdav` | `carddav` | `caldav`
- `status`: `pending` | `running` | `done` | `failed`
- `started_at`, `finished_at`
- `facts` (JSONB): Rohbefund des Laufs
- `diff` (JSONB): Vergleich mit dem letzten erfolgreichen Lauf gleicher Art (`changed`, lesbare
  `changes`)
- `error`: bereinigte Fehlermeldung (`sanitize_error`)
- `triggered_by_user_id`

Migration `0045_immoware_learning.py`, `down_revision = "0044"`.

## Scanner (`mhvp/immoware/learning.py`)

Reine Funktionen auf bereits geladenen Zeilen (Duck-Typing, testbar ohne Datenbank):

- `compute_webdav_facts`: Ordnerbaum bis Tiefe 3 aus `immoware_dav_document`, Dateien und Bytes
  je Ordner, Dateiendungen-Verteilung, Anteil Ordner mit erkannter Objektnummer.
- `compute_carddav_facts`: Feldnutzung (FN, ORG, E-Mail, Telefon, Adresse) aus
  `immoware_dav_contact`, Anteile, Duplikatkandidaten nach normalisierter E-Mail.
- `compute_caldav_facts`: Feldnutzung (SUMMARY, LOCATION, DESCRIPTION) aus `immoware_dav_event`,
  Verteilung je Monat der letzten 12 Monate, Anteil ganztägig, häufigste SUMMARY-Präfixe.
- `diff_facts`: Vergleich mit dem letzten erfolgreichen Lauf gleicher Art, liefert `changed` und
  lesbare Sätze.

`scan_webdav`/`scan_carddav`/`scan_caldav` laden die Zeilen aus der jeweiligen Spiegeltabelle
und rufen die reine Funktion auf.

## Endpunkte

- `POST /api/v1/immoware/learning/runs` `{kind}` (Berechtigung `immoware:update`): legt einen
  Lauf an und stößt den Celery-Task `mhvp.immoware.learning_run` an.
- `GET /api/v1/immoware/learning/runs?kind=` (Berechtigung `immoware:read`): paginierte Liste.
- `GET /api/v1/immoware/learning/runs/{id}`: Einzelansicht mit Fakten und Diff.

Problem-Code `MHVP-IMW-0004` (Lernlauf nicht gefunden), Fortführung der bestehenden
`MHVP-IMW-00xx`-Reihe.

## Grenzen

- Kein zusätzlicher DAV-Zugriff über den bestehenden Spiegel hinaus; die Lernphase liest
  ausschließlich bereits gespiegelte Zeilen, kein PROPFIND außerhalb des laufenden Syncs.
- Kein Schreibpfad Richtung Immoware24.
- Keine Anbindung an den Immoware Hub; eigenständige Re-Implementierung im CRM.

## Stand 26.09.2026

Zusammenfassung aus den Nachträgen dieses Plans, dem `CHANGELOG.md` (1.19.0 bis 1.22.1) und der Lückenliste `docs/plans/LUECKENLISTE-2026-09-26.md`; keine neuen Sachverhalte.

* Im Code: `immoware_learning_run` (Migration 0045), Scanner `mhvp.immoware.learning` mit reinen Funktionen je Art, Endpunkte unter `/api/v1/immoware/learning/runs`, Celery-Task `mhvp.immoware.learning_run`, CRM-Seite `/immoware/lernphase`.
* Tests: `tests/unit/test_immoware_dav.py`, `test_m32_immoware.py`. Keine offenen Punkte in diesem Plan; die Erkenntnisse fließen in M32 ein.
