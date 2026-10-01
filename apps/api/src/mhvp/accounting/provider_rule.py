"""Default bank rule proposal for a service provider relation (GA02-05, 6.2).

``service_provider_relation.create_default_bank_rule`` creates one ``BankRule`` in state
``proposed`` (IBAN fingerprint of the provider account, creditor account as target, low
priority, i.e. a high number). The rule books nothing: it walks the normal four eyes path
(approve, activate with amount cap and test evidence) and only acts after release of G1 and
``auto_posting_enabled``. The call is idempotent per relation and legal entity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import Ledger, LedgerAccount
from mhvp.banking.models import BankRule, RuleState
from mhvp.contacts.models import Contact, ContactBankAccount
from mhvp.core.events import emit

if TYPE_CHECKING:
    from mhvp.properties.models import ServiceProviderRelation

DEFAULT_RULE_PRIORITY = 900  # low priority: specific and learned rules win (lower = earlier)
RULE_NAME_PREFIX = "Standardregel Dienstleister"


async def propose_default_rule(
    session: AsyncSession, relation: ServiceProviderRelation
) -> BankRule | None:
    """The proposed default rule of ``relation``, or None when a prerequisite is missing
    (flag off, no bank account of the provider, no creditor account or ledger)."""
    if not relation.create_default_bank_rule:
        return None
    if relation.contact_bank_account_id is None or relation.creditor_account_id is None:
        return None
    bank = await session.get(ContactBankAccount, relation.contact_bank_account_id)
    account = await session.get(LedgerAccount, relation.creditor_account_id)
    if bank is None or account is None or not bank.iban_fingerprint:
        return None
    ledger = await session.get(Ledger, account.ledger_id)
    if ledger is None:
        return None
    contact = await session.get(Contact, relation.contact_id)
    label = (getattr(contact, "display_name", None) or "Dienstleister")[:120]
    name = f"{RULE_NAME_PREFIX} {label} ({relation.contract_type_code})"[:200]
    existing = await session.scalar(
        select(BankRule).where(
            BankRule.legal_entity_id == ledger.legal_entity_id,
            BankRule.property_id == relation.property_id,
            BankRule.match["counterpart_iban_fingerprint"].astext == bank.iban_fingerprint,
            BankRule.name.like(f"{RULE_NAME_PREFIX}%"),
            BankRule.approval_state != RuleState.DISABLED,
        )
    )
    if existing is not None:
        return existing
    rule = BankRule(
        tenant_id=relation.tenant_id,
        created_by=relation.created_by,
        name=name,
        legal_entity_id=ledger.legal_entity_id,
        property_id=relation.property_id,
        match={"counterpart_iban_fingerprint": bank.iban_fingerprint},
        action={"kind": "creditor_payment", "account_id": str(account.id)},
        priority=DEFAULT_RULE_PRIORITY,
        approval_state=RuleState.PROPOSED,
    )
    session.add(rule)
    await session.flush()
    await emit(
        session,
        tenant_id=relation.tenant_id,
        type="bank_rule.proposed",
        entity_type="bank_rule",
        entity_id=rule.id,
        actor_user_id=relation.created_by,
        payload={
            "origin": "service_provider_relation",
            "relation_id": str(relation.id),
            "legal_entity_id": str(rule.legal_entity_id),
            "approval_state": rule.approval_state.value,
        },
    )
    return rule
