import { expect, test } from "@playwright/test";

import { adminToken, api, invitePortalUser } from "./auth";

// Smoke tests of the newer portal pages against a real API (E2E_BACKEND=1, A71): the owner
// pages of A51 (/beschluesse, /ansprechpartner, /hausgeldkonto), the notice board (A54) and
// the forms (A56) load for an owner; a tenant is told the owner pages are owners only; the
// board audit room (A52) shows nothing to an account without a board engagement and is not
// offered in the navigation.

type Call = ReturnType<typeof api>;

async function freshProperty(call: Call, name: string, management_type: "hoa" | "rental") {
  for (let i = 0; i < 30; i++) {
    const number = String(Math.floor(Math.random() * 900) + 100);
    try {
      return await call<{ id: string }>("POST", "/properties", { number, name, management_type }, 201);
    } catch (e) {
      if (!String(e).includes(": 409 ")) throw e;
    }
  }
  throw new Error("no free property number");
}

async function unitOf(call: Call, propertyId: string, number: string) {
  const building = (await call<{ id: string }>("POST", `/properties/${propertyId}/buildings`, { name: "Haus" }, 201)).id;
  return (await call<{ id: string }>("POST", `/properties/${propertyId}/units`, { building_id: building, number, unit_type: "apartment" }, 201)).id;
}

async function partyOf(call: Call, contactId: string) {
  return (await call<{ id: string }>("POST", "/parties", { members: [{ contact_id: contactId }] }, 201)).id;
}

async function login(page: import("@playwright/test").Page, email: string, password: string) {
  await page.goto("/anmelden");
  await page.getByLabel("E-Mail").fill(email);
  await page.getByLabel("Passwort").fill(password);
  await page.getByRole("button", { name: "Weiter" }).click();
  await expect(page).toHaveURL(/\/start$/);
}

test.describe("portal pages per role @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("owner sees resolutions, contacts, HOA account, notices, forms; no audit room @backend", async ({ page }) => {
    test.setTimeout(120_000);
    const call = api(await adminToken());
    const run = Date.now().toString(36);
    const weg = await freshProperty(call, `E2E WEG Portalseiten ${run}`, "hoa");
    const unit = await unitOf(call, weg.id, "01");
    const contact = await call<{ id: string }>("POST", "/contacts", { kind: "person", first_name: "Otto", last_name: `Eigentuemer${run}` }, 201);
    await call(
      "POST",
      "/contracts",
      {
        kind: "ownership",
        unit_id: unit,
        party_id: await partyOf(call, contact.id),
        start_date: "2020-01-01",
        title_transfer_date: "2020-01-01",
        acquisition_kind: "first_acquisition",
      },
      201,
    );
    const { email, password } = await invitePortalUser(call, contact.id, `eigentuemer-${run}`);
    await login(page, email, password);

    const nav = page.getByRole("navigation");
    for (const label of ["Beschlüsse", "Ansprechpartner", "Hausgeldkonto", "Aushänge", "Formulare"]) {
      await expect(nav.getByRole("link", { name: label, exact: true })).toBeVisible();
    }
    await expect(nav.getByRole("link", { name: "Prüfungsraum" })).toHaveCount(0);

    await page.goto("/beschluesse");
    await expect(page.getByRole("heading", { name: "Beschlüsse", level: 1 })).toBeVisible();
    await expect(page.getByText("Keine verkündeten Beschlüsse vorhanden.")).toBeVisible();

    await page.goto("/ansprechpartner");
    await expect(page.getByRole("heading", { name: "Ansprechpartner", level: 1 })).toBeVisible();
    await expect(page.getByText("Diese Seite steht nur Eigentümern zur Verfügung.")).toHaveCount(0);

    await page.goto("/hausgeldkonto");
    await expect(page.getByRole("heading", { name: "Hausgeldkonto", level: 1 })).toBeVisible();
    await expect(page.getByText("Diese Seite steht nur Eigentümern zur Verfügung.")).toHaveCount(0);

    await page.goto("/aushaenge");
    await expect(page.getByRole("heading", { name: "Aushänge", level: 1 })).toBeVisible();
    await expect(page.getByText("Derzeit keine Aushänge.")).toBeVisible();

    await page.goto("/formulare");
    await expect(page.getByRole("heading", { name: "Formulare", level: 1 })).toBeVisible();

    // A52: without a board engagement the audit room lists nothing and no detail is reachable.
    await page.goto("/pruefung");
    await expect(page.getByRole("heading", { name: "Prüfungsraum des Beirats", level: 1 })).toBeVisible();
    await expect(page.getByText("Kein Prüfauftrag zugewiesen.")).toBeVisible();
    await expect(page.locator("a[href^='/pruefung/']")).toHaveCount(0);
  });

  test("tenant is told the owner pages are owners only @backend", async ({ page }) => {
    test.setTimeout(120_000);
    const call = api(await adminToken());
    const run = Date.now().toString(36);
    const property = await freshProperty(call, `E2E Miete Portalseiten ${run}`, "rental");
    const landlord = await call<{ id: string }>("POST", "/contacts", { kind: "company", company_name: `Vermieter Seiten ${run} GmbH` }, 201);
    await call("POST", `/properties/${property.id}/owners`, { party_id: await partyOf(call, landlord.id), valid_from: "2020-01-01" }, 201);
    const unit = await unitOf(call, property.id, "03");
    const contact = await call<{ id: string }>("POST", "/contacts", { kind: "person", first_name: "Lena", last_name: `Mieterin${run}` }, 201);
    await call("POST", "/contracts", { kind: "tenancy", unit_id: unit, party_id: await partyOf(call, contact.id), start_date: "2023-01-01" }, 201);
    const { email, password } = await invitePortalUser(call, contact.id, `mieterin-${run}`);
    await login(page, email, password);

    const nav = page.getByRole("navigation");
    await expect(nav.getByRole("link", { name: "Aushänge", exact: true })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Formulare", exact: true })).toBeVisible();
    for (const label of ["Beschlüsse", "Ansprechpartner", "Hausgeldkonto", "Prüfungsraum"]) {
      await expect(nav.getByRole("link", { name: label, exact: true })).toHaveCount(0);
    }
    for (const path of ["/beschluesse", "/ansprechpartner", "/hausgeldkonto"]) {
      await page.goto(path);
      await expect(page.getByText("Diese Seite steht nur Eigentümern zur Verfügung.")).toBeVisible();
    }
    await page.goto("/aushaenge");
    await expect(page.getByRole("heading", { name: "Aushänge", level: 1 })).toBeVisible();
    await page.goto("/formulare");
    await expect(page.getByRole("heading", { name: "Formulare", level: 1 })).toBeVisible();
    await page.goto("/pruefung");
    await expect(page.getByText("Kein Prüfauftrag zugewiesen.")).toBeVisible();
    await expect(page.locator("a[href^='/pruefung/']")).toHaveCount(0);
  });
});
