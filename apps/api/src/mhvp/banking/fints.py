"""FinTS/HBCI PIN/TAN connector (M11-01 addendum, operator decision 27.09.2026): direct
bank access with python-fints, in addition to finAPI. Read only: accounts, balances and
transactions; no payment initiation (G2 stays closed).

Three parts live here:

1. Institute lookup (`load_institutes`, `search_institutes`, `blz_from_iban`) from the
   externally maintained list `data/fints_institutes.txt` (one line per BLZ, see
   `docs/integrations/fints.md`). Only institutes with a FinTS URL are "connectable".
2. A synchronous workflow on top of `fints.client.FinTS3PinTanClient` that can be paused for
   a TAN and resumed later, possibly in another process: `start_session` runs the dialog
   until the first TAN request (or completion), `continue_session` feeds a TAN (or polls a
   decoupled confirmation) and continues the work. Every pause returns opaque blobs
   (client state via `deconstruct(including_private=True)`, dialog state via
   `pause_dialog()`, the pending TAN request via `get_data()`); the caller stores them
   encrypted and hands them back unchanged. The PIN is never part of a blob and is never
   logged (python-fints masks it as `Password`).
3. Mapping of bank return codes and python-fints exceptions to registered problem codes
   (ADR 0004, `MHVP-BANK-0007` ff).

python-fints is blocking; `mhvp.banking.tasks.fints_step` runs this in the Celery worker
(queue `bank`) and persists the state in `bank_fints_session`.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import logging
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache
from importlib import resources
from typing import Any

from mhvp.banking import mt940 as mt940_norm
from mhvp.banking.camt import RawTransaction
from mhvp.core.problems import ErrorCode, ErrorCodes, ProblemError

logger = logging.getLogger(__name__)

INSTITUTE_FILE = "fints_institutes.txt"
SEARCH_LIMIT = 20
# PSD2: strong customer authentication is required again after 90 days at the latest
# (product protection: we expect a TAN after this period and tell the operator in advance).
SCA_VALID_DAYS = 90
# Overlap before the last synced booking date on a refresh (like the finAPI job).
SYNC_OVERLAP_DAYS = 3
# First fetch without a cursor: how far back transactions are asked for.
INITIAL_FETCH_DAYS = 89

_IBAN_DE = re.compile(r"^DE\d{20}$")
_BLZ = re.compile(r"^\d{8}$")
_BIC = re.compile(r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$")


# --- 1. Institutes -------------------------------------------------------------------------


@dataclass(frozen=True)
class Institute:
    blz: str
    name: str
    city: str
    bic: str | None
    fints_url: str | None
    hbci_version: str | None
    fints_version: str | None

    @property
    def connectable(self) -> bool:
        return bool(self.fints_url)


def _parse_line(line: str) -> Institute | None:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    blz, _, rest = line.partition("=")
    parts = rest.split("|")
    if not _BLZ.fullmatch(blz.strip()) or len(parts) < 8:
        return None
    name, city, bic, _check, _domain, url, hbci, fints = (p.strip() for p in parts[:8])
    return Institute(
        blz=blz.strip(),
        name=name,
        city=city,
        bic=bic.upper() or None,
        fints_url=url or None,
        hbci_version=hbci or None,
        fints_version=fints or None,
    )


@lru_cache(maxsize=1)
def load_institutes() -> tuple[Institute, ...]:
    """All institutes of the packaged list (cached per process). The list is maintained
    outside this repository; refreshing it is an operations task (docs/integrations/fints.md)."""
    text = resources.files("mhvp.banking").joinpath("data", INSTITUTE_FILE).read_text("utf-8")
    rows = [inst for inst in (_parse_line(line) for line in text.splitlines()) if inst]
    return tuple(rows)


def normalise_query(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def blz_from_iban(iban: str) -> str | None:
    """BLZ of a German IBAN (positions 5 to 12); ``None`` for anything else."""
    compact = normalise_query(iban)
    if not _IBAN_DE.fullmatch(compact):
        return None
    return compact[4:12]


def find_institute(blz: str) -> Institute | None:
    for inst in load_institutes():
        if inst.blz == blz:
            return inst
    return None


def search_institutes(query: str, limit: int = SEARCH_LIMIT) -> list[Institute]:
    """Match by BLZ, BIC, German IBAN or a name/city fragment (case insensitive). Exact BLZ
    and IBAN hits come first, connectable institutes before the others."""
    raw = query.strip()
    if not raw:
        return []
    compact = normalise_query(raw)
    blz = blz_from_iban(compact) or (compact if _BLZ.fullmatch(compact) else None)
    hits: list[Institute] = []
    if blz is not None:
        hits = [inst for inst in load_institutes() if inst.blz == blz]
    elif _BIC.fullmatch(compact):
        hits = [inst for inst in load_institutes() if inst.bic == compact]
        if not hits:
            hits = [
                inst for inst in load_institutes() if inst.bic and inst.bic.startswith(compact[:8])
            ]
    if not hits:
        needle = raw.casefold()
        hits = [
            inst
            for inst in load_institutes()
            if needle in inst.name.casefold()
            or needle in inst.city.casefold()
            or inst.blz.startswith(compact)
        ]
    hits.sort(key=lambda inst: (not inst.connectable, inst.name, inst.city))
    return hits[:limit]


# --- 3. Error mapping ----------------------------------------------------------------------

# Bank return codes (HIRMG/HIRMS, class 9 = error) that we can name for the operator. Anything
# else in class 9 becomes the generic bank rejection with the bank's own text.
PIN_CODES = frozenset({"9340", "9910", "9930", "9931", "9942"})
LOCKED_CODES = frozenset({"3938", "9931"})
TAN_CODES = frozenset({"9941", "9940", "9943"})
SCA_CODES = frozenset({"9075"})


def problem_for_code(code: str, text: str | None = None) -> ProblemError:
    """Registered problem for a bank return code (docs/integrations/fints.md section 5)."""
    detail = f"Rückmeldecode {code}" + (f": {text}" if text else "")
    if code in LOCKED_CODES:
        return ProblemError(ErrorCodes.FINTS_ACCOUNT_LOCKED, detail=detail)
    if code in PIN_CODES:
        return ProblemError(ErrorCodes.FINTS_PIN_REJECTED, detail=detail)
    if code in TAN_CODES:
        return ProblemError(ErrorCodes.FINTS_TAN_REJECTED, detail=detail)
    if code in SCA_CODES:
        return ProblemError(ErrorCodes.FINTS_SCA_REQUIRED, detail=detail)
    return ProblemError(ErrorCodes.FINTS_BANK_REJECTED, detail=detail)


def problem_for_exception(exc: BaseException) -> ProblemError:
    """python-fints exception to registered problem. Never includes the PIN; python-fints
    masks it in its own messages."""
    if isinstance(exc, ProblemError):
        return exc
    name = type(exc).__name__
    if name == "FinTSClientTemporaryAuthError":
        return ProblemError(ErrorCodes.FINTS_ACCOUNT_LOCKED, detail=str(exc))
    if name == "FinTSClientPINError":
        return ProblemError(ErrorCodes.FINTS_PIN_REJECTED, detail=str(exc))
    if name == "FinTSSCARequiredError":
        return ProblemError(ErrorCodes.FINTS_SCA_REQUIRED, detail=str(exc))
    if name in ("FinTSConnectionError", "FinTSNoResponseError", "ConnectionError", "TimeoutError"):
        return ProblemError(ErrorCodes.FINTS_UNAVAILABLE, detail=str(exc))
    if name == "FinTSDialogError":
        message = str(exc)
        match = re.search(r"\b(9\d{3})\b", message)
        if match:
            return problem_for_code(match.group(1), message)
        return ProblemError(ErrorCodes.FINTS_BANK_REJECTED, detail=message)
    return ProblemError(ErrorCodes.FINTS_BANK_REJECTED, detail=f"{name}: {exc}"[:500])


def problem_code(error: ErrorCode) -> str:
    return error.code


# --- 2. Workflow ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Credentials:
    """Everything needed to open a PIN/TAN client. Never logged, never serialised."""

    blz: str
    fints_url: str
    login: str
    pin: str
    product_id: str
    product_version: str = "1.0"

    def __repr__(self) -> str:  # defensive: no PIN in tracebacks or logs
        return f"Credentials(blz={self.blz!r}, login=***, pin=***)"


@dataclass(frozen=True)
class TanMechanism:
    code: str
    name: str
    decoupled: bool = False


@dataclass(frozen=True)
class Challenge:
    """A pending TAN request plus the opaque state needed to answer it later."""

    text: str | None
    image_mime: str | None
    image: bytes | None
    hhduc: str | None
    decoupled: bool
    retry_data: bytes
    dialog_data: bytes
    client_data: bytes


@dataclass
class AccountSnapshot:
    iban: str
    bic: str | None
    account_number: str | None
    subaccount: str | None
    blz: str | None
    balance: str | None = None
    currency: str | None = None
    balance_date: str | None = None


@dataclass
class Progress:
    """JSON serialisable position within the work of one session, so a TAN request in the
    middle (e.g. a bank that asks a TAN per transaction fetch) can be answered and the work
    resumed exactly where it stopped."""

    with_transactions: bool
    since: str | None = None
    until: str | None = None
    accounts: list[dict[str, Any]] | None = None
    next_index: int = 0
    stage: str = "accounts"  # accounts | balance | transactions
    transactions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Progress:
        return cls(**data)


@dataclass
class StepResult:
    status: str  # awaiting_tan | awaiting_decoupled | done
    client_data: bytes
    tan_mechanisms: list[TanMechanism]
    tan_mechanism: str | None
    tan_medium: str | None
    challenge: Challenge | None = None
    progress: Progress | None = None


class TanRequired(Exception):  # noqa: N818 - control flow marker, not an error
    """Raised inside the work loop when a command came back with a TAN request."""

    def __init__(self, response: Any) -> None:
        super().__init__("TAN required")
        self.response = response


def _client_class() -> Any:
    from fints.client import FinTS3PinTanClient

    return FinTS3PinTanClient


# Injection points for tests (a fake client class and fake retry blob restore).
CLIENT_FACTORY: Callable[[], Any] = _client_class


def restore_retry(blob: bytes) -> Any:
    from fints.client import NeedRetryResponse

    return NeedRetryResponse.from_data(blob)


RESTORE_RETRY: Callable[[bytes], Any] = restore_retry


def is_tan_request(value: Any) -> bool:
    return (
        hasattr(value, "get_data") and hasattr(value, "decoupled") and hasattr(value, "challenge")
    )


def _build_client(creds: Credentials, client_data: bytes | None) -> Any:
    cls = CLIENT_FACTORY()
    return cls(
        creds.blz,
        creds.login,
        creds.pin,
        creds.fints_url,
        product_id=creds.product_id,
        product_version=creds.product_version,
        from_data=client_data,
    )


def _mechanisms(client: Any) -> list[TanMechanism]:
    out: list[TanMechanism] = []
    for code, param in client.get_tan_mechanisms().items():
        name = str(getattr(param, "name", "") or code)
        decoupled = bool(getattr(param, "decoupled", False)) or "push" in name.casefold()
        out.append(TanMechanism(code=str(code), name=name, decoupled=decoupled))
    return out


def _challenge(response: Any, dialog_data: bytes, client_data: bytes) -> Challenge:
    image_mime: str | None = None
    image: bytes | None = None
    matrix = getattr(response, "challenge_matrix", None)
    if matrix:
        image_mime, image = str(matrix[0]), bytes(matrix[1])
    return Challenge(
        text=getattr(response, "challenge", None),
        image_mime=image_mime,
        image=image,
        hhduc=getattr(response, "challenge_hhduc", None),
        decoupled=bool(getattr(response, "decoupled", False)),
        retry_data=bytes(response.get_data()),
        dialog_data=dialog_data,
        client_data=client_data,
    )


def _snapshot(account: Any) -> AccountSnapshot:
    return AccountSnapshot(
        iban=str(account.iban).replace(" ", "").upper(),
        bic=getattr(account, "bic", None) or None,
        account_number=getattr(account, "accountnumber", None) or None,
        subaccount=getattr(account, "subaccount", None) or None,
        blz=getattr(account, "blz", None) or None,
    )


def _sepa_account(snapshot: dict[str, Any]) -> Any:
    from fints.models import SEPAAccount

    return SEPAAccount(
        iban=snapshot["iban"],
        bic=snapshot.get("bic"),
        accountnumber=snapshot.get("account_number"),
        subaccount=snapshot.get("subaccount"),
        blz=snapshot.get("blz"),
    )


def _apply_balance(target: dict[str, Any], balance: Any) -> None:
    if balance is None:
        return
    amount = getattr(balance, "amount", None)
    value = getattr(amount, "amount", amount)
    if value is None:
        return
    target["balance"] = str(Decimal(str(value)).quantize(Decimal("0.01")))
    target["currency"] = getattr(amount, "currency", None) or "EUR"
    when = getattr(balance, "date", None)
    target["balance_date"] = when.isoformat() if isinstance(when, date) else None


def mt940_transaction_to_raw(tx: Any, statement_ref: str) -> RawTransaction:
    """`mt940.models.Transaction` (what python-fints returns) to the file import's
    `RawTransaction`: the raw `:86:` text goes through the existing German subfield
    normalisation (`mhvp.banking.mt940.parse_info`), the sign follows the D/C mark with
    reversals (RC negative, RD positive) like the file parser, and the bank reference of
    `:61:` is the dedup key; without one a content derived key keeps the import idempotent."""
    data = tx.data if isinstance(getattr(tx, "data", None), dict) else dict(tx)
    amount_obj = data.get("amount")
    magnitude = abs(Decimal(str(getattr(amount_obj, "amount", amount_obj) or "0")))
    status = str(data.get("status") or "C").upper()
    signed = magnitude if status in ("C", "RD") else -magnitude
    value_date = data.get("date")
    booking = data.get("entry_date") or value_date
    if not isinstance(booking, date):
        raise ValueError("Umsatz ohne Buchungsdatum")
    details = data.get("transaction_details")
    parsed = mt940_norm.parse_info(details) if details else {"info_raw": None, "convention": None}
    account = parsed.get("counterpart_account")
    account_clean = account.replace(" ", "").upper() if account else None
    iban = (
        account_clean
        if account_clean and re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", account_clean)
        else None
    )
    bank = parsed.get("counterpart_bank")
    bic = bank.strip().upper() if bank and _BIC.fullmatch(bank.strip().upper()) else None
    sepa = parsed.get("sepa") or {}
    purpose = parsed.get("purpose")
    info_raw = parsed.get("info_raw")
    if purpose is None and isinstance(info_raw, str) and info_raw:
        purpose = " ".join(line.strip() for line in info_raw.split("\n")).strip()
    bank_ref = (data.get("bank_reference") or "").strip() or None
    if bank_ref:
        reference = f"fints:{bank_ref}"
        source = "61//bank_reference"
    else:
        digest = hashlib.sha256(
            "|".join(
                [
                    statement_ref,
                    booking.isoformat(),
                    str(signed),
                    str(data.get("customer_reference") or ""),
                    str(details or ""),
                ]
            ).encode()
        ).hexdigest()[:32]
        reference = f"fints:{digest}"
        source = "derived:sha256(booking_date,amount,customer_reference,86)"
    raw: dict[str, Any] = {
        "format": "fints-mt940",
        "reference_source": source,
        "customer_reference": data.get("customer_reference"),
        "transaction_type": data.get("id"),
        "debit_credit": status,
        "funds_code": data.get("funds_code"),
        "supplementary": data.get("extra_details") or None,
        "info": parsed,
    }
    currency = getattr(amount_obj, "currency", None) or "EUR"
    return RawTransaction(
        bank_reference=reference,
        booking_date=booking,
        value_date=value_date if isinstance(value_date, date) else None,
        amount=signed,
        currency=str(currency),
        counterpart_name=parsed.get("counterpart_name"),
        counterpart_iban=iban,
        counterpart_bic=bic,
        purpose=purpose or None,
        end_to_end_id=sepa.get("EREF") or None,
        mandate_reference=sepa.get("MREF") or None,
        creditor_id=sepa.get("CRED") or None,
        transaction_code=(parsed.get("gvc") or data.get("id")),
        raw=raw,
    )


def raw_to_json(tx: RawTransaction) -> dict[str, Any]:
    d = asdict(tx)
    d["booking_date"] = tx.booking_date.isoformat()
    d["value_date"] = tx.value_date.isoformat() if tx.value_date else None
    d["amount"] = str(tx.amount)
    return d


def raw_from_json(d: dict[str, Any]) -> RawTransaction:
    return RawTransaction(
        bank_reference=d.get("bank_reference"),
        booking_date=date.fromisoformat(d["booking_date"]),
        value_date=date.fromisoformat(d["value_date"]) if d.get("value_date") else None,
        amount=Decimal(d["amount"]),
        currency=d.get("currency") or "EUR",
        counterpart_name=d.get("counterpart_name"),
        counterpart_iban=d.get("counterpart_iban"),
        counterpart_bic=d.get("counterpart_bic"),
        purpose=d.get("purpose"),
        end_to_end_id=d.get("end_to_end_id"),
        mandate_reference=d.get("mandate_reference"),
        creditor_id=d.get("creditor_id"),
        transaction_code=d.get("transaction_code"),
        raw=d.get("raw") or {},
    )


def _guard(value: Any) -> Any:
    if is_tan_request(value):
        raise TanRequired(value)
    return value


def _work(client: Any, progress: Progress, pending: Any = None) -> Progress:
    """Runs (or resumes) the work of a session inside an open dialog. ``pending`` is the
    result of the command that had asked for a TAN and has now been answered."""
    if progress.accounts is None:
        accounts = _guard(pending if pending is not None else client.get_sepa_accounts())
        pending = None
        progress.accounts = [asdict(_snapshot(a)) for a in accounts]
        progress.stage, progress.next_index = "balance", 0
    while progress.next_index < len(progress.accounts):
        snap = progress.accounts[progress.next_index]
        sepa = _sepa_account(snap)
        if progress.stage == "balance":
            balance = _guard(pending if pending is not None else client.get_balance(sepa))
            pending = None
            _apply_balance(snap, balance)
            progress.stage = "transactions" if progress.with_transactions else "balance"
            if not progress.with_transactions:
                progress.next_index += 1
                continue
        if progress.stage == "transactions":
            since = date.fromisoformat(progress.since) if progress.since else None
            until = date.fromisoformat(progress.until) if progress.until else None
            rows = _guard(
                pending if pending is not None else client.get_transactions(sepa, since, until)
            )
            pending = None
            statement_ref = f"{snap['iban']}/{since or ''}/{until or ''}"
            raws = [mt940_transaction_to_raw(t, statement_ref) for t in rows]
            if since is not None:
                raws = [r for r in raws if r.booking_date >= since]
            if until is not None:
                raws = [r for r in raws if r.booking_date <= until]
            progress.transactions[snap["iban"]] = [raw_to_json(r) for r in raws]
            progress.stage, progress.next_index = "balance", progress.next_index + 1
    return progress


def _pause(client: Any, response: Any, result: StepResult, progress: Progress) -> StepResult:
    dialog_data = bytes(client.pause_dialog())
    client_data = bytes(client.deconstruct(including_private=True))
    result.challenge = _challenge(response, dialog_data, client_data)
    result.client_data = client_data
    result.progress = progress
    result.status = "awaiting_decoupled" if result.challenge.decoupled else "awaiting_tan"
    return result


def start_session(
    creds: Credentials,
    *,
    client_data: bytes | None,
    tan_mechanism: str | None,
    tan_medium: str | None,
    progress: Progress,
) -> StepResult:
    """Opens the dialog and runs the work until it is done or the bank asks for a TAN.
    Raises `ProblemError` for bank rejections (registered codes)."""
    try:
        client = _build_client(creds, client_data)
        if client_data is None or not client.get_current_tan_mechanism():
            client.fetch_tan_mechanisms()
        mechanisms = _mechanisms(client)
        if tan_mechanism and any(m.code == tan_mechanism for m in mechanisms):
            client.set_tan_mechanism(tan_mechanism)
        elif tan_mechanism:
            raise ProblemError(
                ErrorCodes.FINTS_STATE,
                detail=f"TAN-Verfahren {tan_mechanism} wird von der Bank nicht angeboten.",
            )
        selected_medium = tan_medium or getattr(client, "selected_tan_medium", None)
        if client.is_tan_media_required() and not selected_medium:
            _usage, media = client.get_tan_media()
            if media:
                client.set_tan_medium(media[0])
                selected_medium = getattr(client, "selected_tan_medium", None)
        elif tan_medium and not getattr(client, "selected_tan_medium", None):
            client.selected_tan_medium = tan_medium
        result = StepResult(
            status="done",
            client_data=b"",
            tan_mechanisms=mechanisms,
            tan_mechanism=client.get_current_tan_mechanism(),
            tan_medium=selected_medium,
        )
        with client:
            init_response = getattr(client, "init_tan_response", None)
            if is_tan_request(init_response):
                return _pause(client, init_response, result, progress)
            try:
                progress = _work(client, progress)
            except TanRequired as tan:
                return _pause(client, tan.response, result, progress)
        result.client_data = bytes(client.deconstruct(including_private=True))
        result.progress = progress
        return result
    except ProblemError:
        raise
    except Exception as exc:
        raise problem_for_exception(exc) from None


def continue_session(
    creds: Credentials,
    *,
    challenge: Challenge,
    tan: str | None,
    tan_mechanism: str | None,
    tan_medium: str | None,
    progress: Progress,
) -> StepResult:
    """Answers the pending TAN request (or polls the decoupled confirmation) and continues
    the work. A decoupled request that is not yet confirmed comes back as
    ``awaiting_decoupled`` again, without an error."""
    try:
        client = _build_client(creds, challenge.client_data)
        if tan_medium and not getattr(client, "selected_tan_medium", None):
            client.selected_tan_medium = tan_medium
        pending_request = RESTORE_RETRY(challenge.retry_data)
        result = StepResult(
            status="done",
            client_data=b"",
            tan_mechanisms=_mechanisms(client),
            tan_mechanism=client.get_current_tan_mechanism() or tan_mechanism,
            tan_medium=tan_medium,
        )
        with client.resume_dialog(challenge.dialog_data):
            answer = client.send_tan(pending_request, tan or "")
            if is_tan_request(answer):
                # decoupled: not confirmed yet in the bank app, or a further TAN is required
                return _pause(client, answer, result, progress)
            try:
                # The answered command was the dialog init (no pending work result) or a data
                # command whose result is `answer`.
                pending = answer if _is_work_result(progress, answer) else None
                progress = _work(client, progress, pending)
            except TanRequired as tan_again:
                return _pause(client, tan_again.response, result, progress)
        result.client_data = bytes(client.deconstruct(including_private=True))
        result.progress = progress
        return result
    except ProblemError:
        raise
    except Exception as exc:
        raise problem_for_exception(exc) from None


def _is_work_result(progress: Progress, answer: Any) -> bool:
    """Whether `answer` (what `send_tan` returned) is the result of a data command of the
    work loop rather than of the dialog initialisation. A list is an account or transaction
    list; an object with an `amount` is a balance."""
    if isinstance(answer, list):
        return True
    return hasattr(answer, "amount") and progress.stage == "balance"


def sca_due(last_sca_at: date | None, today: date) -> bool:
    return last_sca_at is None or today - last_sca_at >= timedelta(days=SCA_VALID_DAYS)


def encode_blob(data: bytes | None) -> str | None:
    return base64.b64encode(data).decode("ascii") if data else None


def decode_blob(value: str | None) -> bytes | None:
    return base64.b64decode(value) if value else None


def initial_since(last_synced: date | None, today: date) -> date:
    if last_synced is None:
        return today - timedelta(days=INITIAL_FETCH_DAYS)
    return last_synced - timedelta(days=SYNC_OVERLAP_DAYS)


with contextlib.suppress(Exception):  # keep python-fints' own logger from echoing PINs
    logging.getLogger("fints").setLevel(logging.WARNING)
