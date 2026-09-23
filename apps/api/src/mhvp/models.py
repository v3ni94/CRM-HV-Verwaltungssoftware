"""Import point for all mapped models, used by Alembic autogenerate."""

from mhvp.contacts import models as contact_models
from mhvp.contracts import models as contract_models
from mhvp.core import events, numbering, webhooks
from mhvp.documents import models as document_models
from mhvp.platform import models as platform_models
from mhvp.properties import models as property_models

__all__ = [
    "contact_models",
    "contract_models",
    "document_models",
    "events",
    "numbering",
    "platform_models",
    "property_models",
    "webhooks",
]
