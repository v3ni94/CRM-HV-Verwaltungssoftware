# M23-CAL-01 Kalender-Abo mit persönlichem Token für externe Kalender

| Field | Content |
| --- | --- |
| ID | `M23-CAL-01` |
| Title | Kalender-Abo mit persönlichem Token für externe Kalender |
| Scope | Domäne `communication`, Tabelle `calendar_feed_token`, Recht `tenant_settings:read` |
| Source status | Produktschutz. Externe Kalender können sich nicht anmelden; das Token wirkt wie ein Passwort, nur der Hash wird gespeichert |
| Acceptance case | keine in Anhang D; Test `test_p20_letting_dispatch_w2.py::test_dispatch_channels_serial_merge_and_calendar_feed` |
| Implementation | `mhvp.communication.calendar_feed`, `mhvp.communication.dispatch.build_ics`, `CalendarFeedPanel`, Migration 0269 |
| Change reason | Lückenliste 30.09.2026, Befund M23-06 |

## Regeln

- Je Person höchstens ein aktives Token. Ein neues Token widerruft das alte. Die Adresse wird nur bei der Erzeugung angezeigt.
- Der Feed enthält eigene und geteilte Einträge; abgeleitete Fristen nur, wenn die Person bei Erzeugung die Rechte `contracts:read` und `properties:read` hatte. Unbekannte oder widerrufene Token ergeben 404.
- Der Abruf ohne Anmeldung ist nur lesend und wird mit Zeitpunkt der letzten Nutzung protokolliert.
