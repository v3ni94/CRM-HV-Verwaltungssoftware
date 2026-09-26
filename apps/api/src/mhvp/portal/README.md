# mhvp.portal

Portal specific endpoints and access matrix filters.

* Milestone: M21, M22 (docs/MASTER-PROMPT.md section 18).
* Specification: docs/MASTER-PROMPT.md section 6.9.6, 14.
* Status: M21/M22 portal API implemented. See docs/plans/M21.md. Handover protocols of a
  participant (M30 stage 3) live in `mhvp.handover.portal`; their grants (`scope_type`
  `handover`, `legal_basis` `handover_participant`) are manual and survive `access.sync_grants`.

Portal forms (A56): `forms.py` (templates, submissions, pure validation and rendering) and
`form_routers.py` (management under `/portal-admin/forms`, portal under `/portal/forms`); a
submission creates a ticket of the template's category with own uploads as attachments. The
CRM lists the submissions per template (`GET /portal-admin/forms/{id}/submissions`, A73,
tickets:read) with account, contact name and the created ticket; the values stay on the ticket.

Layout once implemented: `models.py`, `schemas.py`, `services.py`, `routers.py`, tests under
`apps/api/tests/portal/`. Register models in `mhvp/models.py` for Alembic autogenerate.

Owner pages, read only (A51, section 14 role owner): `owner.py` serves
`GET /portal/resolutions` (announced resolutions of the own GdWE only), `GET /portal/property-contacts`
(manager display name, caretaker and emergency contacts released for owners, no private numbers)
and `GET /portal/hoa-account` (posted lines of the owner's debtor account in the community's
ledger with balance; note "keine Abrechnung, keine Rechtsfolge"; no ledger means a note and no
amounts). Role owner is required (grant `hoa_member_right`), everyone else gets 403.

Access paths (docs/rules/M21-06.md, D29 to D31): `access.visible_documents` is the single
document filter for portal list and download; `access.document_scope_for_user` applies the same
filter to runs of the AI gateway started on behalf of a portal user; `access.redaction_notes`
marks a released (redacted) version of a receipt, linked to its original with
`entity_type="document"` and role `generated`.

Attachments and appointments (A55, A58, docs/plans/M21.md and M22.md, Nachtrag 26.09.2026):
`_own_uploads` is the single ownership check for portal documents attached to a ticket or a
work order (own portal uploads only, everything else 404); photos are sanitized on upload with
`mhvp.handover.images.sanitize_image`. Appointment proposals of a provider live in
`mhvp.tickets.models.WorkOrderAppointmentProposal`; only the affected resident accepts one.

Read receipts and notices (A53, A54, docs/rules/M21-06.md rules 5 and 6): `read_receipts.py`
records `opened` and `downloaded` per account as an indication only; the CRM reads them via
`GET /documents/{id}/portal-read-receipts`. `notices.py` holds the Schwarzes Brett model,
`notice_routers.py` the CRM maintenance (`properties/{id}/notices`, `notices/{id}`,
`notices/{id}/end`, permission `properties:update`) and the portal view (`GET /portal/notices`,
`GET /portal/notices/{id}/document`): properties of the active grants, matching audience, valid
on the local day; reading writes nothing.


Board audit room (A52, docs/rules/M21-07.md): `board.py` holds the role `board` (grant
`board_audit` per audit engagement, tables `board_access`, `board_audit_note`) and the portal
endpoints under `/portal/board`. The board reads its engagements, positions and the receipts
released through the positions only (`released_document_ids`), and records notes and questions;
the management answers in `mhvp.hoa.board`. No CRM right is granted.

## Further files (addendum 26.09.2026)

Checked against the folder contents on 26.09.2026, the following files were not listed above:

* `staff_access.py`: portal access for staff members per CRM role matrix (M2-08)
