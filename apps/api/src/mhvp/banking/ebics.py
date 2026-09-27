"""EBICS submission scaffold (V2, M11-01, M15-01; docs/integrations/ebics.md).

EBICS needs a bank contract per account, the subscriber initialisation (INI and HIA letters,
bank keys, activation by the bank) and a client library. The library ``fintech`` (joonis) is
licensed software and is not installed; alternatives are an operator decision (V2). Until
then this submitter only documents what is missing and refuses with MHVP-BANK-0017.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking.models import PaymentBatch
from mhvp.banking.payment_submitters import EBICS_SUBMISSION_FLAG, SubmissionResult
from mhvp.core.problems import ErrorCodes, ProblemError

# EBICS order types for SEPA payment files (EBICS 3.0 uses BTF identifiers instead).
ORDER_TYPE_CREDIT_TRANSFER = "CCT"  # pain.001
ORDER_TYPE_DIRECT_DEBIT_CORE = "CDD"  # pain.008 CORE
PREREQUISITES = (
    "EBICS-Vertrag mit der Bank je Konto und Teilnehmer (Host-ID, Partner-ID, User-ID)",
    "Initialisierung INI (Signaturschlüssel A005/A006) und HIA (Verschlüsselung E002, "
    "Authentifikation X002)",
    "Ausdruck und unterschriebener Versand der INI- und HIA-Briefe, Freischaltung durch die Bank",
    "Abholung und Prüfung der Bankschlüssel (HPB) gegen den Bankbrief",
    "Client-Bibliothek: fintech (joonis, lizenzpflichtig) oder Alternative; "
    "Betreiberentscheidung V2",
    "Feature-Flag MHVP_EBICS_PAYMENT_SUBMISSION je Mandant und Freigabetor G2",
)


@dataclass(frozen=True)
class EbicsReadiness:
    contract: bool = False
    initialised: bool = False
    bank_keys_verified: bool = False
    library_available: bool = False
    flag_enabled: bool = False

    @property
    def ready(self) -> bool:
        return all(
            (
                self.contract,
                self.initialised,
                self.bank_keys_verified,
                self.library_available,
                self.flag_enabled,
            )
        )


def readiness() -> EbicsReadiness:
    """Nothing is configured in the repository; only the flag is read so a misconfiguration
    is visible. The library is never imported here."""
    return EbicsReadiness(
        flag_enabled=os.environ.get(EBICS_SUBMISSION_FLAG, "").lower() in ("1", "true", "yes")
    )


class EbicsSubmitter:
    channel = "ebics"

    async def submit(
        self,
        session: AsyncSession,
        batch: PaymentBatch,
        file: bytes,
        *,
        user_id: uuid.UUID | None,
        reference: str | None,
    ) -> SubmissionResult:
        state = readiness()
        missing = [
            text
            for text, ok in zip(
                PREREQUISITES,
                (
                    state.contract,
                    state.initialised,
                    state.initialised,
                    state.bank_keys_verified,
                    state.library_available,
                    state.flag_enabled,
                ),
                strict=True,
            )
            if not ok
        ]
        raise ProblemError(
            ErrorCodes.PAYMENT_CHANNEL_UNAVAILABLE,
            detail="EBICS: Dokumentation und Vertrag erforderlich. Offen: " + "; ".join(missing),
        )
