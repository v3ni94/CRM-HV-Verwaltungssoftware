# U09 Rechnungseinreichung des Dienstleisters (M22-02)

- ID: U09-R01 bis U09-R03
- Geltungsbereich: Portal (Rechnung einreichen) und Belegeingang (receipts), Annahme in `/portal/change-requests/{id}/decide`.
- Quellenstatus Anhang C: keine Rechtsnorm betroffen; Fachliche Umsetzung und Produktschutz. Keine steuerliche Einordnung, der USt-Satz ist die Angabe des Dienstleisters.
- Regeln:
  - U09-R01: Optional eingereichte Werte Netto, USt-Satz und IBAN werden geprüft (Netto höchstens Brutto, Netto plus USt gleich Brutto mit Toleranz von 0,01 EUR bei angegebenem Satz, IBAN mit Prüfziffer, sonst 422). Ohne Netto, aber mit Satz wird das Netto aus dem Brutto abgeleitet. Die Werte gehen unverändert in den Belegentwurf (Quelle portal, Status proposed), die IBAN verschlüsselt als Kandidat.
  - U09-R02: IBAN-Abgleich mit den gültigen Bankverbindungen des Dienstleisters im Kreditorenstamm (Fingerprint) als Befund: übereinstimmend, abweichend oder ohne Stammdatum. Eine Abweichung sperrt nichts, kennzeichnet den Entwurf aber; die Übernahme einer IBAN bleibt an die ausdrückliche Bestätigung im Belegeingang gebunden.
  - U09-R03: Duplikatprüfung gegen das Rechnungsbuch: gleicher Aussteller mit gleicher Nummer (beim Einreichen 409, wie bisher) oder gleichem Datum und Bruttobetrag (Befund am Entwurf). Statuswechsel des Auftrags auf invoiced bei Annahme (aus Q11 unverändert).
- Abnahmefall: `apps/api/tests/integration/test_u09_invoice_submission.py`.
- Änderungsgrund: Lückenliste 30.09.2026, M22-02 Rest. Keine Buchung, keine Zahlung (Gates G1, G2 geschlossen).
