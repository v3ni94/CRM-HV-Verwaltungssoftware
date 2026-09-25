# Abschaltung des Immoware Hub (Roadmap Punkt 10)

Stand 25.09.2026. Der Immoware Hub (Laravel, /opt/immoware-hub, Domains immoware.muellerhv.de und
mail.muellerhv.de) wurde modulweise in das CRM übernommen. Nach Abschluss der Lernphase (M33)
ist keine Funktion mehr nur im Hub vorhanden. Dieses Runbook beschreibt die Abschaltung in
vier Schritten, jeder Schritt ist für sich rückholbar.

## 0. Voraussetzungen (vor Schritt 1 prüfen)

| Nr. | Prüfung | Nachweis |
|-----|---------|----------|
| V1 | Immoware24-DAV-Zugang im CRM eingetragen, "Verbindung prüfen" grün, mindestens ein erfolgreicher Abruf | Einstellungen, Immoware24-Anbindung |
| V2 | Gmail-Postfach im CRM verbunden und synchron, Vier-Augen-Freigabe aktiv | Einstellungen, Postfächer |
| V3 | Paperless im CRM verbunden (Feld-IDs 7 und 5), Dokumente im Ticket und Objekt sichtbar | Einstellungen, DMS |
| V4 | Hub-Doctor zeigt keinen aktiven Postfachimport und alle Schreibflags auf false | `docker compose exec app php artisan hub:doctor` im Hub |
| V5 | Aktuelles Hub-Backup vorhanden und GPG-lesbar (privater Schlüssel liegt nicht auf dem Server, Prüfung des Pakets reicht) | `/var/backups/immoware-hub/daily/` |

Der Hub hielt zum Stichtag keine Stammdaten (Property-Spiegel leer), Postfachimport und
Schreibpfade waren nie produktiv aktiv. Es gibt daher keine Datenübernahme aus dem Hub in das
CRM, nur die Sicherung des letzten Standes.

## 1. Letztes Backup und Einfrieren (Tag 0)

```
cd /opt/immoware-hub && bash -c 'set -a; . /etc/immoware-hub/backup.env; set +a; deploy/scripts/backup-docker.sh'
ls -la /var/backups/immoware-hub/daily/ | tail -3
docker compose stop scheduler worker mail-worker mail-worker-high
```

Ergebnis: Web und App laufen noch (Lesezugriff möglich), keine Hintergrundjobs mehr.

## 2. Weiterleitung auf das CRM (Tag 0, direkt nach Schritt 1)

Die alten Hostnamen sollen nicht ins Leere laufen. Traefik leitet sie dauerhaft (301) auf das
CRM um. Dazu die Hub-Container stoppen und die Zusatzdatei in den CRM-Stack aufnehmen:

```
cd /opt/immoware-hub && docker compose stop web app
cd /opt/mhvp && docker compose -p mhvp --env-file .env.prod -f infra/compose.yaml -f infra/compose.prod.yaml -f infra/compose.hub-redirect.yaml up -d web-crm
sleep 5; curl -sI https://mail.muellerhv.de/ | grep -i "^HTTP\|^location"; curl -sI https://immoware.muellerhv.de/ | grep -i "^HTTP\|^location"
```

Erwartung: `HTTP/2 301` mit `location: https://crm.mueller-holding.ag/`. Damit die Weiterleitung
bei künftigen Deploys erhalten bleibt, in `/opt/mhvp/mhvp.sh` die Zusatzdatei an die
Compose-Aufrufe anhängen (hinter `-f infra/compose.prod.yaml`).

Rückweg: Zusatzdatei aus dem Aufruf entfernen, `up -d web-crm`, danach im Hub `docker compose up -d`.

## 3. Aufräumen auf dem Server (Tag 14, wenn keine Rückfragen)

```
cd /opt/immoware-hub && docker compose down          # Volumes bleiben erhalten
rm /etc/cron.d/immoware-hub-backup
mv /etc/logrotate.d/immoware-hub /root/immoware-hub-logrotate.bak
docker image ls 'immoware-hub' -q | xargs -r docker image rm
```

Das MariaDB-Volume und `/var/backups/immoware-hub` bleiben bis Tag 90 liegen.

## 4. Endgültig (Tag 90)

- Letztes Backup-Paket nach extern kopieren (verschlüsselt, Empfänger D4BE06D177B8B370).
- `docker volume rm` für die Hub-Volumes, `/opt/immoware-hub` und `/var/backups/immoware-hub` entfernen.
- DNS: A-Records für immoware.muellerhv.de und mail.muellerhv.de können bestehen bleiben (Weiterleitung) oder auf einen CNAME crm.mueller-holding.ag umgestellt werden. Keine Änderung an MX, SPF, DKIM, DMARC, die Hostnamen waren nie Mailserver.
- Repository v3ni94/IMMOWARE24 auf GitHub archivieren (nur lesend).

## Domain mail.mueller-holding.ag

Die Mail- und Vorgangsbearbeitung lebt im CRM unter crm.mueller-holding.ag. Ein eigener
Hostname mail.mueller-holding.ag ist technisch nicht nötig. Wird er gewünscht, gilt derselbe
Weg wie in Schritt 2: Hostname in `MHVP_HUB_HOST_MAIL` eintragen, Weiterleitung auf das CRM.
Ein eigener Router mit eigener Oberfläche ist nicht vorgesehen, damit es nur eine Anmeldung
und eine Sitzung gibt.

## Protokoll

| Datum | Schritt | Ergebnis |
|-------|---------|----------|
| 25.09.2026 | 1 und 2 | Letztes Backup immoware_hub-20260925-125702, Hub-Container gestoppt, Weiterleitung über infra/compose.hub-redirect.yaml aktiv, mhvp.sh ergänzt (Sicherung mhvp.sh.vor-hub-redirect) |
| 09.10.2026 | 3 | frühester Termin, Freigabe der Geschäftsführung erforderlich |
| 24.12.2026 | 4 | frühester Termin, Freigabe der Geschäftsführung erforderlich |

Hinweis für Betreiber: Prüfbefehle nie mit `set -e` in einer interaktiven Sitzung ausführen, die Shell beendet sich sonst beim ersten Fehler. Nach `up -d web-crm` mindestens 20 Sekunden warten, bevor Traefik-Antworten geprüft werden.

## Freigabe

Schritt 1 und 2 sind rückholbar und können durch die Geschäftsführung per Zuruf freigegeben
werden. Schritt 3 und 4 löschen Daten und brauchen eine ausdrückliche Freigabe.
