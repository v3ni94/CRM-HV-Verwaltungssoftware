
AJ16 (GAI-411, Welle 21): `ContractMandates.tsx` bietet bei aktiven Mandaten mit contracts:update die Aktion Widerrufen (POST `/sepa-mandates/{id}/revoke`, mit Bestätigung; stoppt den Lastschrifteinzug der Verträge). Messages `BankActions.mandate`. Test in `ContractAllocationValues.test.tsx`.

## SchedulePanel (GAJ-102, W24 AN01)

`SchedulePanel` zeigt die Zahlungspläne aus `contract.schedules` (kein eigener GET nötig) und öffnet je Plan `ScheduleCorrectionForm` (`PATCH /contracts/{id}/schedules/{id}`, nur mit Recht Verträge bearbeiten). Konflikte (409, gebuchte Sollstellungen) werden mit der API-Meldung angezeigt.

- `ContractVersionHistory` (GAK-207, AN18): Versionsverlauf im Vertragsdetail mit Gültigkeit, Link auf Vorversionen und Differenz der Zahlungszeilen.
