# Paket A: Bankverbindung am Kontakt, Vier-Augen-Freigabe, Rolle Freigabe (28.09.2026)

Bezug: `docs/handbuch/README.md`, Abschnitt Lücken in der Software, Zeilen Bankverbindung;
`docs/handbuch/anleitung-bankverbindung.md`; Regel `docs/rules/M3-02-sepa-mandate.md`
(M5-01 und Nachtrag 28.09.2026); `docs/OPEN_QUESTIONS.md` M5-04. Gates G1 bis G5 bleiben
geschlossen; Einzug und Überweisung bleiben hinter G2.

## Ziel

1. Oberfläche, um an einem bestehenden Kontakt eine Bankverbindung hinzuzufügen, als neue
   Version zu ändern (IBAN-Historie bleibt) und zu beenden.
2. Vier-Augen-Prinzip auch für das Beenden bei Rechtsträger-Kontakten (Gemeinschaft,
   Eigentümer, Verwaltung) und bei Vorschlägen von Personen ohne `contacts:approve`; die
   entscheidende Person ist nie die erfassende.
3. Systemrolle Freigabe mit `contacts:approve` und Leserechten, idempotent für bestehende
   Mandanten.

## Umsetzung

- Migration `0225_contact_bank_account_changes.py` (down_revision 0224, umgekettet bei der Integration 29.09.2026):
  `contact_bank_account.replaces_account_id` und Tabelle `contact_bank_account_change`
  (RLS über `tenant_rls_statements`, Status im vorhandenen Enum
  `bank_account_approval_status`, je Konto höchstens eine offene Änderung).
- API (`mhvp.contacts`): `POST /contacts/{id}/bank-accounts`, `.../{konto}/replace`,
  `.../{konto}/end`, `.../{konto}/changes/{änderung}/approve|reject`; bestehender
  Freigabepfad `approve|reject` für die IBAN wiederverwendet. Fehlercodes `MHVP-CONT-0001`
  bis `0003`. Startseite zählt offene Änderungen mit.
- Rolle `approver` (Freigabe) in `mhvp.core.auth.permissions`, nachgezogen durch
  `ensure_system_roles` (Provisionierung, `python -m mhvp.platform.sync_roles`).
- CRM: Reiter Bankverbindungen der Kontaktseite als `BankAccountsSection` mit
  `BankAccountForm` (Hinzufügen, Ändern mit IBAN-Prüfziffer) und `BankAccountActions`
  (Beenden, Bestätigen oder Ablehnen der offenen Änderung); BFF-Freigaben additiv; Texte in
  `de.json` und `en.json`.

## Tests

- `apps/api/tests/integration/test_contact_bank_accounts_crm.py`: Anlegen und Freigabe durch
  die Rolle Freigabe, Ablösung mit festen Sollwerten (alte Zeile endet am 30.09.2026),
  Beenden sofort für Freigeber und als offene Änderung für Sachbearbeiter,
  Rechtsträger-Kontakt immer zweite Person, 403 ohne Recht, 404 fremder Mandant, 409 und 422
  Validierung.
- `apps/web-crm/src/components/contacts/BankAccountForm.test.tsx`,
  `BankAccountActions.test.tsx`, `BankAccountsSection.test.tsx`.

## Offen

Siehe `docs/OPEN_QUESTIONS.md` M5-04: angebundene Bankkonten der Rechtsträger
(`bank_account_assignment`) bleiben ohne Vier-Augen-Freigabe in der Software.
