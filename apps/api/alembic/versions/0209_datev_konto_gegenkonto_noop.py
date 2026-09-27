"""datev_konto_gegenkonto_noop: M18-01 Folgepunkt. Forms Konto/Gegenkonto pairs per booking
in the DATEV Buchungsstapel export (``mhvp.accounting.reports.datev_csv``) instead of writing
an empty Gegenkonto (which failed the self check rule DC-14 on every line). Split bookings
without a single summing side are left out of the file and reported instead of dropped
silently (``skipped_split_bookings``, docs/rules/M18-06, Entwurf, Quellenstatus zu prüfen
durch Steuerberater). No schema change: ``ExportRun.params`` (JSONB, existing column) carries
the skipped list.

Revision ID: 0209
Revises: 0208
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0209"
down_revision: str | None = "0208"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
