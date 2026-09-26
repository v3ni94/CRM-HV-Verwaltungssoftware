# Kostenverteilung (7.8, W03)

| Field | Content |
| --- | --- |
| ID | W03 |
| Title | Kostenverteilung |
| Scope | WEG annual statement (M24), cost items with allocation key; sub communities, entrances and user groups modelled as keys with values on part of the units |
| Source status | annex C R02 (§ 16, § 21 WEG) for the requirement that a partial scope needs a documented basis; the term check on the basis text is product protection, no legal claim |
| Acceptance case | D18, `tests/integration/test_m24_hoa.py::test_d18_sub_community_without_basis_blocks_release` |
| Implementation | `mhvp.hoa.calc.unit_weights` (units without a value are outside the key's scope), `mhvp.hoa.package.blocking_checks` finding `scope_unfounded` when the key covers only part of the units and the basis names no Beschluss, Teilungserklärung or Gemeinschaftsordnung; the internal approval is refused while the finding exists |
| Change reason | A18 of the gap list 26.09.2026; open: structured source link on the cost item instead of the term check |
