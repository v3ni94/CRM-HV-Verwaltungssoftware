# Annahmen

Stand: 23.09.2026. Grundlage: `docs/MASTER-PROMPT.md`, Abschnitt 0.1 Regel 3.

Hier stehen nur unkritische Annahmen, die den Entwurfsbetrieb ermöglichen. Keine dieser Annahmen berührt Geld, Forderungsbestand, Datenschutz, gesetzliche Fristen oder Beweiserhalt. Solche Punkte wären nach Regel 3 offene Fragen und stehen in `docs/OPEN_QUESTIONS.md`. Jede Annahme wird spätestens beim genannten Meilenstein überprüft und bei Bestätigung oder Widerlegung hier fortgeschrieben.

## A-001

| Feld | Inhalt |
| --- | --- |
| Annahme | Das Wurzelverzeichnis dieses Repositorys (CRM-HV-Verwaltungssoftware) ist die Wurzel `mhvp/` des Monorepos nach Abschnitt 17. |
| Begründung | Das Repository existiert bereits auf GitHub; ein zusätzliches Unterverzeichnis `mhvp/` brächte keinen Nutzen. Der Name selbst ist offen (M1-05, V4). |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | gesamtes Repository, Pfade in Dokumentation und CI |
| Überprüfung spätestens bei Meilenstein | M2 |
| Datum | 23.09.2026 |

## A-002

| Feld | Inhalt |
| --- | --- |
| Annahme | CI läuft auf GitHub Actions. |
| Begründung | Abschnitt 4.3 nennt GitHub Actions und Gitea Actions nur für den Fall, dass das Repository dort liegt; das Repository liegt auf GitHub (M1-04). |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | `.github/workflows`, Pinning nach ADR 0001 |
| Überprüfung spätestens bei Meilenstein | M9 |
| Datum | 23.09.2026 |

## A-003

| Feld | Inhalt |
| --- | --- |
| Annahme | psycopg 3 ist der einzige Datenbanktreiber, asynchron für die API, synchron für Worker und Alembic. |
| Begründung | Ein Treiber verringert Abweichungen im Verhalten von Transaktionen und `set_config` (ADR 0001, ADR 0002). |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | api, worker, Migrationen |
| Überprüfung spätestens bei Meilenstein | M2 |
| Datum | 23.09.2026 |

## A-004

| Feld | Inhalt |
| --- | --- |
| Annahme | Technische Dokumentation (ADR, Runbooks, README, Agentenregeln, Regelregister) ist auf Englisch; Betreiber- und Fachdokumente sind auf Deutsch. |
| Begründung | Abschnitt 0.1 Regel 10. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | `docs/`, `README.md`, `CLAUDE.md`, `AGENTS.md` |
| Überprüfung spätestens bei Meilenstein | M9 |
| Datum | 23.09.2026 |

## A-005

| Feld | Inhalt |
| --- | --- |
| Annahme | Entwicklungshostnamen sind `crm.localhost`, `portal.localhost` und `api.localhost`. |
| Begründung | `*.localhost` löst ohne DNS-Eintrag lokal auf; die Produktionsdomains aus Abschnitt 3.3 werden dadurch nicht berührt. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | `infra/compose.dev.yaml`, Traefik (nur Entwicklung) |
| Überprüfung spätestens bei Meilenstein | M9 |
| Datum | 23.09.2026 |

## A-006

| Feld | Inhalt |
| --- | --- |
| Annahme | Produktion nutzt den vorhandenen Traefik auf dem IONOS-Server über ein externes Docker-Netzwerk; es wird kein zweiter Traefik gestartet. |
| Begründung | Abschnitt 3.1: Traefik ist bereits vorhanden und terminiert TLS für alle Dienste der Müller-Gruppe. Netzwerkname, Entrypoint und Cert-Resolver sind offen (M1-02). |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | `infra/compose.prod.yaml` |
| Überprüfung spätestens bei Meilenstein | M9 |
| Datum | 23.09.2026 |

## A-007

| Feld | Inhalt |
| --- | --- |
| Annahme | Die Freigabestufen G1 bis G5 sind je Mandant geschlossen; es gibt keinen globalen Schalter und keine Umgebungsvariable zum Öffnen. Die Speicherung je Mandant folgt mit M2. |
| Begründung | Abschnitt 0.1 Regel 1, Abschnitt 18.0, Abschnitt 19.2; ADR 0003. Die Annahme betrifft nur den zeitlichen Ablauf der Persistenz, nicht die Sperrwirkung. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | `mhvp.core.release_gates`, API, Jobs |
| Überprüfung spätestens bei Meilenstein | M2 |
| Datum | 23.09.2026 |

## A-008

| Feld | Inhalt |
| --- | --- |
| Annahme | Zeitstempel werden in UTC gespeichert (`TIMESTAMPTZ`); die fachliche Zeitzone ist Europe/Berlin. |
| Begründung | Abschnitt 4.1 legt UTC fest; die fachliche Zeitzone ergibt sich aus dem Standort der Mandanten. Fristberechnungen folgen erst mit freigegebenen Regeln. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | api, worker (Celery in UTC), Oberfläche |
| Überprüfung spätestens bei Meilenstein | M2 |
| Datum | 23.09.2026 |

## A-009

| Feld | Inhalt |
| --- | --- |
| Annahme | Paketverwaltung mit pnpm Workspaces (Node) und uv (Python). |
| Begründung | Beide erzeugen Lockfiles, die E16 verlangt (ADR 0001). |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | Monorepo, CI, Container-Builds |
| Überprüfung spätestens bei Meilenstein | M9 |
| Datum | 23.09.2026 |

## A-010

| Feld | Inhalt |
| --- | --- |
| Annahme | SeaweedFS 4.47 dient nur als S3-kompatibler Objektspeicher für Entwicklung und CI, bis M1-01 entschieden ist. |
| Begründung | MinIO-Images sind auf Docker Hub nicht mehr verfügbar (ADR 0005). Die Anwendung nutzt nur die S3-API. |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | `infra/compose*.yaml`, `MHVP_S3_*` |
| Überprüfung spätestens bei Meilenstein | M6 |
| Datum | 23.09.2026 |

## A-011

| Feld | Inhalt |
| --- | --- |
| Annahme | Next.js 15 bleibt, obwohl neuere Hauptversionen existieren. |
| Begründung | Abschnitt 4.2 legt Next.js 15 fest; der Stack wird nicht eigenmächtig geändert (Anhang E, Einleitung). |
| Kennzeichnung | unkritisch, ermöglicht Entwurfsbetrieb |
| Betroffene Bereiche | web-crm, web-portal |
| Überprüfung spätestens bei Meilenstein | M9 |
| Datum | 23.09.2026 |

## Ausdrücklich nicht angenommen

Die folgenden Punkte sind in M1 bewusst nicht entschieden und dürfen nicht als stillschweigende Annahme in Code oder Dokumentation eingehen:

| Punkt | Grund | Zuständig für spätere Festlegung |
| --- | --- | --- |
| Rundungsverfahren (etwa ROUND_HALF_UP) je Rechenwerk | Abschnitt 6.9.8 verlangt die Dokumentation je Rechenwerk in `billing/rules`; betrifft Geld | Festlegung mit M10 und freigegebener Regel |
| Restcentverteilung über D08 hinaus | betrifft Geld; nur der Produktstandard aus 6.9.8 und D08 ist vorgegeben | M10 |
| Verzugszinsen, Mahngebühren, Mahnstufen | V7 offen | M16 |
| Aufbewahrungsfristen und Löschregeln | V17 offen, E05 | M6, M18 |
| Fachliche Fristberechnung (Feiertage, Zugang) | betrifft gesetzliche Fristen | jeweiliger Fachmeilenstein |
| Kontenrahmen | V8 offen | M10 |
