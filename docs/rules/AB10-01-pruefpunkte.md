# AB10-01 Prüfpunkte pflegen (Welle 16, AE19)

- ID: AB10-01. Geltungsbereich: Mandant, Regelregister (Gruppe Prüfpunkt), Hinweis ohne Rechtsfolge.
- Funktion: Prüfpunkte mit Datum, Bezeichnung, Quelle und Notiz anlegen (`POST /accounting/rule-versions/checkpoints`), ändern solange offen (`PATCH .../{id}`), zurückziehen (`POST /accounting/rule-versions/{id}/withdraw`), auflisten mit Stand (`GET .../checkpoints?state=&lead_days=&on=`). Stände: offen, in Vorfrist (Standard 30 Tage), fällig, bestätigt, zurückgezogen.
- Es gibt keine vorbelegten Fristen. Fristen, Daten und Wortlaut sind vor Eintrag amtlich zu prüfen (Fristen als zu verifizieren kennzeichnen); der Eintrag sperrt nichts und ändert keine Rechenregel.
- Quellenstatus Anhang C: Fachliche Umsetzung. Abnahmefall: tests/integration/test_ae19_checkpoints_compare.py. Änderungsgrund: Prioritätenliste Punkt 19, OPEN_QUESTIONS AB10-01.
