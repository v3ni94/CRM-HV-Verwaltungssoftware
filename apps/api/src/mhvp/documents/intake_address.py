"""Tenant intake address for forwarded mail (11.4, M6-04).

Each tenant gets one forwarding address built from the mailbox that receives the forwards and
a random token with plus addressing: ``belege@example.de`` becomes ``belege+<token>@example.de``.
The mailbox itself is synchronised by the existing mail intake (communication); the document
inbox job (``mhvp.documents.intake.process_mailbox``) recognises messages to the address:

* to this tenant's address: attachments go through the intake as source ``forward``; when an
  allowed sender list is set, only those senders (exact address or ``@domain``) are processed.
* to a plus address of the same mailbox with another token: skipped, the message belongs to a
  different tenant and is never processed here.

The configuration lives in ``TenantSettings.sources`` under ``CONFIG_KEY``; no new table.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Any

CONFIG_KEY = "document_intake_address"
TOKEN_BYTES = 6


@dataclass
class IntakeAddress:
    mailbox_address: str
    token: str
    allowed_senders: list[str] = field(default_factory=list)
    enabled: bool = True

    @property
    def address(self) -> str:
        local, domain = self.mailbox_address.lower().split("@", 1)
        return f"{local}+{self.token}@{domain}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "mailbox_address": self.mailbox_address.lower(),
            "token": self.token,
            "allowed_senders": list(self.allowed_senders),
            "enabled": self.enabled,
        }


def new_token() -> str:
    return secrets.token_hex(TOKEN_BYTES)


def load(sources: dict[str, Any] | None) -> IntakeAddress | None:
    raw = (sources or {}).get(CONFIG_KEY)
    if not isinstance(raw, dict) or not raw.get("mailbox_address") or not raw.get("token"):
        return None
    return IntakeAddress(
        mailbox_address=str(raw["mailbox_address"]),
        token=str(raw["token"]),
        allowed_senders=[str(x) for x in raw.get("allowed_senders") or []],
        enabled=bool(raw.get("enabled", True)),
    )


def sender_allowed(config: IntakeAddress, sender: str | None) -> bool:
    if not config.allowed_senders:
        return True
    if not sender:
        return False
    address = sender.strip().lower()
    if "<" in address and address.endswith(">"):
        address = address[address.rindex("<") + 1 : -1]
    domain = "@" + address.split("@", 1)[1] if "@" in address else ""
    return any(
        entry == address or (entry.startswith("@") and entry == domain)
        for entry in config.allowed_senders
    )


def classify(config: IntakeAddress | None, recipients: list[str]) -> str | None:
    """``"own"`` for a message to this tenant's address, ``"foreign"`` for a plus address of
    the same mailbox with another token, otherwise None (ordinary mail)."""
    if config is None or not config.enabled:
        return None
    local, domain = config.mailbox_address.lower().split("@", 1)
    foreign = False
    for recipient in recipients:
        address = recipient.strip().lower()
        if "<" in address and address.endswith(">"):
            address = address[address.rindex("<") + 1 : -1]
        if address == config.address:
            return "own"
        if address.endswith("@" + domain) and address.startswith(local + "+"):
            foreign = True
    return "foreign" if foreign else None
