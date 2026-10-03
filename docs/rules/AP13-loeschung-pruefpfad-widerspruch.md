# AP13-loeschung-pruefpfad-widerspruch

- ID: AP13-loeschung-pruefpfad-widerspruch
- Geltungsbereich: Kontaktlöschung (privacy/erasure), Prüfpfad audit_log, Löschprofile, Einwilligungsregister, KI-Gateway
- Quellenstatus (Anhang C): keine freigegebene Quelle; alle Varianten sind technische Vorbereitung, Entscheidungen offen (OPEN_QUESTIONS AP13-01 bis AP13-04, V17)
- Abnahmefall (Anhang D): offen, Testnachweis `apps/api/tests/integration/test_ap13_privacy_erasure.py`
- Änderungsgrund: Befunde GAM-401, GAM-404, GAM-405, GAM-406 (Welle 26)

## Regeln

1. Schalter `privacy.audit_redaction` (Standard aus): eingeschaltet reduziert die Anonymisierung eines Kontakts (Ausführung und Wiederholung aus dem Löschjournal) die audit_log-Zeilen dieses Kontakts auf Feldnamen, jeder Wert wird `{"redacted": true}`. Die Datenbank erlaubt nur genau diese Änderung an Kontaktzeilen; Löschen, Leeren und jede andere Änderung bleiben gesperrt. Ereignisse, Buchungen und andere Beweisdaten bleiben unverändert (B03).
2. Schalter `privacy.erasure_coupling` (Standard aus): eingeschaltet sperren Bezüge aus message, call_log, dispatch und postal_job die Kontaktlöschung nicht mehr; sie erscheinen als Hinweis `coupled_communication` und im Ergebnis als `coupled`. Die Zeilen selbst werden nicht gelöscht. Alle anderen Bezüge sperren weiter.
3. Löschprofile kennen zusätzlich die Datenarten ai_run, call_log, webhook_delivery, postal_job; die Vorschau zählt nur, keine Frist ist vorbelegt (V17).
4. Einwilligungsarten `sms` und `ai_processing`, Zwecke im Register ohne Vorbelegung. Eine gültige Einwilligung erlaubt, ein eingetragener Widerspruch sperrt; ohne Registereintrag wird sonst nichts geprüft. KI-Läufe mit `contact_id` oder `contact_ids` im input_ref enden bei Widerspruch im Status blocked.
