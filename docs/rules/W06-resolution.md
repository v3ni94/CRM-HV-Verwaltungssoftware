# Beschluss und Buchung (7.8, W06)

| Field | Content |
| --- | --- |
| ID | W06 |
| Title | Beschluss und Buchung |
| Scope | WEG economic plan and statement (M24) |
| Source status | annex C as cited in 7.8; product protection for the snapshot binding |
| Acceptance case | `tests/integration/test_m24_hoa.py` (wrong snapshot hash rejected, G4 for issuing and posting) |
| Implementation | status `resolved` only with a binding resolution (positive, final, legally_binding) whose snapshot hash equals the calculated snapshot; advances from the plan only after resolution; a new version never carries the resolution |
| Change reason | M24, 23.09.2026 |
