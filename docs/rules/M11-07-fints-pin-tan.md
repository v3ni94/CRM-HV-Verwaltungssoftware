# M11-07 FinTS PIN/TAN: Zugangsdaten verschlüsselt, keine Wiederholung nach Fehlversuch, nur lesend

| Field | Content |
| --- | --- |
| ID | `M11-07` |
| Title | FinTS/HBCI PIN/TAN als zweite Bankanbindung: Zugangsdaten verschlüsselt und nie ausgegeben, keine automatische Wiederholung mit derselben PIN, erneute Freigabe nach 90 Tagen, nur lesend |
| Scope | Domäne `banking`, Tabellen `fints_connection`, `fints_account_link`, `bank_fints_session`; alle Mandanten; Konnektor `fints` |
| Source status | Produktschutz. PSD2-Regel (starke Kundenauthentifizierung spätestens alle 90 Tage) und das Sperrverhalten der Banken (drei Fehlversuche) sind bankseitige Vorgaben, keine Norm aus dem Quellenregister; die Umsetzung setzt keine Rechtsfolge, sondern schützt den Zugang |
| Acceptance case | D05 (Dubletten), Tests `apps/api/tests/unit/test_fints.py`, `apps/api/tests/integration/test_m11_fints.py`, `apps/web-crm/src/components/banking/FinTsConnections.test.tsx` |
| Implementation | `mhvp.banking.fints`, `mhvp.banking.fints_routers`, `mhvp.banking.tasks.fints_step`, Migration 0161, Fehlercodes MHVP-BANK-0007 bis 0016, `docs/integrations/fints.md` |
| Change reason | Betreiberentscheidung 27.09.2026 (M11-01 Nachtrag): FinTS direkt zusätzlich zu finAPI |

## Regeln

- Anmeldename, PIN und der python-fints-Client-Zustand liegen verschlüsselt (Master-Key);
  keine API-Antwort und kein Protokoll enthält die PIN oder eine TAN. Regel M11-05
  (Zugangsdaten nie im CRM) wird für FinTS bewusst durchbrochen, weil der Betreiber den
  direkten Zugang gewählt hat; Ausgleich ist die Verschlüsselung, die Trennung je
  Mandant (RLS) und das Löschen beim Trennen.
- Nach einer Ablehnung von Anmeldename oder PIN wird die gespeicherte PIN verworfen und
  nicht automatisch erneut verwendet (Bank sperrt nach drei Fehlversuchen); der nächste
  Versuch verlangt eine neue Eingabe (`MHVP-BANK-0016`).
- Jeder Abruf ist ein Klick und kann eine TAN verlangen; es gibt keinen Zeitplan. Nach
  90 Tagen ist eine erneute Freigabe zu erwarten (Anzeige "Freigabe gültig bis").
- Umsätze werden nur für Konten übernommen, die einem internen Konto mit gleicher IBAN
  zugeordnet sind; die Dublettenregel des Dateiimports gilt unverändert (Bankreferenz
  vorrangig, Inhalts-Hash nur als Hinweis, D05).
- Nur lesend: keine Zahlung, keine Lastschrift, G2 bleibt geschlossen.
- Ohne DK-Produktregistrierung (`MHVP_FINTS_PRODUCT_ID`) ist keine Verbindung möglich
  (`MHVP-BANK-0007`).

## Änderung Welle 16 (AE26, 01.10.2026)

| Field | Content |
| --- | --- |
| Change reason | Betreiberbefund 01.10.2026: Bankzugang gesperrt (`MHVP-BANK-0010`) erschien als englischer Bibliothekstext ohne nächsten Schritt; Bankfusionen ändern die FinTS-Adresse, ohne dass die Institutsliste sofort folgt |
| Acceptance case | `apps/api/tests/unit/test_ae26_fints_hints.py`, `apps/api/tests/unit/test_ae26_fints_institutes_script.py`, `apps/api/tests/integration/test_ae26_fints_url.py`, `FinTsConnections.test.tsx` |
| Implementation | `mhvp.banking.fints` (`locked_detail`, `unavailable_detail`, `validate_manual_fints_url`, `resolve_fints_url`), `PATCH /banking/fints/connections/{id}`, Migration 0382 (`fints_connection.fints_url_manual`), `scripts/update_fints_institutes.py` |

- Die Meldungen zu `MHVP-BANK-0010` und `MHVP-BANK-0013` sind deutsch und nennen
  nummerierte Prüfschritte (Online-Banking testen, Freischaltung für FinTS, Anmeldename,
  Entsperrung bei der Bank, danach PIN neu eingeben; bei Nichterreichbarkeit zusätzlich die
  kontaktierte Adresse, Bankfusion, neue Adresse, Firewall). Der englische Text von
  python-fints wird nicht mehr als Meldung ausgegeben. Netzwerkfehler der Bibliothek
  `requests` (SSL, Zeitüberschreitung) und von python-fints umhüllte Verbindungsfehler führen
  zu `MHVP-BANK-0013`; ein nicht erreichbarer Server verwirft die gespeicherte PIN nicht.
  Dieselbe Behandlung gilt für die englischen Bibliothekstexte zu `MHVP-BANK-0009` (PIN
  abgelehnt) und `MHVP-BANK-0012` (erneute Freigabe nötig): kurze deutsche Meldung mit dem
  nächsten Schritt.
- Je Verbindung kann eine FinTS-Adresse von Hand eingetragen werden (`fints_url_manual`,
  Produktschutz). Reihenfolge der verwendeten Adresse: manuell, sonst Eintrag der aktuellen
  Institutsliste zur Bankleitzahl, sonst die beim Anlegen gespeicherte Adresse. Die Adresse
  muss mit `https://` beginnen, einen öffentlichen Rechnernamen tragen (keine IP-Adresse, kein
  `localhost`, keine interne Domain) und darf keine Zugangsdaten enthalten.
- Mit einer neuen Adresse wird die PIN erneut eingegeben und ersetzt die gespeicherte, damit
  sie nie ohne Zutun an eine neue Adresse geht. Die Änderung startet keinen Anmeldeversuch (ein
  Fehlversuch kann den Zugang sperren), verwirft die zwischengespeicherten Bankparameter und
  den letzten Fehler und wird als Ereignis `fints_connection.url_changed` (nur Rechnernamen)
  festgehalten. Recht `banking:approve`.
- Die Institutsliste wird mit `scripts/update_fints_institutes.py` aus der DK-Datei
  aktualisiert (Trockenlauf als Standard, URLs werden nie stillschweigend entfernt, Zeilen
  ohne DK-Eintrag bleiben unverändert).
