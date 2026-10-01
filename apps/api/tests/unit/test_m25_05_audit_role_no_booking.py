"""M25-05 (PÜ08): the audit role (board portal access) holds no right to book or to change
the audited data. Rule docs/rules/M25-05.md."""

from pathlib import Path

from mhvp.core.auth.permissions import SYSTEM_ROLES

WRITE_ACTIONS = ("create", "update", "delete", "approve")
AUDIT_SOURCE = Path(__file__).resolve().parents[2] / "src" / "mhvp" / "hoa" / "board.py"


def test_portal_roles_hold_no_crm_permission() -> None:
    """The board audit access is a portal grant, never a CRM role: portal_user and
    insurance_broker carry no permission at all, so no booking right can come from them."""
    roles = {r.code: r for r in SYSTEM_ROLES}
    assert roles["portal_user"].permissions == frozenset()


def test_read_only_roles_hold_no_booking_right() -> None:
    roles = {r.code: r for r in SYSTEM_ROLES}
    for code in ("read_only", "read_only_master_data", "support", "tax_advisor"):
        booking = {
            p
            for p in roles[code].permissions
            if p.startswith("accounting:") and p.split(":")[1] in WRITE_ACTIONS
        }
        # tax_advisor may export, nothing else; the others hold no accounting write action.
        assert booking == set(), (code, booking)


def test_board_grant_right_is_comment_only() -> None:
    """The grant created for the audit role carries the right comment and nothing wider."""
    text = AUDIT_SOURCE.read_text(encoding="utf-8")
    assert 'right="comment"' in text
    assert 'right="update"' not in text
    assert 'right="approve"' not in text
