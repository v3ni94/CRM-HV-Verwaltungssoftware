import pytest

from mhvp.core.db.rls import drop_tenant_rls_statements, tenant_rls_statements


def test_statements_enable_force_and_two_policies() -> None:
    statements = tenant_rls_statements("contact")
    assert statements[0] == 'ALTER TABLE "public"."contact" ENABLE ROW LEVEL SECURITY'
    assert statements[1] == 'ALTER TABLE "public"."contact" FORCE ROW LEVEL SECURITY'
    assert "CREATE POLICY tenant_access" in statements[2]
    assert "AS PERMISSIVE" in statements[2]
    assert "CREATE POLICY tenant_isolation" in statements[3]
    assert "AS RESTRICTIVE" in statements[3]
    for policy in statements[2:]:
        assert "USING (tenant_id = app_current_tenant_id())" in policy
        assert "WITH CHECK (tenant_id = app_current_tenant_id())" in policy


@pytest.mark.parametrize(
    "name", ['contact"; DROP TABLE x; --', "Contact", "1table", "a" * 64, "", "public.contact"]
)
def test_rejects_unsafe_identifiers(name: str) -> None:
    with pytest.raises(ValueError, match="invalid SQL identifier"):
        tenant_rls_statements(name)
    with pytest.raises(ValueError, match="invalid SQL identifier"):
        drop_tenant_rls_statements("contact", schema=name)


def test_drop_statements_reverse_order() -> None:
    statements = drop_tenant_rls_statements("contact")
    assert statements[0].startswith("DROP POLICY IF EXISTS tenant_isolation")
    assert statements[-1].endswith("DISABLE ROW LEVEL SECURITY")
