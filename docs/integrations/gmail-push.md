# Gmail-Push einrichten: Schritt-für-Schritt-Anleitung (Betreiber)

Stand 27.09.2026. Diese Anleitung ergänzt die technische Beschreibung in `docs/integrations/gmail.md`
(Endpunkt `POST /api/v1/integrations/gmail/push`, Code `apps/api/src/mhvp/communication/gmail_push.py`,
Watch-Erneuerung `apps/api/src/mhvp/communication/tasks.py`). Offener Punkt M20-05 in
`docs/OPEN_QUESTIONS.md`: die Einrichtung selbst ist Betreiberaufgabe, hier festgehalten als
nachvollziehbare Anleitung. Ohne diese Einrichtung bleibt der Sofortabruf aus, der Fünf-Minuten-
Beat-Sync läuft unverändert weiter.

## 1. Google Cloud Console: Projekt

1. Im selben Google Cloud Projekt arbeiten, in dem der OAuth-Client für die Gmail-Postfächer
   angelegt ist (Menü oben, Projektauswahl). Ein zweites Projekt funktioniert nicht, weil der
   Consent des Postfachs an den OAuth-Client im ersten Projekt gebunden ist.
2. API aktivieren: „APIs und Dienste“, „Bibliothek“, „Cloud Pub/Sub API“ suchen, aktivieren
   (meist bereits aktiv, wenn Gmail API schon genutzt wird).

## 2. Pub/Sub-Thema anlegen

1. „Pub/Sub“, „Themen“, „Thema erstellen“.
2. Themen-ID zum Beispiel `mhvp-gmail`. Der vollständige Name lautet
   `projects/<projektkennung>/topics/mhvp-gmail`.
3. Verschlüsselung: Google verwaltete Schlüssel reichen (kein CMEK erforderlich).

## 3. Berechtigung für Gmail erteilen

1. Auf dem angelegten Thema: „Berechtigungen“, „Prinzipal hinzufügen“.
2. Prinzipal: `gmail-api-push@system.gserviceaccount.com` (Googles fester Dienstaccount für
   Gmail-Push, kein eigenes Dienstkonto).
3. Rolle: „Pub/Sub-Veröffentlicher“ (`roles/pubsub.publisher`).
4. Ohne diese Rolle lehnt Google `users.watch` mit HTTP 403 ab; das Postfach zeigt dann im CRM
   unter Einstellungen, Postfächer eine Fehlermeldung statt „Watch aktiv bis“.

## 4. Push-Subscription anlegen

1. Auf dem Thema: „Abonnement erstellen“.
2. Zustellungstyp: „Push“.
3. Endpunkt-URL: `https://<api-host>/api/v1/integrations/gmail/push?token=<geheimnis>`.
   Das Geheimnis ist ein zufälliger Wert von mindestens 32 Zeichen (zum Beispiel
   `openssl rand -hex 32`), identisch mit `MHVP_GMAIL_PUSH_TOKEN` in `.env.prod`. Alternativ
   kann das Geheimnis als Kopfzeile `X-MHVP-Push-Token` übertragen werden, sofern die
   Subscription benutzerdefinierte Kopfzeilen unterstützt; dann entfällt der Query-Parameter.
4. OIDC-Token aktivieren: „Authentifizierung aktivieren“, Dienstkonto auswählen oder anlegen
   (zum Beispiel `mhvp-pubsub-push@<projektkennung>.iam.gserviceaccount.com`), Audience auf die
   Endpunkt-URL ohne Query-Anteil setzen, zum Beispiel `https://<api-host>/api/v1/integrations/gmail/push`.
   Diese Audience in `MHVP_GMAIL_PUSH_AUDIENCE` in `.env.prod` hinterlegen. Damit prüft der
   Endpunkt zusätzlich zum Geheimnis Aussteller (`accounts.google.com`), Zielgruppe und
   Signatur des Pub/Sub-Tokens gegen Googles Schlüssel (`verify_oidc` in `gmail_push.py`); ohne
   gesetzte Audience bleibt diese zusätzliche Prüfung aus, das Geheimnis allein genügt dann.
5. Bestätigungsfrist (Ack Deadline): 30 Sekunden reichen, der Endpunkt stellt nur in die
   Warteschlange und antwortet sofort mit 204.
6. Wiederholungsrichtlinie: Exponentielles Backoff, Minimum 10 Sekunden, Maximum 600 Sekunden.

## 5. Variablen in `.env.prod`

```
MHVP_GMAIL_PUBSUB_TOPIC=projects/<projektkennung>/topics/mhvp-gmail
MHVP_GMAIL_PUSH_TOKEN=<das oben erzeugte Geheimnis, mindestens 32 Zeichen>
MHVP_GMAIL_PUSH_AUDIENCE=https://<api-host>/api/v1/integrations/gmail/push
```

`MHVP_GMAIL_PUBSUB_TOPIC` wird beim nächsten `users.watch` (Registrierung oder Erneuerung)
verwendet; ohne gesetztes Thema unterbleibt die Watch-Registrierung, das Postfach läuft dann
nur über den Beat-Sync. Nach dem Setzen der Variablen API- und Worker-Container neu starten
(`docker compose -f infra/docker-compose.prod.yml up -d --force-recreate api worker beat`, oder
die entsprechenden Prod-Dienste), damit die Werte geladen werden.

## 6. Watch registrieren und Erneuerung

* Ein Gmail-Watch läuft höchstens sieben Tage. Der tägliche Beat-Job
  `communication-gmail-watch-renew` (`gmail_watch_renew_all` in `tasks.py`, 04:10 Uhr) erneuert
  jedes Postfach, dessen Watch innerhalb eines Tages abläuft; kein Zutun des Betreibers nötig,
  sobald Thema und Geheimnis gesetzt sind.
* Erststart: die Watch-Registrierung läuft beim regulären History-Sync (`renew_watch=True`)
  mit, also spätestens beim nächsten Fünf-Minuten-Sync nach dem Setzen der Variablen.
* Status je Postfach unter Einstellungen, Postfächer: „Watch aktiv bis <Datum, Uhrzeit>“ und
  „letzte Push-Nachricht <Zeitpunkt>“ (Feld `last_push_at`, Quelle `MailboxSettings.tsx`).
  Ein Postfach ohne „Watch aktiv bis“ nach dem nächsten Sync hat keine gültige Berechtigung
  oder kein gesetztes Thema (siehe Schritt 3).

## 7. historyId-Nachverarbeitung und Vollabgleich-Fallback

* Jede Push-Nachricht liefert `historyId`; der Job liest Gmails History-API ab dem zuletzt
  gespeicherten `gmail_history_id` des Postfachs nach, nicht ab der im Push mitgelieferten Id
  (Google garantiert keine Reihenfolge der Zustellung).
* Antwortet die History-API mit 404 (History zu alt, mehr als ca. sieben Tage seit dem letzten
  Abgleich, zum Beispiel nach einem längeren Ausfall), fällt der Sync auf einen vollständigen
  Abgleich der letzten `INBOX`-Nachrichten zurück (`gmail.py`, dieselbe Logik wie beim
  Ersteinrichten eines Postfachs) und setzt danach `gmail_history_id` neu.
* Fehler werden nach ADR 0004 einem Fehlercode zugeordnet (`mhvp.core.problems`,
  `WEBHOOK_SIGNATURE` bei ungültigem Push-Token oder OIDC-Token, `WEBHOOK_TOO_LARGE` bei zu
  großem Push-Inhalt); Sync-Fehler je Postfach erscheinen zusätzlich im Postfach-Status.

## 8. Prüfbefehle

Geheimnis-Prüfung (erwartet 204, mit falschem Token 401):

```bash
curl -i -X POST "https://<api-host>/api/v1/integrations/gmail/push?token=<geheimnis>" \
  -H 'Content-Type: application/json' \
  -d '{"message":{"data":"'"$(printf '{"emailAddress":"postfach@muellerhv.de","historyId":"123"}' | base64 -w0)"'"}}'
```

Subscription-Zustand und letzte Zustellversuche:

```bash
gcloud pubsub subscriptions describe <subscription-name> --project <projektkennung>
gcloud pubsub subscriptions pull <subscription-name> --project <projektkennung> --limit=5 --auto-ack=false
```

Watch-Registrierung serverseitig (Worker-Log nach dem nächsten Sync):

```bash
docker compose -f infra/docker-compose.prod.yml logs worker --since 10m | grep -i "gmail.*watch"
```

Beat-Zeitplan bestätigen (Erneuerung eingetragen):

```bash
docker compose -f infra/docker-compose.prod.yml logs beat --since 1h | grep "communication-gmail-watch-renew"
```

## 9. Häufige Fehler

| Symptom | Ursache | Behebung |
| --- | --- | --- |
| `users.watch` 403 | Rolle Pub/Sub-Veröffentlicher fehlt | Schritt 3 wiederholen |
| Push kommt nie an | Endpunkt-URL falsch oder Firewall blockiert Google-IPs | Endpunkt-URL prüfen, `environment.network` (Betreiber-Doku) |
| Push kommt an, 401 | Geheimnis oder OIDC-Audience stimmen nicht mit `.env.prod` überein | Werte in Schritt 5 vergleichen, Container neu gestartet? |
| „Watch aktiv bis“ bleibt leer | `MHVP_GMAIL_PUBSUB_TOPIC` nicht gesetzt oder Container nicht neu gestartet | Schritt 5 und Neustart prüfen |
