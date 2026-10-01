"""V10 / U07-01: the chart seed carries a key distribution per unambiguous cost account and a
statement kind for 028100; the seed stays idempotent and keeps maintained values."""

from decimal import Decimal

from mhvp.accounting.defaults import COSTS, TEMPLATE_ACCOUNTS, fill_unset, merge_missing

ROWS = {r["number"]: r for r in TEMPLATE_ACCOUNTS}


def test_split_only_for_accounts_with_unambiguous_key() -> None:
    for number, _, _, key, _ in COSTS:
        split = ROWS[number]["allocation_split"]
        if key is None:
            assert split == []
        else:
            assert split == [{"key_code": key, "share_percent": "100"}]
            assert sum(Decimal(i["share_percent"]) for i in split) == Decimal("100")
    assert ROWS["041805"]["allocation_split"] == []  # mixed account stays open
    assert ROWS["001200"]["allocation_split"] == []


def test_interest_account_is_hoa_fee_draft() -> None:
    assert ROWS["028100"]["statement_kind"] == "hoa_fee"
    assert ROWS["028100"]["review_status"] == "entwurf"
    assert ROWS["028101"]["statement_kind"] == "reserve"


def test_seed_idempotent_and_keeps_maintained_values() -> None:
    legacy = [{k: v for k, v in r.items() if k != "allocation_split"} for r in TEMPLATE_ACCOUNTS]
    maintained = dict(legacy[[r["number"] for r in legacy].index("040100")])
    maintained["allocation_split"] = [
        {"key_code": "WFL", "share_percent": "60"},
        {"key_code": "PERS", "share_percent": "40"},
    ]
    rows = [maintained if r["number"] == "040100" else r for r in legacy]
    filled, changed = fill_unset(rows, TEMPLATE_ACCOUNTS)
    assert changed
    by = {r["number"]: r for r in filled}
    assert by["040100"]["allocation_split"] == maintained["allocation_split"]
    assert by["040300"]["allocation_split"] == ROWS["040300"]["allocation_split"]
    again, changed2 = fill_unset(filled, TEMPLATE_ACCOUNTS)
    assert not changed2
    assert again == filled
    assert merge_missing(again, TEMPLATE_ACCOUNTS) == again
