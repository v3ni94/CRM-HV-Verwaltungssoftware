import { expect, test } from "@playwright/test";

import { api, apiToken, uiLogin } from "./auth";

// Inline editing of master data (AP8, ADR 0012) on the property, building and unit pages.
// Runs only with E2E_BACKEND=1 against a real API (see scripts/e2e-backend.sh).
test.describe("Inline editing against the API @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("property, building and unit fields save in place with version check @backend", async ({ page }) => {
    test.setTimeout(180_000);
    const call = api(await apiToken());
    const run = Date.now().toString(36);
    // Property numbers are NNN and unique per tenant; repeated runs pick a free one.
    let prop: { id: string; number: string } | null = null;
    for (let i = 0; i < 30 && !prop; i++) {
      const number = String(Math.floor(Math.random() * 900) + 100);
      try {
        prop = await call<{ id: string; number: string }>("POST", "/properties", { number, name: `E2E Inline ${run}`, management_type: "rental" }, 201);
      } catch (e) {
        if (!String(e).includes(": 409 ")) throw e;
      }
    }
    if (!prop) throw new Error("no free property number");
    const building = await call<{ id: string; version: number }>("POST", `/properties/${prop.id}/buildings`, { name: "Haus A" }, 201);
    const unit = await call<{ id: string }>("POST", `/properties/${prop.id}/units`, { building_id: building.id, number: "01", unit_type: "apartment" }, 201);

    await uiLogin(page, `/objekte/${prop.id}`);
    // Known drift: after a password only login the middleware sends the session to /mandant
    // without the "next" parameter, so the deep link ends on /kontakte. Navigate explicitly
    // until the redirect keeps the target (src/middleware.ts, LoginForm.tsx).
    await page.waitForURL(/\/(kontakte|objekte)/);
    if (!page.url().includes(`/objekte/${prop.id}`)) await page.goto(`/objekte/${prop.id}`);
    await expect(page).toHaveURL(new RegExp(`/objekte/${prop.id}$`));

    // Property: the links bar and the master data section are visible; a field saves on blur.
    await expect(page.getByTestId("entity-links")).toBeVisible();
    const propertySection = page.getByTestId("property-master-data");
    await propertySection.getByRole("button", { name: "Bearbeiten", exact: true }).click();
    await propertySection.getByLabel("Ort").fill("Monheim am Rhein");
    await propertySection.getByLabel("Ort").press("Tab");
    await expect(propertySection.getByText("Gespeichert").first()).toBeVisible();
    const saved = await call<{ city: string; version: number }>("GET", `/properties/${prop.id}`);
    expect(saved.city).toBe("Monheim am Rhein");

    // Inline validation: a negative area is not sent.
    await propertySection.getByLabel("Bebaute Fläche in m²").fill("-1");
    await propertySection.getByLabel("Bebaute Fläche in m²").press("Enter");
    await expect(propertySection.getByRole("alert")).toHaveText("Fläche darf nicht negativ sein.");
    await propertySection.getByRole("button", { name: "Fertig" }).click();

    // Buildings list links to the building page; the energy certificate saves there.
    await page.getByRole("link", { name: "Gebäude öffnen: Haus A" }).click();
    await expect(page).toHaveURL(new RegExp(`/objekte/${prop.id}/gebaeude/${building.id}$`));
    const buildingSection = page.getByTestId("building-master-data");
    await buildingSection.getByRole("button", { name: "Bearbeiten", exact: true }).click();
    await buildingSection.getByLabel("Adresszusatz").fill("Hinterhaus");
    await buildingSection.getByLabel("Adresszusatz").press("Enter");
    await expect(buildingSection.getByText("Gespeichert").first()).toBeVisible();
    await page.getByTestId("energy-certificate").getByLabel("Art des Ausweises").selectOption("bedarf");
    await page.getByTestId("energy-certificate").getByLabel("Effizienzklasse").fill("c");
    await page.getByRole("button", { name: "Energieausweis speichern" }).click();
    await expect(page.getByText("Gespeichert.")).toBeVisible();
    const b = await call<{ address_addition: string; energy_certificate_class: string }>("GET", `/buildings/${building.id}`);
    expect(b.address_addition).toBe("Hinterhaus");
    expect(b.energy_certificate_class).toBe("C");

    // Conflict: a change from elsewhere bumps the version; the next inline save shows the hint.
    await call("PATCH", `/buildings/${building.id}`, { floors: 3 });
    await buildingSection.getByLabel("Geschosse").fill("5");
    await buildingSection.getByLabel("Geschosse").press("Enter");
    await expect(buildingSection.getByText("Von jemand anderem geändert, neu laden").first()).toBeVisible();
    await expect(buildingSection.getByRole("button", { name: "Neu laden" })).toBeVisible();

    // Unit: commission and deposit are master data, saved per field; the audit log lists it.
    await page.goto(`/vermietung/einheit/${unit.id}`);
    const unitSection = page.getByTestId("unit-master-data");
    await unitSection.getByRole("button", { name: "Bearbeiten", exact: true }).click();
    await unitSection.getByLabel("Kaution in EUR").fill("1500");
    await unitSection.getByLabel("Kaution in EUR").press("Tab");
    await expect(unitSection.getByText("Gespeichert").first()).toBeVisible();
    const u = await call<{ deposit_amount: string }>("GET", `/units/${unit.id}`);
    expect(u.deposit_amount).toBe("1500.00");
    await expect(page.getByRole("heading", { name: "Ereignisprotokoll" })).toBeVisible();
  });
});
