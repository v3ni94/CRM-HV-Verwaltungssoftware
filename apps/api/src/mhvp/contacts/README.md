# mhvp.contacts

Contacts, addresses, channels, identifiers, bank accounts, parties, consents, portal accounts.

* Milestone: M3 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.1.
* Status: not implemented. Package reserved by the repository layout of section 17.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/contacts/`. Register models in `mhvp/models.py` for Alembic autogenerate.

## Further files (addendum 26.09.2026)

Checked against the folder contents on 26.09.2026, the following files were not listed above:

* `validation.py`: normalisation and validation of contact data (IBAN per ISO 13616, phone numbers E.164)

## Performance (Review 26.09.2026)

`services.summaries` loads primary email, phone, city, tags and types of a page in one
UNION ALL statement; `GET /parties` loads the members of all parties in one query
(`_parties_out`). Index `contact(tenant_id, display_name)` for the list ordering (migration
0127). Measurements in `docs/reviews/2026-09-26-performance.md`.
