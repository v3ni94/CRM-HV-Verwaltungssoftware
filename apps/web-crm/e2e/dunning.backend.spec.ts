import { expect, test } from "@playwright/test";

import { api, apiToken, uiLogin } from "./auth";

// Dunning run preview and approval against a real API (E2E_BACKEND=1). Release gate G1 stays
// closed: the ledger cannot become the leading system, so every case is excluded and there is
// no approval; the API refuses the gate change and the approval (A71, UI money paths).
test.describe("dunning preview and approval lock against the API @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("preview lists the excluded case, approval is locked by G1 @backend", async ({ page }) => {
    test.setTimeout(180_000);
    const token = await apiToken();
    const call = api(token);
    const run = Date.now().toString(36);
    const property = async <T,>(name: string, management_type: string): Promise<T> => {
      for (let i = 0; i < 30; i++) {
        const number = String(Math.floor(Math.random() * 900) + 100);
        try {
          return await call<T>("POST", "/properties", { number, name, management_type }, 201);
        } catch (e) {
          if (!String(e).includes(": 409 ")) throw e;
        }
      }
      throw new Error("no free property number");
    };
    const party = async (name: string) => {
      const c = await call<{ id: string }>("POST", "/contacts", { kind: "company", company_name: `${name} ${run} GmbH` }, 201);
      return (await call<{ id: string }>("POST", "/parties", { members: [{ contact_id: c.id }] }, 201)).id;
    };

    // Rental property, one tenancy with rent 450,00 due on the 3rd, posted receivable for 01/2026.
    const prop = await property<{ id: string }>(`E2E Mahnung ${run}`, "rental");
    const entity = (await call<{ legal_entity_id: string }>("POST", `/properties/${prop.id}/owners`, { party_id: await party("Vermieter"), valid_from: "2020-01-01" }, 201)).legal_entity_id;
    const building = (await call<{ id: string }>("POST", `/properties/${prop.id}/buildings`, { name: "Haus" }, 201)).id;
    const unit = (await call<{ id: string }>("POST", `/properties/${prop.id}/units`, { building_id: building, number: "01", unit_type: "apartment", living_area_sqm: "50" }, 201)).id;
    const contract = await call<{ id: string }>("POST", "/contracts", { kind: "tenancy", unit_id: unit, party_id: await party("Mieter"), start_date: "2024-01-01" }, 201);
    await call("POST", `/contracts/${contract.id}/payments`, { payment_type_code: "rent", net: "450.00", gross: "450.00", valid_from: "2024-01-01" }, 201);
    await call("POST", `/contracts/${contract.id}/schedules`, { valid_from: "2024-01-01", due_day: 3 }, 201);
    const template = await call<{ id: string }>("POST", "/accounting/templates/default", undefined, 201);
    const ledger = (await call<{ id: string }>("POST", "/accounting/ledgers", { legal_entity_id: entity, template_id: template.id }, 201)).id;
    const revenue = (await call<{ id: string }>("POST", `/accounting/ledgers/${ledger}/accounts`, { number: "061000", name: "Mieteinnahmen", category: "revenue", type: "income" }, 201)).id;
    await call("PUT", `/accounting/ledgers/${ledger}/payment-type-accounts`, { payment_type_code: "rent", account_id: revenue });
    await call("PUT", "/accounting/dunning-settings", {
      property_id: prop.id,
      levels: [{ level: 1, min_days_overdue: 14, text: "Zahlungserinnerung" }],
    });
    const receivable = await call<{ id: string }>("POST", "/accounting/receivable-runs", { period_month: "2026-01-01", scope: "property", scope_id: prop.id }, 201);
    await call("POST", `/accounting/receivable-runs/${receivable.id}/post`);

    // G1 lock: the ledger cannot be declared leading (MHVP-GATE-0001, 403).
    const gate = await fetch(`${process.env.MHVP_API_INTERNAL_URL ?? "http://127.0.0.1:8000"}/api/v1/accounting/ledgers/${ledger}/leading`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
      body: JSON.stringify({ leading_system: "mhvp" }),
    });
    expect(gate.status).toBe(403);
    expect(await gate.text()).toContain("MHVP-GATE-0001");

    // 1. Preview through the screen: the notice explains the lock and the run opens.
    await uiLogin(page, "/buchhaltung/mahnwesen");
    await expect(page.getByRole("heading", { name: "Mahnwesen", level: 1 })).toBeVisible();
    await expect(page.getByText(/Freigeben muss eine zweite Person/)).toBeVisible();
    await page.getByLabel("Stichtag").fill("2026-03-01");
    await page.getByRole("button", { name: "Vorschau erstellen" }).click();
    await expect(page).toHaveURL(/\/buchhaltung\/mahnwesen\/[0-9a-f-]{36}$/);
    const runId = page.url().split("/").pop()!;
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Mahnlauf zum 01.03.2026");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Vorschau");

    // 2. The case of the open item 450,00 is listed but excluded (ledger not leading).
    const row = page.locator("table.mhvp-table tbody tr", { hasText: /450,00/ });
    await expect(row.first()).toBeVisible();
    await expect(row.first()).toContainText("ausgeschlossen");
    await expect(page.getByText(/nicht führend/).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Mahnlauf freigeben" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Als versendet markieren" })).toHaveCount(0);

    // 3. Approval stays refused on the API as well: nothing is posted while G1 is closed.
    const approve = await fetch(`${process.env.MHVP_API_INTERNAL_URL ?? "http://127.0.0.1:8000"}/api/v1/accounting/dunning-runs/${runId}/approve`, {
      method: "POST",
      headers: { authorization: `Bearer ${token}` },
    });
    expect([403, 409, 422]).toContain(approve.status);
    const detail = await call<{ status: string }>("GET", `/accounting/dunning-runs/${runId}`);
    expect(detail.status).toBe("preview");

    // 4. The run appears in the list of recent runs as a preview.
    await page.goto("/buchhaltung/mahnwesen");
    await expect(page.getByRole("link", { name: "01.03.2026" }).first()).toBeVisible();
  });
});
