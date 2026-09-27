"""Submission of payment files to the bank (M15-01, V2; masterprompt chapter 8 Zahlläufe).

``PaymentSubmitter`` is the single interface. Only ``FileDownloadSubmitter`` is usable: the
file is handed out behind G2, uploaded by a person in the online banking and the status
"eingereicht" is confirmed manually with the bank reference. ``FintsSubmitter`` (python-fints
can submit pain files with a TAN) and ``EbicsSubmitter`` (``mhvp.banking.ebics``) are
scaffolds: both refuse with MHVP-BANK-0017 until the operator decision (V2), the bank
contract and the per tenant feature flag exist. Nothing here moves money on its own.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking.models import PaymentBatch
from mhvp.core.problems import ErrorCodes, ProblemError

FINTS_SUBMISSION_FLAG = "MHVP_FINTS_PAYMENT_SUBMISSION"  # env flag, default off (G2 + V2)
EBICS_SUBMISSION_FLAG = "MHVP_EBICS_PAYMENT_SUBMISSION"


@dataclass(frozen=True)
class SubmissionResult:
    """Outcome of one submission attempt; ``submitted`` is only true for a proven hand-over."""

    channel: str
    submitted: bool
    reference: str | None = None
    instructions: list[str] = field(default_factory=list)


class PaymentSubmitter(Protocol):
    channel: str

    async def submit(
        self,
        session: AsyncSession,
        batch: PaymentBatch,
        file: bytes,
        *,
        user_id: uuid.UUID | None,
        reference: str | None,
    ) -> SubmissionResult: ...


def _require_file(batch: PaymentBatch) -> None:
    if batch.document_id is None or not batch.file_sha256:
        raise ProblemError(
            ErrorCodes.PAYMENT_FILE_STATE, detail="Für den Sammler ist keine Datei abgelegt."
        )
    if batch.submitted_at is not None:
        raise ProblemError(
            ErrorCodes.PAYMENT_FILE_STATE, detail="Der Sammler wurde bereits eingereicht."
        )


class FileDownloadSubmitter:
    """Manual upload in the online banking. The submission is a human statement: the caller
    confirms that the downloaded file (same checksum) was uploaded and names the bank
    reference or protocol number; the batch then counts as submitted."""

    channel = "file"

    async def submit(
        self,
        session: AsyncSession,
        batch: PaymentBatch,
        file: bytes,
        *,
        user_id: uuid.UUID | None,
        reference: str | None,
    ) -> SubmissionResult:
        _require_file(batch)
        if not (reference or "").strip():
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Bankreferenz oder Protokollnummer der Einreichung angeben.",
            )
        batch.submission_channel = self.channel
        batch.submission_reference = (reference or "").strip()[:140]
        batch.submitted_at = datetime.now(UTC)
        batch.submitted_by = user_id
        batch.submitted_via = "manual"
        batch.status = "submitted"
        await session.flush()
        return SubmissionResult(self.channel, True, batch.submission_reference)


class FintsSubmitter:
    """Scaffold for the FinTS/HBCI submission (python-fints ``sepa_transfer`` with a TAN
    challenge; HKCCM/HKDSE segments). Not active: the flag ``MHVP_FINTS_PAYMENT_SUBMISSION``
    stays off, G2 stays closed and the DK product registration (M11-42) is pending."""

    channel = "fints"

    @staticmethod
    def enabled() -> bool:
        return os.environ.get(FINTS_SUBMISSION_FLAG, "").lower() in ("1", "true", "yes")

    async def submit(
        self,
        session: AsyncSession,
        batch: PaymentBatch,
        file: bytes,
        *,
        user_id: uuid.UUID | None,
        reference: str | None,
    ) -> SubmissionResult:
        _require_file(batch)
        if not self.enabled():
            raise ProblemError(
                ErrorCodes.PAYMENT_CHANNEL_UNAVAILABLE,
                detail=(
                    "FinTS-Einreichung ist vorbereitet, aber nicht freigeschaltet "
                    f"({FINTS_SUBMISSION_FLAG}, Betreiberentscheidung V2, M11-42)."
                ),
            )
        # Planned flow (docs/integrations/fints.md): open a bank_fints_session of kind
        # "payment", hand the pain file to python-fints (client.sepa_transfer for a single
        # order or the pain based multi transfer), collect the TAN via the existing TAN dialog,
        # then record the bank acknowledgement as submission_reference.
        raise ProblemError(
            ErrorCodes.PAYMENT_CHANNEL_UNAVAILABLE,
            detail="FinTS-Einreichung ist noch nicht umgesetzt (Grundgerüst, M15-01).",
        )


def submitter_for(channel: str) -> PaymentSubmitter:
    from mhvp.banking.ebics import EbicsSubmitter

    registry: dict[str, PaymentSubmitter] = {
        FileDownloadSubmitter.channel: FileDownloadSubmitter(),
        FintsSubmitter.channel: FintsSubmitter(),
        EbicsSubmitter.channel: EbicsSubmitter(),
    }
    if channel not in registry:
        raise ProblemError(ErrorCodes.VALIDATION, detail=f"Unbekannter Einreichungsweg {channel}.")
    return registry[channel]
