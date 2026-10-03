# GAJ-401 Foto beim Zählerstand im Portal

- ID: GAJ-401-zaehlerfoto
- Geltungsbereich: `POST /portal/meter-readings`, Vorschlagsprüfung am Kontakt (CRM), Portalformular Zählerstand.
- Regelart: Produktschutz (keine Rechtsgrundlage behauptet).
- Inhalt: Mandantenschalter `portal_feature_setting.meter_photo_mode` (Migration 0451). `off`: kein Foto erwartet, kein Kennzeichen. `hint` (Standard, Verhalten vor 0451): Meldung ohne Foto wird angenommen, Vorschlag mit `photo_missing: true` und Hinweis. `required`: Meldung ohne eigenes Foto wird mit 422 `MHVP-PORTAL-0003` abgelehnt, nichts wird gespeichert.
- Quellenstatus (Anhang C): keine Norm; Abschnitt 14 "Zählerstand mit Foto melden".
- Abnahmefall: tests/integration/test_an02_meter_photo_mode.py; Anhang D ohne eigenen Fall.
- Entscheidung: AM06-01 offen (Betreiber); der Standard bleibt hint.
- Änderungsgrund: Welle 24, AN02 (gespeicherter Schalter statt Code-Vorgabe).
