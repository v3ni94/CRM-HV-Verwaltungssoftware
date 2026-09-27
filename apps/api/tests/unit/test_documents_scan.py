"""ClamAV scan before storing documents (operator decision 27.09.2026): INSTREAM client
against a fake clamd on a local TCP port, reply parsing and the mode logic of
``scan_before_store`` (finding rejects, warn stores on outage, enforce refuses). The audit
entries are covered by the integration test in ``test_m6_documents.py``."""

import asyncio
import socket
import struct
import threading
from collections.abc import Iterator
from typing import Any

import pytest

from mhvp.core.problems import ProblemError
from mhvp.documents import scan
from mhvp.documents.scan import ClamdScanner, ScanStatus, parse_reply
from tests.conftest import make_settings

EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class FakeClamd:
    """Answers FOUND when the streamed bytes contain the EICAR string, OK otherwise."""

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        self.received: list[bytes] = []
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                cmd = b""
                while not cmd.endswith(b"\0"):
                    cmd += conn.recv(1)
                if cmd == b"zPING\0":
                    conn.sendall(b"PONG\0")
                    continue
                data = b""
                while True:
                    (size,) = struct.unpack("!I", _exact(conn, 4))
                    if size == 0:
                        break
                    data += _exact(conn, size)
                self.received.append(data)
                if EICAR in data:
                    conn.sendall(b"stream: Eicar-Test-Signature FOUND\0")
                else:
                    conn.sendall(b"stream: OK\0")

    def close(self) -> None:
        self.sock.close()


def _exact(conn: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        part = conn.recv(n - len(buf))
        if not part:
            raise ConnectionError
        buf += part
    return buf


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def clamd() -> Iterator[FakeClamd]:
    server = FakeClamd()
    yield server
    server.close()


def _settings(mode: str, port: int) -> Any:
    return make_settings(
        clamav_mode=mode, clamav_host="127.0.0.1", clamav_port=port, clamav_timeout_seconds=2
    )


def test_parse_reply_variants() -> None:
    assert parse_reply("stream: OK").status is ScanStatus.CLEAN
    found = parse_reply("stream: Eicar-Test-Signature FOUND")
    assert (found.status, found.detail) == (ScanStatus.INFECTED, "Eicar-Test-Signature")
    error = parse_reply("INSTREAM size limit exceeded. ERROR")
    assert (error.status, error.detail) == (ScanStatus.ERROR, "INSTREAM size limit exceeded.")
    assert parse_reply("garbage").status is ScanStatus.ERROR


def test_instream_client_streams_chunks_and_reads_verdict(clamd: FakeClamd) -> None:
    scanner = ClamdScanner("127.0.0.1", clamd.port, 2)
    assert scanner.ping()
    big = b"a" * (scan.CHUNK_SIZE * 2 + 17)
    assert scanner.scan(big).status is ScanStatus.CLEAN
    assert clamd.received[-1] == big
    result = scanner.scan(b"prefix" + EICAR)
    assert (result.status, result.detail) == (ScanStatus.INFECTED, "Eicar-Test-Signature")


def test_unreachable_scanner_answers_error() -> None:
    scanner = ClamdScanner("127.0.0.1", _free_port(), 1)
    assert not scanner.ping()
    assert scanner.scan(b"x") == scan.ScanResult(ScanStatus.ERROR, "unreachable")


@pytest.fixture
def journal(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    async def fake(session: Any, **kwargs: Any) -> None:
        entries.append(kwargs)

    monkeypatch.setattr(scan, "_journal", fake)
    return entries


def _run(settings: Any, data: bytes) -> Any:
    import uuid

    return asyncio.run(
        scan.scan_before_store(
            None,  # type: ignore[arg-type]
            settings,
            tenant_id=uuid.uuid4(),
            data=data,
            filename="test.txt",
            sha256="00",
            source="upload",
            actor_user_id=None,
        )
    )


def test_mode_off_skips_scan(journal: list[dict[str, Any]]) -> None:
    assert _run(_settings("off", _free_port()), EICAR) is None
    assert journal == []


@pytest.mark.parametrize("mode", ["warn", "enforce"])
def test_finding_rejects_with_doc_0008_and_journals_signature(
    clamd: FakeClamd, journal: list[dict[str, Any]], mode: str
) -> None:
    with pytest.raises(ProblemError) as info:
        _run(_settings(mode, clamd.port), EICAR)
    assert info.value.error.code == "MHVP-DOC-0008"
    assert info.value.status == 422
    assert journal[0]["type"] == scan.EVENT_REJECTED
    assert journal[0]["payload"]["signature"] == "Eicar-Test-Signature"
    assert journal[0]["payload"]["filename"] == "test.txt"


def test_clean_file_passes(clamd: FakeClamd, journal: list[dict[str, Any]]) -> None:
    result = _run(_settings("enforce", clamd.port), b"harmless")
    assert result.status is ScanStatus.CLEAN
    assert journal == []


def test_warn_mode_stores_on_outage_and_journals_gap(journal: list[dict[str, Any]]) -> None:
    result = _run(_settings("warn", _free_port()), b"harmless")
    assert result.status is ScanStatus.ERROR
    assert journal[0]["type"] == scan.EVENT_SKIPPED
    assert journal[0]["payload"]["reason"] == "unreachable"


def test_enforce_mode_refuses_on_outage_with_doc_0009(journal: list[dict[str, Any]]) -> None:
    with pytest.raises(ProblemError) as info:
        _run(_settings("enforce", _free_port()), b"harmless")
    assert info.value.error.code == "MHVP-DOC-0009"
    assert info.value.status == 503
    assert journal == []


def test_prod_settings_require_enforce() -> None:
    from pydantic import SecretStr, ValidationError

    prod: dict[str, Any] = {
        "env": "prod",
        "s3_endpoint_url": "https://s3.example",
        "s3_access_key_id": SecretStr("a"),
        "s3_secret_access_key": SecretStr("b"),
        "master_key": SecretStr("k"),
        "jwt_private_key": SecretStr("p"),
    }
    with pytest.raises(ValidationError, match="MHVP_CLAMAV_MODE"):
        make_settings(**prod)
    assert make_settings(**prod, clamav_mode="enforce").clamav_mode == "enforce"
