"""Property assignment of the membership in the WEG routers (M2-02/S16-02, Q13-01).

Path ids of WEG records resolve to the property through the legal entity (GdWE) or the
ledger; outside ``Membership.property_ids`` the endpoint answers 404 before it runs.
Produktschutz, not a legal duty; next to tenant RLS and the legal entity scope (A37).
"""

from typing import Any

from mhvp.accounting.models import Ledger
from mhvp.core.auth.scope import property_column_guard
from mhvp.hoa.models import (
    AuditEngagement,
    EconomicPlan,
    HoaAssetReport,
    HoaInsuranceClaim,
    HoaLoan,
    HoaMeasure,
    HoaStatement,
    Meeting,
    Resolution,
    SpecialLevy,
)
from mhvp.properties.models import LegalEntity

HOA_COLUMNS: dict[str, Any] = {
    # query parameters of the lists "einer GdWE" / "eines Buchungskreises"
    "legal_entity_id": LegalEntity.property_id,
    "ledger_id": Ledger.property_id,
    "statement_id": HoaStatement.ledger_id,
    "plan_id": EconomicPlan.ledger_id,
    "meeting_id": Meeting.legal_entity_id,
    "levy_id": SpecialLevy.legal_entity_id,
    "loan_id": HoaLoan.legal_entity_id,
    "measure_id": HoaMeasure.legal_entity_id,
    "claim_id": HoaInsuranceClaim.legal_entity_id,
    "resolution_id": Resolution.legal_entity_id,
    "engagement_id": AuditEngagement.legal_entity_id,
    "audit_id": AuditEngagement.legal_entity_id,
}

# ``report_id`` names an asset report in assets.py and an audit report in board.py; the audit
# report carries no legal entity, board.py therefore guards only the other ids.
HOA_GUARD = property_column_guard({**HOA_COLUMNS, "report_id": HoaAssetReport.legal_entity_id})
HOA_BOARD_GUARD = property_column_guard(HOA_COLUMNS)
