# M12-S10 Wochendigest Stufe L3 und Kopplung an die Bankabstimmung B09

- **ID:** M12-S10 (Befund M12-02 der Lückenliste 30.09.2026, Plan M12 Schritt S10)
- **Geltungsbereich:** Automatikbuchungen der Stufe L3 (Klassen `debtor_full`, `transfer_pair`)
  je Mandant und Rechtsträger. Keine Wirkung auf L0 bis L2.
- **Quellenstatus (Anhang C):** Produktschutz, keine Rechtsgrundlage. Abgeleitet aus 7.4 Nr. 4
  (Nachkontrolle Pflicht, Automatisierungsquote ist Kennzahl, kein Sicherheitsnachweis) und
  7.1 B09 (Bankkontoabstimmung). Die Stichprobe als Nachkontrolle im internen Kontrollsystem
  bleibt Betreiberentscheidung mit Steuerberatung (Gate G1).
- **Regel:**
  1. Montags wird je Rechtsträger mit Automatikbuchungen der Vorwoche ein Wochendigest
     erzeugt (`auto_posting_digest`, Job `mhvp.banking.weekly_digest`): Anzahl automatisch
     gebucht, Stichproben, offene Stichproben, Befunde (korrigiert oder storniert) und das
     Ergebnis der Bankabstimmung des Vormonats der beteiligten Konten.
  2. Die Abstimmung gilt als ohne Differenz, wenn jedes beteiligte Konto mindestens einen
     Auszug mit Abschluss im Vormonat hat, jeder dieser Auszüge aufgeht (Anfangssaldo plus
     Bewegungen gleich Endsaldo) und, soweit ein Sachkonto verknüpft ist, der Kontosaldo
     übereinstimmt.
  3. Bestätigung durch eine Person mit `accounting:review`; abgelehnt mit `MHVP-BANK-0028`,
     solange eine Stichprobe offen ist oder die Abstimmung eine Differenz zeigt.
  4. Solange ein Digest einer früheren Woche unbestätigt ist, sperrt der Runner die
     Stichprobenklassen auf L3 (keine Automatikbuchung); L2 bleibt unberührt.
- **Abnahmefall:** `tests/integration/test_p09_banking_sync_digest.py::test_run_metrics_digest_confirmation_and_l3_block`,
  `tests/unit/test_banking_p09_units.py::test_digest_helpers`. Fachliche Abnahme durch den
  Betreiber offen.
- **Änderungsgrund:** Lückenliste 30.09.2026, Befund M12-02 (Digest und B09-Kopplung fehlten).
