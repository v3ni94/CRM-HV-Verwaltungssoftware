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
