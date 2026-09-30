"""Offline check against compromised passwords (M2-05, operator decision 9 a of 30.09.2026).

No network call is ever made. The check compares the upper case SHA-1 hex digest of the
password (the format of the public "Pwned Passwords" range files) against

* a small bundled list (``BUNDLED_SHA1``, widely known weak passwords of at least 12
  characters; shorter ones already fail the minimum length), and
* optionally a larger local hash file, one ``SHA1`` or ``SHA1:count`` per line, sorted or not.
  Its path comes from the environment variable ``MHVP_BREACHED_PASSWORDS_FILE``; the operator
  provides and updates the file. A missing or unreadable file is logged and ignored (the
  bundled list still applies), so login and password change never fail because of it.

Further sources can be registered with ``register_source`` (interface ``BreachedSource``).
Both the password as entered and its lower case form are checked.
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)

ENV_FILE = "MHVP_BREACHED_PASSWORDS_FILE"


class BreachedSource(Protocol):
    def contains(self, sha1_hex_upper: str) -> bool: ...


BUNDLED_SHA1: frozenset[str] = frozenset(
    {
        "0071877D20A65C02D9A1654F109B97DC61416D1A",
        "08D7DE6CBF6C3FA0A26E094E5115BCD1A0E3D2C3",
        "095115C3CFBC016AC0918BDF22DF9C5FEB185BB9",
        "1FD7539A0DC535C10B55C9DC12A32B3C44DFE73A",
        "2130FB49CFFF656805A8262430C5DAFD70A0C25C",
        "26672BF11F3ABFA225D99958931AF9DC6AE5BDB8",
        "291DDA6A7FE504E9BA71145508D5F8EAA471E0C4",
        "2AD8BE0D5458D76A178BC7F827980F6C491B7CFF",
        "2E38D47E05AAA48CE6B8A39DA5AC7FB6440813D4",
        "34633B129BAC06A85C99D50990B0EBBF2190815A",
        "3533DC31B5B114D597E3AA2D198BC0965D17905F",
        "38A3A41958C15CBC44FE311F77E4E5B70B58E24E",
        "3BC21FD44CE4590137481F2755C0C8DBEDFFB56B",
        "3E49C3E4513E92806634F552518EA6BBAD14FA60",
        "46BABE61E2CA39C790C4524F4BA42E78A4CDECE9",
        "476E251CC54B60534F68D0F614FCC67950151353",
        "48B404FD4A6436435F28260E39774CD0DBBFB9E9",
        "56259DD1C4EA0117CD601FFF7AEFA0E8892A3B25",
        "5A8F70E725742EE64204353E700778B29F81B988",
        "5AD56F95E58809DF7AFAD232A414BB6A1F7EB7E3",
        "5C7FFA1C415252DBB6DADB28F86A6F00ED981472",
        "6CAAF02BE2851FCBD479BD7068617EA2F30B71BA",
        "712C982522DFFE90646090310276DB1D1EA4794F",
        "71DD07494C5EE54992A27746D547E25DEE01BD97",
        "79692ACE00DF5A255D5FAD842C109C31C999F265",
        "7EC8AA461C2C28BE905E1DFB0BE256A971AA6108",
        "82419490EE51953E4ACBB4C45051910740E200B7",
        "827A416FE85CFE0EE5FE301542182B3FE3DDA2BF",
        "87B7439E46BDD70FEA489439023727AA24EF5EB1",
        "892B152A73426DA7BD87611A508CC4D0B6C2574A",
        "8D993CCDF628E26E170A949EE2A3870455DBD8FA",
        "9517A04D3A898BCBD1E4E9999E265398C010A164",
        "9D1DBBBB6EC0A7C8420B81D71356C0A8DB1E5D66",
        "9F8469F55B74E784B907768D0B0323C99B2CB965",
        "A0C55FDF6B3C10909D8B570FA4219F941275E750",
        "A218508B1FCF715F754146A4EFA2C3B0C6869480",
        "A34A07FEA197C29103EBCB0D27BF525F09153050",
        "A5BD420F273D3954B24E73DD0C1AD015361A86BC",
        "A9527849C636E5CD1172BD9A6A199CDF3DCFDCAD",
        "AAC1D659EDF5B13FCFDA3DB1F05B983136A53086",
        "AE9030C665364EB2651D450E8321AE62DD51A726",
        "B3ACA92C793EE0E9B1A9B0A5F5FC044E05140DF3",
        "B5F50017653C165B94576300A4481EF80456AD35",
        "BF858D54F42DB43702A2D3B039CF953393FE580D",
        "C2311E92660DE47B456E721B0DABC9F857AB48F0",
        "C618D854BA68F12E9DADEB84A24FA528155D906F",
        "E4F7E8B171964C523A5811D72C015BE4DD5753EF",
        "E6B6AFBD6D76BB5D2041542D7D2E3FAC5BB05593",
        "EAA0879C83689209C26F553DCB0E2CBC3FA1052D",
        "EB4608CEBFCFD4DF81410CBD06507EA6AF978D9C",
        "EC8E3A329BDF47FDB08E2F22C45B7971D7A5CB5B",
        "F3BA381B6BAEF526BF70FF220B1DA4906989224B",
        "F766E1E8F4CD5A247079C0B3BEDADFF6A93D70C3",
    }
)


class _SetSource:
    def __init__(self, hashes: frozenset[str]) -> None:
        self._hashes = hashes

    def contains(self, sha1_hex_upper: str) -> bool:
        return sha1_hex_upper in self._hashes


class FileSource:
    """Hash file in the Pwned Passwords format, loaded once into memory."""

    def __init__(self, path: Path) -> None:
        hashes: set[str] = set()
        with path.open(encoding="ascii", errors="ignore") as handle:
            for line in handle:
                digest = line.split(":", 1)[0].strip().upper()
                if len(digest) == 40:
                    hashes.add(digest)
        self._hashes = frozenset(hashes)

    def __len__(self) -> int:
        return len(self._hashes)

    def contains(self, sha1_hex_upper: str) -> bool:
        return sha1_hex_upper in self._hashes


_sources: list[BreachedSource] = [_SetSource(BUNDLED_SHA1)]
_env_loaded = False


def register_source(source: BreachedSource) -> None:
    _sources.append(source)


def reset_sources() -> None:
    """Back to the bundled list only (tests)."""
    global _env_loaded
    _sources[:] = [_SetSource(BUNDLED_SHA1)]
    _env_loaded = False


def _load_env_file() -> None:
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    raw = os.environ.get(ENV_FILE)
    if not raw:
        return
    try:
        _sources.append(FileSource(Path(raw)))
    except OSError:
        logger.warning("breached password file %s not readable, bundled list only", raw)


def sha1_upper(password: str) -> str:
    return hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()


def is_breached(password: str) -> bool:
    _load_env_file()
    digests = {sha1_upper(password), sha1_upper(password.lower())}
    return any(source.contains(d) for source in _sources for d in digests)
