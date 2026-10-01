"""RSA key material for EBICS subscribers (M11-01, AE23, rule M11-11).

Sources (freely available on ebics.de, checked 01.10.2026):

* Die Deutsche Kreditwirtschaft, "Krypto LifeCycle EBICS", Version 1.4 vom 09.07.2025: RSA
  keys for all key pairs (A00x, X00x, E00x) need at least 2,048 bits, which runs out 11/2027;
  from 11/2027 at least 4,096 bits; below 2,048 bits expired since 11/2021. EBICS 2.4 expired
  since 11/2023, 2.5 and 3.0 are supported.
* Die Deutsche Kreditwirtschaft, "EBICS Sicherheitsempfehlungen für Kunden", Stand
  04.05.2026, section 3.1.2/3.2: the signature key should stay with the signing person (chip
  card recommended); authentication and encryption keys of portal solutions are kept in the
  operator's environment.

Key versions (A005, A006, X002, E002) are the identifiers used by the bank contract and the
existing runbook; how a key of a version is encoded on the wire and how the hash value of the
initialisation letter is computed is part of the EBICS specification and is left to the
transport (``mhvp.banking.ebics_transport``, open question AE23-02). This module only creates,
loads and describes RSA keys; it never talks to a bank.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEY_SIZES = (2048, 3072, 4096)
DEFAULT_KEY_BITS = 4096
# Krypto LifeCycle EBICS V1.4: 4,096 bits from 11/2027, 2,048 bits run out then.
STRICT_FROM = date(2027, 11, 1)
SIGNATURE_VERSIONS = ("A005", "A006")
AUTHENTICATION_VERSION = "X002"
ENCRYPTION_VERSION = "E002"
EBICS_VERSIONS = ("2.5", "3.0")
SOURCES = (
    "DK Krypto LifeCycle EBICS V1.4 (09.07.2025)",
    "DK EBICS Sicherheitsempfehlungen für Kunden (Stand 04.05.2026), Kapitel 3.1 und 3.2",
    "DFÜ-Abkommen Anlage 3 V26.11 (09.04.2026), Kapitel 9.2.1 und 9.2.2",
)


def min_key_bits(today: date) -> int:
    """Minimum RSA length accepted on ``today`` (Krypto LifeCycle EBICS V1.4)."""
    return 4096 if today >= STRICT_FROM else 2048


def runs_out(bits: int) -> date | None:
    """Date from which a key of ``bits`` is no longer accepted, if the source names one."""
    return None if bits >= 4096 else STRICT_FROM


def check_key_bits(bits: int, today: date) -> None:
    if bits not in KEY_SIZES:
        raise ValueError("Schlüssellänge muss 2048, 3072 oder 4096 Bit betragen.")
    if bits < min_key_bits(today):
        raise ValueError(
            f"Schlüssellänge {bits} Bit ist nicht mehr zulässig (Krypto LifeCycle EBICS: "
            f"mindestens {min_key_bits(today)} Bit)."
        )


@dataclass(frozen=True)
class KeyPair:
    private_pem: str
    public_pem: str
    bits: int


def generate_key_pair(bits: int) -> KeyPair:
    """New RSA key pair (public exponent 65537). The private key is returned as unencrypted
    PKCS#8 PEM only to be stored in an ``EncryptedText`` column right away; it is never
    logged and never returned by the API."""
    if bits not in KEY_SIZES:
        raise ValueError("Schlüssellänge muss 2048, 3072 oder 4096 Bit betragen.")
    key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("ascii")
    )
    return KeyPair(private_pem=private_pem, public_pem=public_pem, bits=bits)


def load_public_key(pem: str) -> rsa.RSAPublicKey:
    """Parses a PEM public key (SubjectPublicKeyInfo or PKCS#1); only RSA is accepted."""
    try:
        data = pem.strip().encode("ascii")
        key = serialization.load_pem_public_key(data)
    except (ValueError, UnicodeEncodeError):
        raise ValueError("Öffentlicher Schlüssel ist kein lesbarer PEM-Schlüssel.") from None
    if not isinstance(key, rsa.RSAPublicKey):
        raise ValueError("Öffentlicher Schlüssel muss ein RSA-Schlüssel sein.")
    return key


def normalised_public_pem(pem: str) -> str:
    key = load_public_key(pem)
    return key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")


def public_key_bits(pem: str) -> int:
    return load_public_key(pem).key_size


def public_key_sha256(pem: str) -> str:
    """Internal SHA-256 (hex, upper case) over the DER SubjectPublicKeyInfo. It identifies a
    key inside the platform; it is not the hash value of the EBICS initialisation letter."""
    der = load_public_key(pem).public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(der).hexdigest().upper()


def exponent_modulus_hex(pem: str) -> tuple[str, str]:
    """Public exponent and modulus as upper case hexadecimal without leading zeros, as data
    for the letter view. The letter hash itself comes from the transport (AE23-02)."""
    numbers = load_public_key(pem).public_numbers()
    return format(numbers.e, "X"), format(numbers.n, "X")


def private_matches_public(private_pem: str, public_pem: str) -> bool:
    key = serialization.load_pem_private_key(private_pem.encode("ascii"), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        return False
    return key.public_key().public_numbers() == load_public_key(public_pem).public_numbers()


def normalise_hash(value: str) -> str:
    """Hash value as typed from a letter: blanks, colons and line breaks removed, upper case."""
    return "".join(ch for ch in value if ch not in " :\t\r\n-").upper()
