# M9-06 Dienstleisterverträge in der Fristenliste (A41)

Bezug: `docs/OPEN_QUESTIONS.md` M9-06, MASTER-PROMPT Abschnitt 15.1 (Fristenliste), Plan `docs/plans/M9.md`.

## Ziel

Verträge mit Dienstleistern (Hausmeister, Wartung, Reinigung und ähnliche) mit Laufzeit, Kündigungsfrist und automatischer Verlängerung erfassen und den spätesten Kündigungstermin in die Fristenliste aufnehmen.

## Umsetzung

- Modell `ServiceContract`, Tabelle `service_contract` (`apps/api/src/mhvp/contracts/service_contracts.py`): Mandant, `provider_contact_id` (Kontakt), `property_id` optional, `title`, `starts_at`, `ends_at` optional, `notice_period_days` (Anzahl) mit `notice_period_unit` (`days` oder `months`), `auto_renewal_months` optional, `cancelled_at` optional, `notes`.
- Migration `0122_service_contract.py`, `down_revision` 0121, RLS über `tenant_rls_statements()` wie die Vorgänger.
- Endpunkte `/api/v1/service-contracts` (Liste, Anlegen, Lesen, Ändern, Löschen) in `service_contract_routers.py`. Rechte: `contracts:read`, `contracts:create`, `contracts:update`, `contracts:delete` (Löschen nur Administrator, M2-07). Ereignisse `service_contract.created`, `.updated`, `.deleted`.
- Berechnete Felder `next_possible_end` und `latest_notice_date` mit `orientation_only: true`.
- Fristenliste: Typ `service_contract_notice`, Bezug "Kündigungsfrist Dienstleistervertrag <Titel>", feste Vorfrist 14 Tage (`DEADLINE_LEAD_DAYS`), Rechte wie Verträge. Gekündigte Verträge erzeugen keinen Eintrag; offene Einträge schließt der Tagesjob.
- Oberfläche: Seite `/dienstleistervertraege` (Navigation Verwaltung) mit Liste und Formular, Typ in der Fristenliste, BFF-Freigaben, Texte in `de.json` und `en.json`.

## Orientierungsberechnung

Keine rechtliche Fristberechnung (M1-09). Regeln:

1. Monatsfristen werden kalendermonatlich vom Vertragsende zurückgerechnet. Ist das Vertragsende ein Monatsletzter, ist der Kündigungstermin ebenfalls ein Monatsletzter (Ende 30.06., drei Monate, Termin 31.03.). Sonst wird der Tag auf das Monatsende begrenzt.
2. Ohne Vertragsende ist der Vertrag unbefristet: nächstmögliches Ende heute plus Kündigungsfrist, kein fester Kündigungstermin.
3. Mit automatischer Verlängerung verschiebt sich das Ende um die Verlängerungsmonate, solange der Kündigungstermin vor dem Stichtag liegt.
4. Gekündigt: Ende ist das erste Vertragsende, dessen Kündigungstermin nicht vor dem Kündigungsdatum liegt; kein weiterer Kündigungstermin.

## Tests

`apps/api/tests/unit/test_m9_service_contracts.py` (Monatsende, Verlängerung, gekündigt, unbefristet, abgelaufen), `apps/web-crm/src/components/contracts/ServiceContracts.test.tsx`.

## Offen

- Integrationstest der Endpunkte und des Tagesjobs gegen PostgreSQL (RLS, Rechte) steht aus.
- Migrationsnummer 0122 setzt beim Zusammenführen am 26.09.2026 auf 0121 auf (ursprünglich 0110 auf 0108).
- Fachliche Freigabe der Monatsende-Regel durch den Betreiber.
