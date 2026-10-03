"""AJ19 guards on the test suite itself (GAI-612, GAI-616, GAI-617).

* every annex D case (D01 to D49) is named by at least one test, by name token ``dNN`` or
  by the marker ``annex_d("DNN")``; cases with a single test are an exact ratchet list
  (rule 8 asks for two independent tests, the list may only shrink),
* CI runs pytest with ``MHVP_REQUIRE_INTEGRATION=1`` so integration tests fail instead of
  being skipped, and the skip guard in tests/conftest.py treats a missing schema package
  (xmlschema) as a failure in such a run,
* xmlschema is a locked runtime dependency and importable here.
"""

import ast
import importlib.util
import re
from collections import defaultdict
from pathlib import Path

from tests.conftest import REQUIRED_TEST_PACKAGES, forbidden_skip_reason

TESTS = Path(__file__).resolve().parents[1]
REPO = TESTS.parents[2]
CASES = [f"D{i:02d}" for i in range(1, 50)]
_NAME_TOKEN = re.compile(r"(?:^|_)d(\d\d)(?=_|$)")

# Cases covered by exactly one test today (GAI-612, rule 8). Remove an entry once a second
# independent test names the case; adding an entry is not allowed.
SINGLE_TEST_CASES: frozenset[str] = frozenset()  # fmt: skip


def _marker_cases(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    found: set[str] = set()
    for dec in func.decorator_list:
        if isinstance(dec, ast.Call) and ast.unparse(dec.func).endswith("mark.annex_d"):
            found |= {a.value for a in dec.args if isinstance(a, ast.Constant)}
    return found


def annex_d_coverage() -> dict[str, set[str]]:
    cover: dict[str, set[str]] = defaultdict(set)
    for path in TESTS.rglob("test_*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            cases = {f"D{n}" for n in _NAME_TOKEN.findall(node.name[5:])}
            for case in cases | _marker_cases(node):
                cover[case].add(f"{path.name}::{node.name}")
    return cover


def test_every_annex_d_case_is_named_by_a_test() -> None:
    cover = annex_d_coverage()
    assert [c for c in CASES if not cover[c]] == []


def test_single_test_cases_only_shrink() -> None:
    cover = annex_d_coverage()
    single = {c for c in CASES if len(cover[c]) == 1}
    assert single == SINGLE_TEST_CASES


def test_d16_is_named_by_two_independent_tests() -> None:
    assert len(annex_d_coverage()["D16"]) >= 2


def test_ci_requires_integration_for_the_pytest_step() -> None:
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    step = ci.split("- name: Tests", 1)[1].split("- name:", 1)[0]
    assert 'MHVP_REQUIRE_INTEGRATION: "1"' in step
    assert "run: uv run pytest" in step


def test_skip_guard_reasons() -> None:
    assert forbidden_skip_reason("integration test not executed: no database")
    assert forbidden_skip_reason("could not import 'xmlschema': No module named 'xmlschema'")
    assert not forbidden_skip_reason("could not import 'lxml': No module named 'lxml'")
    assert not forbidden_skip_reason("proven with prepared record: ledger")


def test_required_schema_packages_are_installed() -> None:
    for name in REQUIRED_TEST_PACKAGES:
        assert importlib.util.find_spec(name) is not None, name
