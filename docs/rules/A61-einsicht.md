# Einsichtsanfragen außerhalb des Portals (A61, M25-04)

| Field | Content |
| --- | --- |
| ID | A61 |
| Title | Einsichtsanfragen außerhalb des Portals protokollieren |
| Scope | WEG communities (legal entity kind `hoa`); requests by owners or their representatives recorded by staff; documents of the community or its property released for owners (`visibility` contains `owner`) |
| Source status | Produktschutz. Section 14 (phase boundary of the owner portal) and PÜ12, PÜ13 require a substitute process; the access matrix of owners (§ 18 Abs. 4 WEG, annex C) is not implemented as a legal rule. Periods and scope of inspection are an operator decision (docs/OPEN_QUESTIONS.md M25-05); the software never derives a right to inspect from a status |
| Acceptance case | none in annex D; `tests/integration/test_a61_inspection.py` (flow, package reproducible with SHA-256, only released documents, `hoa:update` required, tenant separation); `apps/web-crm/src/components/hoa/InspectionPanel.test.tsx` |
| Implementation | `mhvp.hoa.inspection` (tables `hoa_inspection_request`, `hoa_inspection_event`, migration 0117): status `requested`, `released` (user and time recorded), `provided` (delivery kind portal, data medium, on site; package required except on site), `retrieved` (set by the logged download), `closed`, `rejected` (reason required); one trail row per status change, note, package and retrieval plus a domain event; package `POST /api/v1/hoa/inspection-requests/{id}/package` as deterministic ZIP with `index.json` and `index.csv` (file name, category, date, SHA-256), stored as document linked to the request and the community; permission resource `hoa` (`read`, `update`) |
| Change reason | Gap list A61, 26.09.2026 |
