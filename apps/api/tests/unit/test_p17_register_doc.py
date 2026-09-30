"""P17: Entwurf des Verarbeitungsverzeichnisses mit Prüfhinweis, Lücken, nur aktive Einträge."""

from datetime import date

from mhvp.privacy.models import PrivacyRegisterEntry
from mhvp.privacy.register_doc import REVIEW_NOTICE, render


def _entry(**kw: object) -> PrivacyRegisterEntry:
    base: dict[str, object] = {
        "kind": "processor",
        "name": "Dienst A",
        "data_categories": [],
        "data_subjects": [],
        "third_country": False,
        "avv_status": "none",
        "legal_review_status": "open",
        "active": True,
    }
    return PrivacyRegisterEntry(**{**base, **kw})


def test_render_contains_notice_and_gaps() -> None:
    text = render(
        "Mandant",
        [
            _entry(),
            _entry(name="Dienst B", avv_status="confirmed", avv_confirmed_on=date(2026, 9, 1)),
            _entry(name="Alt", active=False),
            _entry(name="Übermittlung", kind="processing_activity", third_country=True),
        ],
        date(2026, 9, 30),
    )
    assert REVIEW_NOTICE in text
    assert "Stand: 30.09.2026" in text
    assert "Dienst A: AVV-Nachweis fehlt" in text
    assert "Dienst B: AVV-Nachweis fehlt" not in text
    assert "bestätigt am 01.09.2026" in text
    assert "Alt" not in text
    assert "Übermittlung: Drittlandübermittlung ohne dokumentierte Garantie" in text
    assert "\u2014" not in text
    assert "\u2013" not in text
