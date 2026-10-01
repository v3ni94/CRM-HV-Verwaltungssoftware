import { expect, test } from "@playwright/test";

import { api, apiToken, uiLogin } from "./auth";

// Detail page of an economic plan (weg/[propertyId]/plan/[planId]) against a real API
// (E2E_BACKEND=1, one worker). Master data from the API, the steps through the screen. Nothing
// is approved or booked: the plan stays a draft, release gates stay closed.
test.describe("HOA plan detail page @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("draft plan: title, items, calculation per unit, back link @backend", async ({ page }) => {
    test.setTimeout(180_000);
    const call = api(await apiToken());
    const run = Date.now().toString(36);
    let prop: { id: string; legal_entities: { id: string; kind: string }[] } | null = null;
    for (let i = 0; i < 30 && !prop; i++) {
      const number = String(Math.floor(Math.random() * 900) + 100);
      try {
        prop = await call("POST", "/properties", { number, name: `E2E Plan ${run}`, management_type: "hoa" }, 201);
      } catch (e) {
        if (!String(e).includes(": 409 ")) throw e;
      }
    }
    if (!prop) throw new Error("no free property number");
    const hoa = prop.legal_entities.find((e) => e.kind === "hoa")!.id;
    const keys = await call<{ id: string; code: string }[]>("GET", `/properties/${prop.id}/allocation-keys`);
    const mea = keys.find((k) => k.code === "MEA")!.id;
    const building = (await call<{ id: string }>("POST", `/properties/${prop.id}/buildings`, { name: "Haus" }, 201)).id;
    const unit = (await call<{ id: string }>("POST", `/properties/${prop.id}/units`, { building_id: building, number: "01", unit_type: "apartment" }, 201)).id;
    await call("POST", `/units/${unit}/allocation-values`, { allocation_key_id: mea, value: "1000", valid_from: "2020-01-01" }, 201);
    const template = await call<{ id: string }>("POST", "/accounting/templates/default", undefined, 201);
    await call("POST", "/accounting/ledgers", { legal_entity_id: hoa, template_id: template.id }, 201);

    await uiLogin(page, `/weg/${prop.id}`);
    await page.getByLabel("Jahr").first().fill("2028");
    await page.getByRole("button", { name: "Plan anlegen" }).click();
    await expect(page).toHaveURL(/\/plan\/[0-9a-f-]{36}$/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("2028");
    await expect(page.getByText(/Etwas ist schiefgelaufen|Application error/i)).toHaveCount(0);

    await page.getByLabel("Bezeichnung").fill("Versicherung");
    await page.getByLabel("Betrag").fill("2400");
    await page.getByLabel("Schlüssel").selectOption(mea);
    await page.getByRole("button", { name: "Position hinzufügen" }).click();
    await expect(page.getByRole("cell", { name: "Versicherung" })).toBeVisible();

    await page.getByRole("button", { name: "Berechnen", exact: true }).click();
    // 2.400,00 by MEA on the only unit: 200,00 per month.
    await expect(page.getByRole("cell", { name: /200,00/ }).first()).toBeVisible();
    await expect(page.getByRole("cell", { name: "01", exact: true })).toBeVisible();

    await page.getByRole("link", { name: "Wirtschaftspläne" }).first().click();
    await expect(page).toHaveURL(new RegExp(`/weg/${prop.id}$`));
  });
});
