"""Import point for all mapped models, used by Alembic autogenerate."""

from mhvp.accounting import models as accounting_models
from mhvp.ai import models as ai_models
from mhvp.banking import models as banking_models
from mhvp.billing import models as billing_models
from mhvp.contacts import models as contact_models
from mhvp.contracts import models as contract_models
from mhvp.core import events, numbering, webhooks
from mhvp.documents import models as document_models
from mhvp.imports import models as import_models
from mhvp.platform import models as platform_models
from mhvp.properties import models as property_models
from mhvp.tickets import models as ticket_models
from mhvp.workspace import models as workspace_models

__all__ = [
    "accounting_models",
    "ai_models",
    "banking_models",
    "billing_models",
    "contact_models",
    "contract_models",
    "document_models",
    "events",
    "import_models",
    "numbering",
    "platform_models",
    "property_models",
    "ticket_models",
    "webhooks",
    "workspace_models",
]
