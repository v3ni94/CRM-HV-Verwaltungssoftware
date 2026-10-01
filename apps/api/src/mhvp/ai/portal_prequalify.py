"""AI pre-qualification of a portal chat message (M21-01, 14 Phase 3).

Runs only when the portal caller already checked the tenant switch
``chat_ai_prequalification_enabled`` and the gateway gate is open (released provider with
data processing agreement and training opt out). The message is masked before it becomes the
run input (IBAN, e-mail, phone, addresses; rule 0.1.13) and goes through the regular gateway
path as task ``classify_email`` (budget, deduplication, cascade). The result is a proposal
for the management only: topic, urgency and a short summary; it never changes the ticket, it
never answers the portal user and it is no emergency assessment (rule 0.1.6).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.ai import gateway, tasks
from mhvp.ai.masking import mask_personal_data
from mhvp.ai.models import AiTask, AiTaskRun, RunStatus
from mhvp.core.db.tenancy import tenant_transaction

CONTEXT_TYPE = "portal_chat_prequalification"
INSTRUCTION = (
    "Ordne die folgende Nachricht eines Mieters oder Eigentümers aus dem Portal ein: Kategorie, "
    "Dringlichkeit und eine kurze Zusammenfassung. Nur Vorschlag für die Verwaltung."
)


async def prequalify(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    ticket_id: uuid.UUID,
    text: str,
    blobs: Any,
) -> dict[str, Any]:
    """Queues and executes the run inline; returns the proposal fields or the reason."""
    from mhvp.ai import jobs

    masked = mask_personal_data(text)
    prompt = tasks.prompt(AiTask.CLASSIFY_EMAIL)
    instruction = f"{INSTRUCTION}\n\n{masked}"
    context = {"context_type": CONTEXT_TYPE, "context_id": str(ticket_id)}
    async with tenant_transaction(factory, tenant_id) as session:
        run = AiTaskRun(
            tenant_id=tenant_id,
            created_by=None,
            task=AiTask.CLASSIFY_EMAIL,
            conversation_id=None,
            prompt_version=prompt.version,
            input_hash=gateway.input_hash(
                AiTask.CLASSIFY_EMAIL, prompt.version, instruction, context
            ),
            input_ref={"instruction": instruction, "document_ids": [], "context": context},
            status=RunStatus.QUEUED,
        )
        session.add(run)
        await session.flush()
        run_id = run.id
    done = await jobs.run_and_propose(factory, tenant_id, run_id, blobs, None)
    if done is None or done.status is not RunStatus.SUCCEEDED:
        return {"run_id": str(run_id), "status": done.status.value if done else "failed"}
    output = done.output or {}
    return {
        "run_id": str(run_id),
        "status": "succeeded",
        "category": output.get("category"),
        "urgency": output.get("urgency"),
        "summary": output.get("summary"),
    }
