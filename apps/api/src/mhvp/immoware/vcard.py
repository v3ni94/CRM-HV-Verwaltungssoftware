"""Minimaler vCard-3/4-Parser (FN, ORG, EMAIL, TEL, ADR, UID), selbst implementiert (Regel 8:
keine neuen Pakete). Zeilenumbrueche (folding) nach RFC 6350/2426 werden aufgeloest."""

from dataclasses import dataclass, field


@dataclass
class ParsedVCard:
    uid: str | None = None
    fn: str | None = None
    org: str | None = None
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    addresses: list[dict[str, str]] = field(default_factory=list)


def _unfold(raw: str) -> list[str]:
    lines: list[str] = []
    for line in raw.replace("\r\n", "\n").split("\n"):
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        elif line.strip():
            lines.append(line)
    return lines


def parse_vcard(raw: str) -> ParsedVCard:
    card = ParsedVCard()
    for line in _unfold(raw):
        if ":" not in line:
            continue
        name_part, _, value = line.partition(":")
        name = name_part.split(";", 1)[0].upper()
        params = name_part.split(";")[1:]
        if name == "UID":
            card.uid = value.strip()
        elif name == "FN":
            card.fn = value.strip()
        elif name == "ORG":
            card.org = value.replace("\\;", ";").split(";")[0].strip()
        elif name == "EMAIL":
            if value.strip():
                card.emails.append(value.strip())
        elif name == "TEL":
            if value.strip():
                card.phones.append(value.strip())
        elif name == "ADR":
            parts = value.split(";")
            parts += [""] * (7 - len(parts))
            card.addresses.append(
                {
                    "label": next((p.split("=", 1)[-1] for p in params if "TYPE" in p.upper()), ""),
                    "street": parts[2].strip(),
                    "city": parts[3].strip(),
                    "region": parts[4].strip(),
                    "postal_code": parts[5].strip(),
                    "country": parts[6].strip(),
                }
            )
    return card
