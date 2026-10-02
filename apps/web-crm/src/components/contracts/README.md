
AJ16 (GAI-411, Welle 21): `ContractMandates.tsx` bietet bei aktiven Mandaten mit contracts:update die Aktion Widerrufen (POST `/sepa-mandates/{id}/revoke`, mit Bestätigung; stoppt den Lastschrifteinzug der Verträge). Messages `BankActions.mandate`. Test in `ContractAllocationValues.test.tsx`.
