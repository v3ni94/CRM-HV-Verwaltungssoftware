"""Import point for all mapped models, used by Alembic autogenerate."""

from mhvp.accounting import direct_debit_models
from mhvp.accounting import models as accounting_models
from mhvp.accounting import rent_invoice_models as accounting_rent_invoice_models
from mhvp.accounting import tax_models as accounting_tax_models
from mhvp.ai import models as ai_models
from mhvp.automation import models as automation_models
from mhvp.banking import models as banking_models
from mhvp.billing import advance_rule as billing_advance_rule
from mhvp.billing import models as billing_models
from mhvp.billing import owner_statement as billing_owner_statement
from mhvp.communication import assignment_review as communication_assignment_review
from mhvp.communication import calendar_feed as communication_calendar_feed
from mhvp.communication import models as communication_models
from mhvp.communication import sync_retry as communication_sync_retry
from mhvp.communication import telephony as communication_telephony
from mhvp.contacts import models as contact_models
from mhvp.contracts import deposit_settlement as deposit_settlement_models
from mhvp.contracts import models as contract_models
from mhvp.contracts import service_contracts as service_contract_models
from mhvp.core import events, numbering, webhooks
from mhvp.documents import models as document_models
from mhvp.handover import models as handover_models
from mhvp.hoa import inspection as hoa_inspection_models
from mhvp.hoa import models as hoa_models
from mhvp.hoa import reserve_statement as hoa_reserve_statement
from mhvp.immoware import models as immoware_models
from mhvp.imports import history_models as import_history_models
from mhvp.imports import migration_models as import_migration_models
from mhvp.imports import models as import_models
from mhvp.integrations import models as integrations_models
from mhvp.integrations.schadenstool import models as schadenstool_models
from mhvp.letting import models as letting_models
from mhvp.letting import rentlaw as rentlaw_models
from mhvp.metering import models as metering_models
from mhvp.objektakte import dms_models as objektakte_dms_models
from mhvp.objektakte import models as objektakte_models
from mhvp.platform import licensing as licensing_models
from mhvp.platform import market_readiness as market_readiness_models
from mhvp.platform import models as platform_models
from mhvp.portal import board as portal_board_models
from mhvp.portal import forms as portal_form_models
from mhvp.portal import models as portal_models
from mhvp.portal import notices as portal_notice_models
from mhvp.privacy import models as privacy_models
from mhvp.properties import models as property_models
from mhvp.receipts import models as receipt_models
from mhvp.sla import models as sla_models
from mhvp.tickets import board as ticket_board_models
from mhvp.tickets import models as ticket_models
from mhvp.workspace import models as workspace_models

__all__ = [
    "accounting_models",
    "accounting_rent_invoice_models",
    "accounting_tax_models",
    "ai_models",
    "automation_models",
    "banking_models",
    "billing_advance_rule",
    "billing_models",
    "billing_owner_statement",
    "communication_assignment_review",
    "communication_calendar_feed",
    "communication_models",
    "communication_sync_retry",
    "communication_telephony",
    "contact_models",
    "contract_models",
    "deposit_settlement_models",
    "direct_debit_models",
    "document_models",
    "events",
    "handover_models",
    "hoa_inspection_models",
    "hoa_models",
    "hoa_reserve_statement",
    "immoware_models",
    "import_history_models",
    "import_migration_models",
    "import_models",
    "integrations_models",
    "letting_models",
    "licensing_models",
    "market_readiness_models",
    "metering_models",
    "numbering",
    "objektakte_dms_models",
    "objektakte_models",
    "platform_models",
    "portal_board_models",
    "portal_form_models",
    "portal_models",
    "portal_notice_models",
    "privacy_models",
    "property_models",
    "receipt_models",
    "rentlaw_models",
    "schadenstool_models",
    "service_contract_models",
    "sla_models",
    "ticket_board_models",
    "ticket_models",
    "webhooks",
    "workspace_models",
]
