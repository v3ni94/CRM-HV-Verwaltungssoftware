"""Deterministic reading of chat instructions for the table import (Betreiberauftrag
26.09.2026): "Rolle bank hinterlegen", "als Mieter", "Rolle: Eigentümer", "Tag Bank".

The role found here is a default for every imported contact. It is added to ``roles``
(``ck_contact_roles_values``), never replaces a role from the table, and is also handed to the
``map_columns`` prompt so the model sees the operator's instruction.
"""

import re
import unicodedata

from mhvp.contacts.models import ContactRoleCode

# Spoken forms (lower case, umlauts folded) to ContactRoleCode values.
_ROLE_WORDS: dict[str, str] = {
    "eigentuemer": ContactRoleCode.EIGENTUEMER.value,
    "eigentumer": ContactRoleCode.EIGENTUEMER.value,
    "eigentuemerin": ContactRoleCode.EIGENTUEMER.value,
    "eigentuemerinnen": ContactRoleCode.EIGENTUEMER.value,
    "vermieter": ContactRoleCode.EIGENTUEMER.value,
    "owner": ContactRoleCode.EIGENTUEMER.value,
    "mieter": ContactRoleCode.MIETER.value,
    "mieterin": ContactRoleCode.MIETER.value,
    "mieterinnen": ContactRoleCode.MIETER.value,
    "tenant": ContactRoleCode.MIETER.value,
    "verwalter": ContactRoleCode.VERWALTER.value,
    "verwaltung": ContactRoleCode.VERWALTER.value,
    "hausverwaltung": ContactRoleCode.VERWALTER.value,
    "dienstleister": ContactRoleCode.DIENSTLEISTER.value,
    "handwerker": ContactRoleCode.DIENSTLEISTER.value,
    "provider": ContactRoleCode.DIENSTLEISTER.value,
    "bank": ContactRoleCode.BANK.value,
    "banken": ContactRoleCode.BANK.value,
    "kreditinstitut": ContactRoleCode.BANK.value,
    "kreditinstitute": ContactRoleCode.BANK.value,
    "sonstige": ContactRoleCode.SONSTIGES.value,
    "sonstiges": ContactRoleCode.SONSTIGES.value,
    "sonstiger": ContactRoleCode.SONSTIGES.value,
}

# Role codes of the map_columns / extract_contacts schemas to ContactRoleCode values.
TASK_ROLE_TO_CONTACT_ROLE: dict[str, str] = {
    "owner": ContactRoleCode.EIGENTUEMER.value,
    "tenant": ContactRoleCode.MIETER.value,
    "provider": ContactRoleCode.DIENSTLEISTER.value,
    "bank": ContactRoleCode.BANK.value,
    "manager": ContactRoleCode.VERWALTER.value,
    "other": ContactRoleCode.SONSTIGES.value,
}

_WORD = r"([A-Za-zÄÖÜäöüß]+)"
_ROLE_PATTERNS = [
    # "Rolle bank", "Rolle: Eigentümer", "Rolle = mieter", "Rollen bank"
    re.compile(rf"\brollen?\s*[:=]?\s*[\"'„“]?{_WORD}", re.IGNORECASE),
    # "als Mieter anlegen", "als Bank hinterlegen", "als Eigentümer"
    re.compile(rf"\bals\s+{_WORD}", re.IGNORECASE),
    # "Kontaktrolle bank"
    re.compile(rf"\bkontaktrollen?\s*[:=]?\s*{_WORD}", re.IGNORECASE),
]
_TAG_PATTERN = re.compile(
    r"\b(?:tags?|kategorie|schlagwort)\s*[:=]?\s*[\"'„“]?([A-Za-zÄÖÜäöüß0-9][\wÄÖÜäöüß\- ]{0,40}?)"
    r"(?=[\"'“]|[,.;!?\n]|\s+(?:und|hinterlegen|setzen|vergeben|anlegen|geben)\b|$)",
    re.IGNORECASE,
)


def _fold(word: str) -> str:
    word = word.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    word = word.replace("ß", "ss")
    return unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode()


def role_code(word: str) -> str | None:
    """Maps one role word ("Eigentümer", "bank", "owner") to a ContactRoleCode value."""
    return _ROLE_WORDS.get(_fold(word.strip()))


def role_from_instruction(text: str | None) -> str | None:
    """First role named in the chat instruction, or ``None``."""
    if not text:
        return None
    for pattern in _ROLE_PATTERNS:
        for match in pattern.finditer(text):
            code = role_code(match.group(1))
            if code is not None:
                return code
    return None


def tags_from_instruction(text: str | None) -> list[str]:
    """Tags named as "Tag Bank", "Kategorie: Bank" or "Schlagwort Bank"."""
    if not text:
        return []
    found: list[str] = []
    for match in _TAG_PATTERN.finditer(text):
        tag = match.group(1).strip()
        if tag and tag not in found:
            found.append(tag)
    return found


def contact_role(task_role: str | None) -> str | None:
    """Role of a mapped or extracted row (task code or free text) as a ContactRoleCode value."""
    if not task_role:
        return None
    return TASK_ROLE_TO_CONTACT_ROLE.get(task_role) or role_code(task_role)
