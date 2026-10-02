"""Inbound webhook of the claims adjuster (contract section 7, rule INT-SDT-01).

``POST /integrations/schadenstool/webhook/{tenant_id}/{webhook_path_id}`` is outside the
login: the adjuster calls it. Checks in this order: size limit; tenant config found under the
tenant's RLS context with the matching random path id and ``enabled``; HMAC
(``X-Timestamp``, ``X-Signature: sha256=<hex>`` over ``${timestamp}.${rawBody}``) with the
tenant's webhook secret and a 5 minute window; JSON event with ``eventId``. The event is stored
once per ``eventId`` (at least once delivery: a duplicate answers 200 without effect) and the
processing job is kicked; the endpoint itself never calls the adjuster. The path of tenant A
never reaches tenant B: the lookup runs in A's RLS transaction and compares A's path id.
"""

from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import APIRouter, Request, Response

from mhvp.core.auth.principal import sessions
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.uploads import read_body_limited
from mhvp.integrations.schadenstool import services as svc
from mhvp.integrations.schadenstool.signature import SIGNATURE_HEADER, TIMESTAMP_HEADER, verify

log = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/schadenstool", tags=["Schadenbearbeiter Webhook"])

MAX_BODY_BYTES = 256 * 1024


@router.post(
    "/webhook/{tenant_id}/{path_id}",
    summary="Ereignis des Schadenbearbeiters entgegennehmen",
    response_class=Response,
    status_code=200,
    responses={200: {"description": "Angenommen oder bereits bekannt"}},
)
async def receive(tenant_id: uuid.UUID, path_id: uuid.UUID, request: Request) -> Response:
    raw = await read_body_limited(
        request, MAX_BODY_BYTES, error=ErrorCodes.WEBHOOK_TOO_LARGE, detail=None
    )
    fresh = False
    async with tenant_transaction(sessions(request), tenant_id) as session:
        config = await svc.get_config(session, tenant_id)
        if (
            config is None
            or config.webhook_path_id != path_id
            or not config.enabled
            or not config.webhook_secret
        ):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        reason = verify(
            config.webhook_secret,
            raw,
            request.headers.get(TIMESTAMP_HEADER),
            request.headers.get(SIGNATURE_HEADER),
            now=int(time.time()),
        )
        if reason is not None:
            log.warning("schadenstool webhook rejected", extra={"reason": reason})
            raise ProblemError(ErrorCodes.WEBHOOK_SIGNATURE)
        try:
            event = json.loads(raw)
        except ValueError:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Ereignis ist kein JSON.") from None
        if not isinstance(event, dict):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Ereignis ist kein Objekt.")
        fresh = await svc.record_event(session, tenant_id, event)
    if fresh:
        from mhvp.integrations.schadenstool.tasks import enqueue_process

        enqueue_process(request.app.state.settings, tenant_id)
    return Response(status_code=200)
