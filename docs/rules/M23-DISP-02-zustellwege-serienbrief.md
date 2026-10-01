# M23-DISP-02 Zustellwege Post mit Postauftrag, SMS, Einschreiben, Bote und Serienbrief aus Vorlage

| Field | Content |
| --- | --- |
| ID | `M23-DISP-02` |
| Title | Zustellwege Post mit Postauftrag, SMS, Einschreiben, Bote und Serienbrief aus Vorlage |
| Scope | Domäne `communication`, Tabelle `dispatch`, Rechte `communication:create`, `communication:update`, für Serienbriefe zusätzlich `documents:create` |
| Source status | Fachliche Umsetzung (11.3, 13.5). Es gibt keinen SMS-Anbieter und keinen Einschreibeanbieter; diese Wege werden vorbereitet und mit Nachweis erfasst. Die Plattform versendet nichts selbst |
| Acceptance case | keine in Anhang D; Test `test_p20_letting_dispatch_w2.py::test_dispatch_channels_serial_merge_and_calendar_feed` |
| Implementation | `mhvp.communication.dispatch` (`CHANNELS`, `CHANNEL_EVIDENCE`, `submit_postal`, `POST /dispatches/serial-merge`), `DispatchPanel`, `SerialDispatchForm` |
| Change reason | Lückenliste 30.09.2026, Befunde M23-02, M23-03, M23-05 |

## Regeln

- Zustellwege: post, email, portal, sms, registered (Einschreiben), courier (Bote). SMS verlangt eine Telefonnummer am Kontakt.
- Kanal post mit `submit_postal` legt den Postauftrag im selben Schritt an. Freigabe des Postdienstes und Recht `communication:approve` bei externem Anbieter gelten unverändert.
- Zugang (`delivered`) braucht Nachweisart und Referenz. Je Weg sind nur passende Nachweisarten zulässig: Einschreiben nur Einschreiben oder Sonstiges, Bote nur Botenquittung, Übergabe oder Sonstiges, SMS nur SMS Protokoll oder Sonstiges.
- Serienbrief aus Vorlage: je aufgelöstem Empfänger (Vertreterregel) ein eigenes Dokument mit den Platzhaltern der Vorlage, abgelegt und verknüpft wie ein Einzelbrief, dazu eine Zustellung. Ein Fehler (fehlende Anschrift, Platzhalter) bricht den ganzen Lauf ab, es entsteht kein halber Lauf.

## Nachtrag 30.09.2026 (Q14, M23-05)

- Kanal `post` legt den Postauftrag jetzt automatisch an (`submit_postal` leer oder `true`; `false` unterdrückt).
  Ohne Freigabe eines externen Postdienstes oder ohne Recht `communication:approve` bleibt die Zustellung
  vorbereitet und der Auftrag entsteht über `POST /postal/jobs`; die Sperren des Postmoduls gelten unverändert.
  Mit dem Anbieter manuell entsteht ein manueller Auftrag ohne externen Versand.
