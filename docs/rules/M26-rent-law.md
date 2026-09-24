# M26 Mieterhöhung: Regelwerk (Quellenregister-Ergänzung, Entwurf)

| Field | Content |
| --- | --- |
| ID | `M26-RL` (codes in `rent_law_rule`) |
| Title | Mieterhöhung: Wartefrist, Kappungsgrenze, Begründung, Zustimmung |
| Scope | Wohnraummietverträge in Deutschland; Kappungsgebiete je Land und Gemeinde (`rent_cap_area`, Admin-Pflege) |
| Source status | Addition to annex C requested by the operator on 24.09.2026. Statute text of §§ 558, 558a, 558b BGB retrieved from gesetze-im-internet.de on 24.09.2026; all six seed values match the text. Rules stay `draft` until the operator releases them. Release per rule only by the operator (RA) via `PUT /platform/rent-law/rules/{code}` |
| Acceptance case | none in annex D yet; tests `tests/integration/test_m26_letting.py::test_rent_law_rules_and_cap_area` |
| Implementation | `mhvp.letting.rentlaw`, migration 0030 |
| Change reason | M26-01 decision of the operator, 24.09.2026. Seed values and letter template reviewed by the operator (RA) on 24.09.2026; release per rule is recorded in the backend (`released_by`, `released_at`) |

## Seed values (to verify against the statute text)

| Code | Value | Norm | Source URL |
| --- | --- | --- | --- |
| waiting_months | 15 | § 558 Abs. 1 BGB | https://www.gesetze-im-internet.de/bgb/__558.html |
| cap_percent | 20 | § 558 Abs. 3 BGB | https://www.gesetze-im-internet.de/bgb/__558.html |
| cap_window_years | 3 | § 558 Abs. 3 BGB | https://www.gesetze-im-internet.de/bgb/__558.html |
| comparison_flats_min | 3 | § 558a Abs. 2 Nr. 4 BGB | https://www.gesetze-im-internet.de/bgb/__558a.html |
| consent_months | 2 | § 558b Abs. 2 BGB | https://www.gesetze-im-internet.de/bgb/__558b.html |
| effective_month | 3 | § 558b Abs. 1 BGB | https://www.gesetze-im-internet.de/bgb/__558b.html |

Modernisation (§ 559 BGB), graduated rent (§ 557a BGB) and index rent (§ 557b BGB) are
registered as bases; no automatic check exists for them. The letter template
(`GET /letting/rent-increases/{id}/letter`) is a draft with visible placeholders and needs
the operator's legal review before use. Sending stays behind G3.

## Cap areas NRW (migration 0031)

Source: Mieterschutzverordnung NRW of 28.01.2025 (GV. NRW. S. 111), amended 28.10.2025
(GV. NRW. S. 848), § 1 Abs. 2 with annex; retrieved from recht.nrw.de on 24.09.2026. The 57
municipalities of the annex are seeded with a 15 % cap (§ 558 Abs. 3 Satz 2 BGB), valid
01.03.2025 to 28.02.2030 (§ 3 Abs. 2). The list was compared name by name with the annex PDF
(`tests/unit/test_m26_cap_areas.py` checks count and uniqueness). Other states are not seeded;
the platform administrator maintains them. Earlier NRW ordinances (2020) are not seeded.

Matching: municipality code first; otherwise by name within the property's state. A missing
state or a match by name prefix (for example "Monheim am Rhein" to "Monheim") is flagged for
review.

## Known gaps (not checked automatically)

- § 558 Abs. 1 Satz 2 BGB: request at the earliest one year after the last increase.
- § 558a Abs. 2 Nr. 2 and Abs. 3 BGB: rent database as a fourth means; information from a
  qualified rent index must be stated even with another means.
- § 558b Abs. 2 Satz 2 BGB: action for consent within three further months.
