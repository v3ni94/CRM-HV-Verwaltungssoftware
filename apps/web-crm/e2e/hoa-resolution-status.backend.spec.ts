import { expect, test } from "@playwright/test";

import { api, apiToken, uiLogin } from "./auth";

// GAM-201: status dialog of the Beschluss-Sammlung (weg/[propertyId]) against a real API
// (E2E_BACKEND=1, one worker). The change cancels nothing; no gate is opened, nothing is booked.
test.describe("HOA resolution status dialog @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("contest a resolution with court note and reason @backend", async ({ page }) => {
    test.setTimeout(180_000);
    const call = api(await apiToken());
    const run = Date.now().toString(36);
    let prop: { id: string; legal_entities: { id: string; kind: string }[] } | null = null;
    for (let i = 0; i < 30 && !prop; i++) {
      const number = String(Math.floor(Math.random() * 900) + 100);
      try {
        prop = await call("POST", "/properties", { number, name: `E2E Beschluss ${run}`, management_type: "hoa" }, 201);
      } catch (e) {
        if (!String(e).includes(": 409 ")) throw e;
      }
    }
    if (!prop) throw new Error("no free property number");
    const hoa = prop.legal_entities.find((e) => e.kind === "hoa")!.id;
    const template = await call<{ id: string }>("POST", "/accounting/templates/default", undefined, 201);
    await call("POST", "/accounting/ledgers", { legal_entity_id: hoa, template_id: template.id }, 201);
    await call("POST", "/hoa/resolutions", { legal_entity_id: hoa, decided_on: "2026-05-10", subject: "E2E Dachsanierung", wording: "Die Dachsanierung wird beschlossen.", status: "positive", kind: "external" }, 201);

    await uiLogin(page, `/weg/${prop.id}`);
    await expect(page.getByRole("cell", { name: /E2E Dachsanierung/ })).toBeVisible();
    await page.getByRole("button", { name: "Status ändern" }).first().click();
    await expect(page.getByText(/storniert nichts automatisch/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Status speichern" })).toBeDisabled();
    await page.getByLabel("Gericht").fill("AG Musterstadt");
    await page.getByLabel("Begründung (Pflicht)").fill("Anfechtungsklage eingegangen");
    await page.getByRole("button", { name: "Status speichern" }).click();
    await expect(page.getByText(/AG Musterstadt/)).toBeVisible();
  });
});
