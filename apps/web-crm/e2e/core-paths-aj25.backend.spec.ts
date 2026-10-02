import { expect, test } from "@playwright/test";

import { api, apiToken, email, uiLogin } from "./auth";

// GAI-621 (AJ25): own CRM core paths against a real API (E2E_BACKEND=1, scripts/e2e-backend.sh):
// the login as a separate case (wrong password, redirect of a protected page) and saving a
// contract through the form (unit, contract partner via contact search, start date). Booking
// and bank transaction are covered by bank-buchen.spec.ts and money.backend.spec.ts.
test.describe("CRM core paths AJ25 @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("Anmeldung: geschützte Seite leitet um, falsches Passwort wird abgewiesen @backend", async ({ page }) => {
    test.setTimeout(180_000);
    await page.goto("/kontakte");
    await expect(page).toHaveURL(/\/anmelden/, { timeout: 60_000 });
    await page.getByLabel("E-Mail").fill(email);
    await page.getByLabel("Passwort").fill("falsches-Passwort-AJ25");
    await page.getByRole("button", { name: "Weiter" }).click();
    await expect(page.locator('p[role="alert"]').first()).toBeVisible({ timeout: 60_000 });
    await expect(page).toHaveURL(/\/anmelden/);
    // The correct password leads through the second factor and the tenant choice.
    await uiLogin(page, "/start");
    await expect(page).toHaveURL(/\/start$/, { timeout: 60_000 });
    await expect(page.locator("p.mhvp-title")).toBeVisible();
  });

  test("Vertrag über das Formular anlegen und speichern @backend", async ({ page }) => {
    test.setTimeout(300_000);
    const call = api(await apiToken());
    const run = Date.now().toString(36);
    let property: { id: string } | null = null;
    for (let i = 0; i < 30 && !property; i++) {
      try {
        property = await call<{ id: string }>(
          "POST",
          "/properties",
          { number: String(Math.floor(Math.random() * 900) + 100), name: `E2E AJ25 Vertrag ${run}`, management_type: "rental" },
          201,
        );
      } catch (e) {
        if (!String(e).includes(": 409 ")) throw e;
      }
    }
    expect(property, "no free property number").not.toBeNull();
    const ownerContact = await call<{ id: string }>("POST", "/contacts", { kind: "company", company_name: `Vermieter AJ25 ${run} GmbH` }, 201);
    const ownerParty = (await call<{ id: string }>("POST", "/parties", { members: [{ contact_id: ownerContact.id }] }, 201)).id;
    await call("POST", `/properties/${property!.id}/owners`, { party_id: ownerParty, valid_from: "2020-01-01" }, 201);
    const building = (await call<{ id: string }>("POST", `/properties/${property!.id}/buildings`, { name: "Haus" }, 201)).id;
    const unit = (await call<{ id: string }>("POST", `/properties/${property!.id}/units`, { building_id: building, number: "01", unit_type: "apartment" }, 201)).id;
    const lastName = `Mieteraj${run}`;
    await call("POST", "/contacts", { kind: "person", first_name: "Erika", last_name: lastName }, 201);

    await uiLogin(page, `/vertraege/neu?objekt=${property!.id}`);
    await expect(page).toHaveURL(/\/vertraege\/neu/, { timeout: 60_000 });
    const form = page.getByTestId("contract-form");
    await expect(form.getByRole("combobox", { name: "Objekt", exact: true })).toHaveValue(property!.id, { timeout: 60_000 });
    await form.getByRole("combobox", { name: "Einheit", exact: true }).selectOption(unit);
    // The role filter follows the contract kind (tenants); the new contact has no role yet.
    await form.getByRole("combobox", { name: "Rolle" }).first().selectOption("");
    await form.getByLabel("Kontakt suchen").first().fill(lastName);
    await form.getByRole("button", { name: "Suchen" }).first().click();
    await form.getByRole("list", { name: "Suchergebnisse" }).getByRole("button", { name: new RegExp(lastName) }).click({ timeout: 60_000 });
    await expect(form.getByTestId("picked-party")).toContainText(lastName);
    await form.getByLabel("Beginn", { exact: true }).fill("2026-01-01");
    await form.getByRole("button", { name: "Vertrag anlegen" }).click();

    await expect(page).toHaveURL(/\/vertraege\/[0-9a-f-]{36}/, { timeout: 90_000 });
    const id = /\/vertraege\/([0-9a-f-]{36})/.exec(page.url())![1];
    const contract = await call<{ unit_id: string; kind: string; start_date: string }>("GET", `/contracts/${id}`);
    expect(contract.unit_id).toBe(unit);
    expect(contract.kind).toBe("tenancy");
    expect(contract.start_date).toBe("2026-01-01");
  });
});
