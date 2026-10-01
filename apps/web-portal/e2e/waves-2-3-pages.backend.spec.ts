import { expect, test, type Page } from "@playwright/test";

import { adminToken, api, invitePortalUser } from "./auth";

// Portal core paths of waves 2 and 3 against a real API (E2E_BACKEND=1, one worker): document
// search, owner statements, role switch. Pattern: pages.backend.spec.ts.
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

async function login(page: Page, email: string, password: string) {
  await page.goto("/anmelden");
  await page.getByLabel("E-Mail").fill(email);
  await page.getByLabel("Passwort").fill(password);
  await page.getByRole("button", { name: "Weiter" }).click();
  await expect(page).toHaveURL(/\/start$/);
}

test.describe("portal pages of waves 2 and 3 @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("owner: document search, statements and role switch @backend", async ({ page }) => {
    test.setTimeout(150_000);
    const call = api(await adminToken());
    const run = Date.now().toString(36);
    const weg = await freshProperty(call, `E2E WEG Welle23 ${run}`, "hoa");
    const wegUnit = await unitOf(call, weg.id, "01");
    const rental = await freshProperty(call, `E2E Miete Welle23 ${run}`, "rental");
    const landlord = await call<{ id: string }>("POST", "/contacts", { kind: "company", company_name: `Vermieter Welle23 ${run} GmbH` }, 201);
    await call("POST", `/properties/${rental.id}/owners`, { party_id: await partyOf(call, landlord.id), valid_from: "2020-01-01" }, 201);
    const rentalUnit = await unitOf(call, rental.id, "02");
    const contact = await call<{ id: string }>("POST", "/contacts", { kind: "person", first_name: "Paula", last_name: `Doppel${run}` }, 201);
    const party = await partyOf(call, contact.id);
    await call(
      "POST",
      "/contracts",
      { kind: "ownership", unit_id: wegUnit, party_id: party, start_date: "2020-01-01", title_transfer_date: "2020-01-01", acquisition_kind: "first_acquisition" },
      201,
    );
    await call("POST", "/contracts", { kind: "tenancy", unit_id: rentalUnit, party_id: party, start_date: "2023-01-01" }, 201);
    const { email, password } = await invitePortalUser(call, contact.id, `doppel-${run}`);
    await login(page, email, password);

    // Document search (M25-06): the form is a GET search, an unknown term shows the empty state.
    await page.goto("/dokumente");
    await expect(page.getByRole("heading", { name: "Dokumente", level: 1 })).toBeVisible();
    await page.getByRole("searchbox").fill(`nichtvorhanden-${run}`);
    await page.getByRole("button", { name: "Anwenden" }).click();
    await expect(page).toHaveURL(/q=nichtvorhanden/);
    await expect(page.getByText("Keine freigegebenen Dokumente.")).toBeVisible();

    // Owner statements (M24-03): none released yet, so the empty state shows, no owners-only notice.
    await page.goto("/abrechnungen");
    await expect(page.getByRole("heading", { name: "Hausgeldabrechnung", level: 1 })).toBeVisible();
    await expect(page.getByText("Diese Seite steht nur Eigentümern zur Verfügung.")).toHaveCount(0);

    // Role switch (M21-05): owner and tenant role, narrowing to tenant hides the owner pages.
    const switcher = page.getByLabel("Ansicht");
    await expect(switcher).toBeVisible();
    // The select can be used before hydration finishes (the change is then lost), so retry the
    // selection until the value sticks. router.refresh() re-renders the layout asynchronously.
    await expect(async () => {
      await switcher.selectOption("tenant_resident");
      await expect(switcher).toHaveValue("tenant_resident", { timeout: 3_000 });
    }).toPass({ timeout: 20_000 });
    await expect(page.getByRole("navigation").getByRole("link", { name: "Hausgeldkonto", exact: true })).toHaveCount(0, { timeout: 15_000 });
    await switcher.selectOption("");
    await expect(page.getByRole("navigation").getByRole("link", { name: "Hausgeldkonto", exact: true })).toBeVisible({ timeout: 15_000 });
  });

  test("tenant: statements page says owners only, no role switch @backend", async ({ page }) => {
    test.setTimeout(120_000);
    const call = api(await adminToken());
    const run = Date.now().toString(36);
    const property = await freshProperty(call, `E2E Miete Welle23b ${run}`, "rental");
    const landlord = await call<{ id: string }>("POST", "/contacts", { kind: "company", company_name: `Vermieter Welle23b ${run} GmbH` }, 201);
    await call("POST", `/properties/${property.id}/owners`, { party_id: await partyOf(call, landlord.id), valid_from: "2020-01-01" }, 201);
    const unit = await unitOf(call, property.id, "03");
    const contact = await call<{ id: string }>("POST", "/contacts", { kind: "person", first_name: "Lena", last_name: `Mieter23${run}` }, 201);
    await call("POST", "/contracts", { kind: "tenancy", unit_id: unit, party_id: await partyOf(call, contact.id), start_date: "2023-01-01" }, 201);
    const { email, password } = await invitePortalUser(call, contact.id, `mieter23-${run}`);
    await login(page, email, password);
    await page.goto("/abrechnungen");
    await expect(page.getByText("Diese Seite steht nur Eigentümern zur Verfügung.")).toBeVisible();
    await expect(page.getByLabel("Ansicht")).toHaveCount(0);
  });
});
