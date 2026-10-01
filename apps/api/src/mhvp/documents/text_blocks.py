"""AA11-01/02: operator text blocks (Informationsblatt, Anschreiben, § 35a) with release status.

Only the approved version of a code is printed. Without it the output keeps the marker
"Text nicht freigegeben". The software ships no legal text.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.documents.models import LegalTextBlock


async def approved_texts(
    session: AsyncSession, codes: tuple[str, ...] | None = None
) -> dict[str, str]:
    """Approved body per code (RLS limits to the tenant of the session)."""
    stmt = select(LegalTextBlock).where(LegalTextBlock.status == "approved")
    if codes:
        stmt = stmt.where(LegalTextBlock.code.in_(codes))
    return {row.code: row.body.strip() for row in (await session.scalars(stmt)).all()}


def status_by_code(texts: dict[str, str], codes: tuple[str, ...]) -> dict[str, str]:
    return {c: ("released" if c in texts else "not_released") for c in codes}
