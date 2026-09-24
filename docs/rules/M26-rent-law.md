# M26 Mieterhöhung: Regelwerk (Quellenregister-Ergänzung, Entwurf)

| Field | Content |
| --- | --- |
| ID | `M26-RL` (codes in `rent_law_rule`) |
| Title | Mieterhöhung: Wartefrist, Kappungsgrenze, Begründung, Zustimmung |
| Scope | Wohnraummietverträge in Deutschland; Kappungsgebiete je Land und Gemeinde (`rent_cap_area`, Admin-Pflege) |
| Source status | Addition to annex C requested by the operator on 24.09.2026. Retrieval from gesetze-im-internet.de not yet possible (network egress blocked); all rules `draft`, `source_verified=false`. Release per rule only by the operator (RA) via `PUT /platform/rent-law/rules/{code}` |
| Acceptance case | none in annex D yet; tests `tests/integration/test_m26_letting.py::test_rent_law_rules_and_cap_area` |
| Implementation | `mhvp.letting.rentlaw`, migration 0030 |
| Change reason | M26-01 decision of the operator, 24.09.2026 |

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
