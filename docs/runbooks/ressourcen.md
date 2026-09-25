# Runbook: Ressourcenbegrenzung der Nachbarstacks

Kontext: Auf dem eigenen Server (`docs/runbooks/server-setup.md`, 32 Kerne, 2 TB) laufen
neben dem CRM-Stack (`mhvp`) weitere, unabhängige Container-Stacks, unter anderem
paperless-ngx (Dokumentenmanagement, siehe `docs/integrations/*`) und objektakte
(Übernahmesystem, `uebernahme.muellerhv.de`, siehe `docs/plans/M35-objektakte-uebernahme.md`).
Diese Stacks liegen in ihren eigenen Repositories/Projektverzeichnissen, nicht in diesem
Repository; die folgenden Beispiele sind entsprechend dort einzutragen, nicht hier.

## Ziel

Die CRM-Dienste (`api`, `worker`, `beat`, `web-crm`, `web-portal`, `postgres`) dürfen von
den Nachbarstacks nicht durch CPU- oder Arbeitsspeicherknappheit verdrängt werden
("nicht ausgehungert"). Dazu erhalten die Nachbarstacks eine feste Obergrenze statt einer
unbegrenzten Nutzung.

## Vorgehen

Docker Compose kennt zwei gängige Wege, eine Obergrenze zu setzen. Welcher greift, hängt
von der Compose-Version und davon ab, ob Swarm-Modus verwendet wird (`deploy.resources`
wirkt nur mit `docker stack deploy` oder mit `docker compose` ab Version 2 mit
aktivierten Ressourcengrenzen; die klassischen Felder `cpus`/`mem_limit` wirken bei
`docker compose up` ohne Swarm). Im Zweifel beide Varianten prüfen und die tatsächlich
wirksame durch `docker stats` bestätigen.

### Variante A: `deploy.resources` (Swarm-Modus oder Compose mit Ressourcengrenzen)

In der jeweiligen `compose.yaml` des Nachbarstacks (Platzhalterwerte, keine echten
aktuellen Werte, vor dem Übernehmen mit dem tatsächlichen Bedarf des Stacks abstimmen):

    services:
      webserver:            # z. B. paperless-ngx, Servicename dort prüfen
        deploy:
          resources:
            limits:
              cpus: "<N>"          # z. B. "4" für 4 Kerne
              memory: "<N>G"       # z. B. "4G"
            reservations:
              cpus: "<N>"
              memory: "<N>G"

### Variante B: `cpus` / `mem_limit` (docker compose ohne Swarm)

    services:
      webserver:
        cpus: "<N>"
        mem_limit: "<N>g"
        memswap_limit: "<N>g"      # optional, verhindert unbegrenztes Swappen

Für objektakte (Django/Celery/MariaDB/Redis) gilt dasselbe Muster je Dienst, insbesondere
für die Celery-Worker (OCR- und Klassifikationsläufe sind CPU-intensiv):

    services:
      worker:
        cpus: "<N>"
        mem_limit: "<N>g"
      mariadb:
        cpus: "<N>"
        mem_limit: "<N>g"

## Nach der Änderung

1. Im jeweiligen Projektverzeichnis (nicht in diesem Repository) `docker compose up -d`,
   damit die neuen Grenzen greifen.
2. Mit `docker stats` prüfen, dass die betroffenen Container die gesetzte Grenze nicht
   überschreiten und dass CRM-Container weiterhin ausreichend Kapazität erhalten.
3. Werte dokumentieren dort, wo der jeweilige Stack seine eigene Betriebsdokumentation
   führt; dieses Runbook nennt nur die Methode, keine für diese Server aktuell gültigen
   Zahlen.

## Zusammenhang mit dem CRM-Mehrkernbetrieb

Die CRM-eigenen Werte (`MHVP_API_WORKERS`, `MHVP_WORKER_CONCURRENCY`, `PG_*`) stehen in
`docs/runbooks/server-setup.md`, Abschnitt Mehrkernbetrieb. Der Server teilt sich seine
Kerne mit den Nachbarstacks; bei dauerhaft hoher Last ist grundsätzlich zuerst zu prüfen,
ob ein Nachbarstack seine Grenze braucht oder überschreitet, bevor die CRM-Werte erhöht
werden.
