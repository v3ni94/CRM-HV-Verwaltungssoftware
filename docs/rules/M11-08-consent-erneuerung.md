# Regel M11-08: Erneuerung der Aggregator-Zustimmung

* ID: M11-08
* Geltungsbereich: Mandant, Banking, finAPI (`mhvp.banking.finapi`, `mhvp.banking.tasks`).
* Quellenstatus: Spezifikation 8.2 (Erinnerung 10 Tage vor Ablauf) als Fachliche Umsetzung; Feldname des Ablaufdatums ist Annahme A-M11-08-01 (M11-41, T03-02).
* Regel: Beim Prüfen der Verbindung wird das Ablaufdatum aus der Anbieterantwort gelesen (frühestes Datum, nichts wird geschätzt; ohne Lieferung bleibt ein manuelles Datum). Der tägliche Job erinnert 10 Tage vorher je Ablaufdatum einmal als Benachrichtigung und legt genau eine interne Aufgabe (Ticketkategorie task, zugewiesen an den ersten Buchhaltungsnutzer, Fälligkeit am Ablauftag) an. Abgelaufen: Status consent_expired. Die Erneuerung selbst ist eine Handlung der Person im WebForm der Bank. Das CRM zeigt je Verbindung dauerhaft das Datum oder den Hinweis, dass keines vorliegt.
* Abnahmefall: Anhang D (Zustimmungserinnerung A29); Tests `test_t03_bank_raw_consent.py`, `test_m11_finapi.py`.
* Änderungsgrund: Lückenliste 30.09.2026, M11-08.

## Nachtrag Y02: täglicher Abgleich beim Anbieter (T03-02, technisch)

* Regel: Der Beat-Job `mhvp.banking.consent_provider_sync` (täglich 07:00, vor den Erinnerungen um 07:05) liest je finAPI-Verbindung die Bankverbindung beim Anbieter und wertet sie mit `parse_consent_valid_until` aus. Geschrieben wird nur, wenn der Anbieter ein Datum liefert, das vom gespeicherten abweicht (Ereignis `banking.consent_synced` mit vorher und nachher). Liefert er keines, bleibt das gespeicherte (auch manuelle) Datum; ein Anbieterfehler wird gezählt und bricht die übrigen Verbindungen nicht ab. Ein erneuertes Datum hebt den Status consent_expired wieder auf. Erinnerung und Aufgabe laufen unverändert über `remind_consent_expiry`.
* Schalter: je Mandant in `tenant_settings.sources["bank_consent_sync"]["enabled"]`, Standard aus, ohne Migration; API `GET/PUT /banking/consent-sync/settings` (Schreiben mit `tenant_settings:update`), CRM unter Einstellungen, Bank.
* Quellenstatus: Produktschutz. Der Feldname beim Anbieter bleibt Annahme A-M11-08-01; der Betrieb gegen den Produktivzugang setzt die Bestätigung aus T03-02 voraus. Das Gate bleibt unberührt, es werden nur Metadaten der Verbindung gelesen, keine Umsätze.
* Abnahmefall: `tests/integration/test_y02_consent_sync.py` (Schalter, Berechtigung, Mandantentrennung, Schreiben nur bei Änderung, Fehlerfall, Erinnerung aus abgeglichenem Datum).
* Änderungsgrund: T03-02, Paket Y02 Welle 10.
