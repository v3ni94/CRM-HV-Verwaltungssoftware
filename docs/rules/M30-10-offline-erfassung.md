# M30-10 Übergabeprotokoll: Offline Erfassung mit verschlüsselter Warteschlange auf dem Gerät (Produktschutz)

| Field | Content |
| --- | --- |
| ID | `M30-10` |
| Title | Änderungen und Fotos des Übergabeprotokolls dürfen ohne Verbindung verschlüsselt auf dem Gerät warten und werden nach Wiederherstellung der Verbindung in der Reihenfolge der Erfassung übertragen; der Server bleibt die einzige Stelle, die entscheidet, was gespeichert wird; Gerätezeiten sind gemeldete Werte, nie Beweis |
| Scope | Domäne `handover`, CRM Editor `HandoverEditor.tsx` mit `components/handover/offline/*`; Tabellen `tenant_settings.handover_offline_enabled`, `handover_client_write` (neu), `captured_at` an `handover_participant`, `handover_meter`, `handover_room`, `handover_defect`, `handover_key`, `handover_item`, `handover_note`, `signed_at_device` an `handover_signature`; alle Mandanten, nur Mitarbeiter im CRM (Portal bleibt online only); Schalter je Mandant, Standard aus |
| Source status | Keine Rechtsnorm im Quellenregister (annex C) einschlägig. Betreiberentscheidung 28.09.2026 (vollständig offline) mit den Datenschutzauflagen aus ADR 0016 als Produktschutz. Die rechtliche Bewertung digitaler Unterschriften und verzögerter Übertragungen bleibt M30-02 |
| Acceptance case | keine in annex D; Tests `apps/api/tests/integration/test_m30_handover_offline.py::test_offline_queue_replay` (feste Erwartung: Schalter aus antwortet 403 MHVP-HDOV-0003, Schalter an speichert `captured_at` gleich Gerätezeit und `created_at` später, gleicher Schlüssel liefert dieselbe Antwort ohne zweite Zeile, abgeschlossenes Protokoll antwortet 409 mit dem Sperrhinweis, älterer Basisstand antwortet 409 MHVP-HDOV-0004 mit dem Serverstand, Leserecht 403, fremder Mandant 404), `apps/web-crm/src/components/handover/offline/queue.test.ts` (kein Klartext im Speicher, Reihenfolge, Dublette je Schlüssel, Löschung bei Abmeldung, verlorener Schlüssel verwirft die Datensätze), `OfflineBanner.test.tsx`, `HandoverEditorOffline.test.tsx` |
| Implementation | Server: `mhvp.handover.routers` (`ClientWrite`, `_replayed`, `_require_offline_allowed`, `_require_base_current`, `_record_write`; Header `X-Handover-Client-Key`, `X-Captured-At`, `X-Base-Updated-At` an PATCH Protokoll, POST, PATCH und DELETE Teildatensatz, POST Dokument, POST Unterschrift), `mhvp.handover.models.HandoverClientWrite`, `mhvp.handover.pdf` (Gerätezeit der Unterschrift), `mhvp.platform` (Schalter), Migration 0245, Fehlercodes MHVP-HDOV-0003 und MHVP-HDOV-0004. Client: `offline/crypto.ts` (AES-GCM, Schlüssel nur im Speicher), `offline/store.ts` (IndexedDB, nur Kennung und Folgenummer im Klartext), `offline/queue.ts`, `offline/apply.ts`, `offline/sync.ts`, `offline/useHandoverOffline.ts`, `OfflineBanner.tsx`, `SyncPanel.tsx`, `settings/HandoverOfflineSwitch.tsx` |
| Change reason | Betreiberentscheidung 28.09.2026 zu M30-07: vollständig offline statt online only mit Hinweis (M31 WP2) |

## Regeln

- Schalter: `tenant_settings.handover_offline_enabled` (Standard aus, Änderung über
  `PATCH /tenant/settings` mit `tenant_settings:update`, Ereignis `tenant_settings.updated`).
  Ohne den Schalter speichert der Editor nichts auf dem Gerät und zeigt nur den Hinweis
  Keine Verbindung mit Erneut senden; der Server weist jeden Eintrag mit `X-Captured-At`
  mit 403 MHVP-HDOV-0003 ab, auch aus Integrationen (Regel 0.1.4).
- Warteschlange: Änderungen (Protokollfelder, Teildatensätze anlegen, ändern, löschen,
  verkleinerte Fotos und Anhänge, Unterschriften) werden ohne Verbindung oder bei nicht
  erreichbarer API in der Reihenfolge der Erfassung mit eigener Kennung, Folgenummer und
  Gerätezeit (`capturedAt`, ISO 8601 mit Zeitzone) in IndexedDB abgelegt. Solange etwas
  wartet, wartet jede weitere Änderung des Protokolls dahinter (Reihenfolge). Die Ansicht
  zeigt die Serverkopie plus die wartenden Änderungen mit der Kennzeichnung Wartet auf
  Abgleich; Fotos ohne Vorschau. Das Löschen von Fotos und Unterschriften, Abschluss,
  Storno, Versionen und Zustellung bleiben online only.
- Verschlüsselung: AES-GCM 256 mit einem Schlüssel, der je Anmeldung im Speicher der Seite
  erzeugt wird (nicht exportierbar, nie in Storage, nie übertragen). Im Speicher stehen im
  Klartext nur die zufällige Kennung und die Folgenummer; Protokollnummer, Namen, Adressen,
  Fotos und Unterschriftsbilder liegen im verschlüsselten Teil. Der Service Worker
  (`public/sw.js`) cached weiterhin nur die Offline Seite und die Symbole, nie
  API Antworten, Fotos oder Protokolldaten.
- Löschung: die Warteschlange wird gelöscht bei Abmeldung und Sitzungsende (Antwort 401,
  Entladen der Seite), nach erfolgreicher Übertragung je Protokoll und durch die Aktion
  Lokale Entwürfe löschen. Einschränkung: ein Neuladen der Seite ohne Verbindung verwirft
  den Schlüssel; die verbliebenen Datensätze sind unlesbar, werden beim nächsten Lesen
  gelöscht und als verworfen angezeigt. Eine Passphrase wurde verworfen (auf einem
  geteilten Tablet schwächer als der Speicherschlüssel und ohne Speicherung nicht
  hilfreich).
- Übertragung: bei Verbindung werden die Einträge in Reihenfolge mit den Headern
  `X-Handover-Client-Key` (Kennung), `X-Captured-At` (Gerätezeit) und, bei Änderungen
  bestehender Zeilen, `X-Base-Updated-At` (Stand der Serverkopie) gesendet. Kennungen
  offline angelegter Einträge werden auf die Serverkennung abgebildet (auch Verweise wie
  `room_id`). Der Server prüft alle Regeln unverändert (Rechte, RLS, M30-01, M30-09):
  ein abgeschlossenes Protokoll antwortet 409 mit dem Sperrhinweis, eine gesperrte
  Fassung 409 mit dem Hinweis auf Änderung nach Unterschrift. Jede Abweisung hält die
  Übertragung an; die übrigen Einträge bleiben auf dem Gerät.
- Dublette je Schlüssel: nur angenommene Schreibvorgänge werden mit ihrer Antwort in
  `handover_client_write` gespeichert (RLS, eindeutig je Mandant und Schlüssel, ohne
  Ablauf); ein erneuter Aufruf mit demselben Schlüssel liefert die gespeicherte Antwort
  und schreibt nichts. Abweisungen werden nicht gespeichert, damit ein später
  freigegebener Schalter oder eine neue Fassung nicht an einer alten Antwort scheitert.
  Der eigene Header ist bewusst nicht `Idempotency-Key` (die allgemeine Middleware
  `mhvp.core.idempotency` spielt 24 Stunden auch Abweisungen zurück).
- Konflikt: ist die Serverzeile jünger als `X-Base-Updated-At`, antwortet der Server 409
  MHVP-HDOV-0004 mit dem Serverstand in der Erweiterung `server`. Die Oberfläche zeigt
  beide Stände mit der Gerätezeit und fragt: Serverstand behalten (Eintrag verwerfen) oder
  Meine Änderung übernehmen (erneut ohne Basisstand senden). Nichts wird automatisch
  entschieden.
- Gerätezeiten: `captured_at` an Teildatensätzen und `signed_at_device` an Unterschriften
  sind vom Gerät gemeldete Werte; `created_at` und `signed_at` bleiben die Serverzeit der
  Übertragung. Das PDF druckt bei Unterschriften beide mit dem Hinweis vom Gerät gemeldet.
  Die Ereignisse `handover.*` tragen `captured_at` und `idempotency_key` zusätzlich.
- Abgleichsprotokoll: je Protokoll führt der Editor ein Protokoll der Übertragung
  (Zeitpunkt, Art, Gerätezeit, Ergebnis übertragen, Konflikt, abgelehnt, keine Verbindung,
  verworfen, erneut eingereiht) nur im Speicher der Sitzung.
