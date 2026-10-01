# Regel M11-08: Erneuerung der Aggregator-Zustimmung

* ID: M11-08
* Geltungsbereich: Mandant, Banking, finAPI (`mhvp.banking.finapi`, `mhvp.banking.tasks`).
* Quellenstatus: Spezifikation 8.2 (Erinnerung 10 Tage vor Ablauf) als Fachliche Umsetzung; Feldname des Ablaufdatums ist Annahme A-M11-08-01 (M11-41, T03-02).
* Regel: Beim Prüfen der Verbindung wird das Ablaufdatum aus der Anbieterantwort gelesen (frühestes Datum, nichts wird geschätzt; ohne Lieferung bleibt ein manuelles Datum). Der tägliche Job erinnert 10 Tage vorher je Ablaufdatum einmal als Benachrichtigung und legt genau eine interne Aufgabe (Ticketkategorie task, zugewiesen an den ersten Buchhaltungsnutzer, Fälligkeit am Ablauftag) an. Abgelaufen: Status consent_expired. Die Erneuerung selbst ist eine Handlung der Person im WebForm der Bank. Das CRM zeigt je Verbindung dauerhaft das Datum oder den Hinweis, dass keines vorliegt.
* Abnahmefall: Anhang D (Zustimmungserinnerung A29); Tests `test_t03_bank_raw_consent.py`, `test_m11_finapi.py`.
* Änderungsgrund: Lückenliste 30.09.2026, M11-08.
