"""GA14-05: XRechnung files from the generator checked by the official KoSIT validator.

Optional: runs only when ``MHVP_KOSIT_DIR`` holds the validator jar and the XRechnung
configuration (see ``scripts/kosit_validate.sh``) and ``java`` is available. Locally and in the
default CI job it is skipped and reported as not executed; the optional CI job
``xrechnung-kosit`` runs it (OPEN_QUESTIONS P05, AA02-03).
"""

import os
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from mhvp.accounting import xrechnung as x
from tests.unit.test_m13_xrechnung import SELLER, _data

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "kosit_validate.sh"
KOSIT_DIR = os.environ.get("MHVP_KOSIT_DIR")

pytestmark = pytest.mark.skipif(
    not KOSIT_DIR or shutil.which("java") is None or not SCRIPT.exists(),
    reason="KoSIT validator not available (MHVP_KOSIT_DIR, java); not executed",
)


def _variants() -> dict[str, bytes]:
    small = _data(
        seller=x.Seller(
            name="Timo Müller",
            address=SELLER.address,
            tax_number="000/0000/0000",
            register_number="HRA 1",
            payee_iban=SELLER.payee_iban,
            email="tm@example.org",
            phone="+49 2173 1",
            contact_name="Timo Müller",
        ),
        vat_percent=Decimal("0"),
        vat=Decimal("0.00"),
        gross=Decimal("100.00"),
        tax_exemption_reason="Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.",
    )
    return {"regelbesteuert.xml": x.build_xml(_data()), "kleinunternehmer.xml": x.build_xml(small)}


def test_generator_output_accepted_by_kosit(tmp_path: Path) -> None:
    files = []
    for name, xml in _variants().items():
        assert x.check_structure(xml) == []
        path = tmp_path / name
        path.write_bytes(xml)
        files.append(str(path))
    bash = shutil.which("bash") or "/bin/bash"
    result = subprocess.run(  # noqa: S603
        [bash, str(SCRIPT), *files], capture_output=True, text=True, timeout=300, check=False
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
