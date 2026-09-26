"""Import point for all mapped models, used by Alembic autogenerate."""

from mhvp.accounting import direct_debit_models
from mhvp.accounting import models as accounting_models
from mhvp.ai import models as ai_models
from mhvp.automation import models as automation_models
from mhvp.banking import models as banking_models
from mhvp.billing import models as billing_models
from mhvp.billing import owner_statement as billing_owner_statement
from mhvp.communication import models as communication_models
from mhvp.contacts import models as contact_models
from mhvp.contracts import models as contract_models
from mhvp.contracts import service_contracts as service_contract_models
from mhvp.core import events, numbering, webhooks
from mhvp.documents import models as document_models
from mhvp.handover import models as handover_models
from mhvp.hoa import models as hoa_models
from mhvp.immoware import models as immoware_models
from mhvp.imports import models as import_models
from mhvp.letting import models as letting_models
from mhvp.letting import rentlaw as rentlaw_models
from mhvp.objektakte import models as objektakte_models
from mhvp.platform import licensing as licensing_models
from mhvp.platform import models as platform_models
from mhvp.portal import models as portal_models
from mhvp.portal import notices as portal_notice_models
from mhvp.properties import models as property_models
from mhvp.receipts import models as receipt_models
from mhvp.sla import models as sla_models
from mhvp.tickets import models as ticket_models
from mhvp.workspace import models as workspace_models

__all__ = [
    "accounting_models",
    "ai_models",
    "automation_models",
    "banking_models",
    "billing_models",
    "billing_owner_statement",
    "communication_models",
    "contact_models",
    "contract_models",
    "direct_debit_models",
    "document_models",
    "events",
    "handover_models",
    "hoa_models",
    "immoware_models",
    "import_models",
    "letting_models",
    "licensing_models",
    "numbering",
    "objektakte_models",
    "platform_models",
    "portal_models",
    "portal_notice_models",
    "property_models",
    "receipt_models",
    "rentlaw_models",
    "service_contract_models",
    "sla_models",
    "ticket_models",
    "webhooks",
    "workspace_models",
]
