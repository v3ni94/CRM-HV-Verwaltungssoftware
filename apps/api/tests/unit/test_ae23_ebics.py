"""AE23 / M11-01: EBICS key policy, C53 container handling, connector seam and transport
default, without network and without database (rule M11-11)."""

from __future__ import annotations

from datetime import date

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from mhvp.banking import ebics_connector, ebics_keys, ebics_transport
from mhvp.banking.connectors import BankAccountInfo, BankConnector, ConnectorNotSupportedError
from mhvp.banking.ebics_connector import EbicsConnector, parse_c53, unpack_c53
from mhvp.banking.ebics_transport import (
    C53,
    EbicsClientKeys,
    EbicsSubscriberRef,
    UnavailableEbicsTransport,
)
from mhvp.core.problems import ProblemError
from tests.ebics_fake import FakeEbicsBank, c53_zip

IBAN = "DE02120300000000202051"
OTHER = "DE89370400440532013000"
REF = EbicsSubscriberRef("HOST1", "PARTNER1", "USER1", "https://ebics.example", "3.0", "A006")


def camt(stmt_id: str, iban: str, entries: list[tuple[str, str, str]]) -> bytes:
    rows = "".join(
        f'<Ntry><Amt Ccy="EUR">{amount}</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>'
        f"<BookgDt><Dt>{day}</Dt></BookgDt><ValDt><Dt>{day}</Dt></ValDt>"
        f"<AcctSvcrRef>{ref}</AcctSvcrRef></Ntry>"
        for ref, amount, day in entries
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt>'
        "<GrpHdr><MsgId>M1</MsgId><CreDtTm>2026-02-01T08:00:00</CreDtTm></GrpHdr>"
        f"<Stmt><Id>{stmt_id}</Id><Acct><Id><IBAN>{iban}</IBAN></Id><Ccy>EUR</Ccy></Acct>"
        f"{rows}</Stmt></BkToCstmrStmt></Document>"
    ).encode()


def test_key_policy_follows_krypto_lifecycle() -> None:
    assert ebics_keys.min_key_bits(date(2026, 10, 1)) == 2048
    assert ebics_keys.min_key_bits(date(2027, 10, 31)) == 2048
    assert ebics_keys.min_key_bits(date(2027, 11, 1)) == 4096
    assert ebics_keys.DEFAULT_KEY_BITS == 4096
    assert ebics_keys.runs_out(2048) == date(2027, 11, 1)
    assert ebics_keys.runs_out(4096) is None
    ebics_keys.check_key_bits(2048, date(2026, 10, 1))
    with pytest.raises(ValueError, match="mindestens 4096"):
        ebics_keys.check_key_bits(3072, date(2027, 11, 1))
    with pytest.raises(ValueError, match="2048, 3072 oder 4096"):
        ebics_keys.check_key_bits(1024, date(2026, 10, 1))


def test_generated_key_pair_and_public_key_data() -> None:
    pair = ebics_keys.generate_key_pair(2048)
    assert "PRIVATE KEY" in pair.private_pem
    assert "PUBLIC KEY" in pair.public_pem
    assert ebics_keys.private_matches_public(pair.private_pem, pair.public_pem)
    assert ebics_keys.public_key_bits(pair.public_pem) == 2048
    digest = ebics_keys.public_key_sha256(pair.public_pem)
    assert len(digest) == 64
    assert digest == digest.upper()
    exponent, modulus = ebics_keys.exponent_modulus_hex(pair.public_pem)
    assert exponent == "10001"
    assert len(modulus) == 512
    other = ebics_keys.generate_key_pair(2048)
    assert not ebics_keys.private_matches_public(other.private_pem, pair.public_pem)
    with pytest.raises(ValueError, match="Schlüssellänge"):
        ebics_keys.generate_key_pair(1024)


def test_public_key_upload_validation() -> None:
    with pytest.raises(ValueError, match="PEM"):
        ebics_keys.load_public_key("kein Schlüssel")
    ec_pem = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    with pytest.raises(ValueError, match="RSA"):
        ebics_keys.load_public_key(ec_pem)
    pair = ebics_keys.generate_key_pair(2048)
    assert ebics_keys.normalised_public_pem("\n" + pair.public_pem + "\n") == pair.public_pem
    assert ebics_keys.normalise_hash("ab:cd ef\n01-23") == "ABCDEF0123"


def test_c53_order_is_the_btf_of_anlage_3() -> None:
    assert C53.order_type == "C53"
    assert C53.btf == "EOP/DE//camt.053/ZIP"


def test_unpack_c53_names_and_skips() -> None:
    content = c53_zip(
        {
            f"2026-02-01_C53_{IBAN}_EUR_000001.xml": camt(
                "S1", IBAN, [("R1", "10.00", "2026-01-15")]
            ),
            "auszug.xml": camt("S2", OTHER, [("R2", "5.00", "2026-01-16")]),
            "liesmich.txt": b"x",
        }
    )
    members, skipped = unpack_c53(content)
    assert skipped == ["liesmich.txt"]
    by_name = {m.name: m for m in members}
    first = by_name[f"2026-02-01_C53_{IBAN}_EUR_000001.xml"]
    assert first.name_conforms
    assert first.created_on == date(2026, 2, 1)
    assert first.account_hint == IBAN
    assert len(first.sha256) == 64
    assert by_name["auszug.xml"].name_conforms is False
    parsed, _ = parse_c53(content)
    assert {p.statements[0].iban for _, p in parsed} == {IBAN, OTHER}


def test_unpack_c53_rejects_bad_archives(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="ZIP"):
        unpack_c53(b"no zip")
    with pytest.raises(ValueError, match=r"a\.xml: Die Datei ist kein lesbares XML"):
        parse_c53(c53_zip({"a.xml": b"<x"}))
    with pytest.raises(ValueError, match=r"b\.xml"):
        parse_c53(c53_zip({"b.xml": b"<?xml version='1.0'?><Document/>"}))
    monkeypatch.setattr(ebics_connector, "MAX_MEMBERS", 1)
    with pytest.raises(ValueError, match="zu viele"):
        unpack_c53(c53_zip({"a.xml": b"1", "b.xml": b"2"}))
    monkeypatch.setattr(ebics_connector, "MAX_MEMBERS", 10)
    monkeypatch.setattr(ebics_connector, "MAX_MEMBER_BYTES", 10)
    with pytest.raises(ValueError, match="zu groß"):
        unpack_c53(c53_zip({"a.xml": b"x" * 100}))


def test_connector_seam_with_fake_bank() -> None:
    bank = FakeEbicsBank()
    auth, enc = ebics_keys.generate_key_pair(2048), ebics_keys.generate_key_pair(2048)
    bank.send_hia(REF, auth.public_pem, enc.public_pem)
    keys = EbicsClientKeys(
        auth.private_pem, enc.private_pem, bank.bank_auth.public_pem, bank.bank_enc.public_pem
    )
    bank.zip_content = c53_zip(
        {
            "a.xml": camt(
                "S1", IBAN, [("R1", "10.00", "2026-01-15"), ("R2", "1.00", "2026-03-01")]
            ),
            "b.xml": camt("S2", OTHER, [("R3", "5.00", "2026-01-16")]),
        }
    )
    connector = EbicsConnector(REF, keys, bank)
    assert isinstance(connector, BankConnector)
    txs = connector.fetch_transactions(
        BankAccountInfo(iban="DE02 1203 0000 0000 2020 51"), date(2026, 1, 1), date(2026, 1, 31)
    )
    assert [t.bank_reference for t in txs] == ["R1"]
    assert bank.downloads == [("EOP/DE//camt.053/ZIP", date(2026, 1, 1), date(2026, 1, 31))]
    assert connector.consent_status("x").status == "not_required"
    for call in (
        lambda: connector.search_bank("x"),
        lambda: connector.list_accounts(),
        lambda: connector.fetch_balance(BankAccountInfo(iban=IBAN)),
        lambda: connector.submit_payment_batch("b"),
    ):
        with pytest.raises(ConnectorNotSupportedError):
            call()


def test_transport_default_is_unavailable() -> None:
    ebics_transport.set_transport_factory(None)
    transport = ebics_transport.get_transport()
    assert isinstance(transport, UnavailableEbicsTransport)
    assert ebics_transport.is_available() is False
    assert transport.letter_hash("x", "X002", "3.0") is None
    with pytest.raises(ProblemError) as info:
        transport.send_ini(REF, "pem")
    assert info.value.error.code == "MHVP-BANK-0050"
    bank = FakeEbicsBank()
    ebics_transport.set_transport_factory(lambda: bank)
    try:
        assert ebics_transport.get_transport() is bank
        assert ebics_transport.is_available()
    finally:
        ebics_transport.set_transport_factory(None)
    assert not ebics_transport.is_available()
