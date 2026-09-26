import { expect, test } from "@playwright/test";

import { adminToken, api, invitePortalUser } from "./auth";

// Tenant damage report through the portal against a real API (E2E_BACKEND=1, see
// scripts/e2e-backend.sh): a tenant with a tenancy logs in, submits a report without a photo,
// sees it in the list and opens it. The report arrives as a ticket in the CRM (A71, M21).
test.describe("portal damage report @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("tenant submits a report without photo and sees it in the list @backend", async ({ page }) => {
    test.setTimeout(90_000);
    const call = api(await adminToken());
    const run = Date.now().toString(36);
    const contact = await call<{ id: string }>(
      "POST",
      "/contacts",
      { kind: "person", first_name: "Max", last_name: `Meldung${run}` },
      201,
    );
    let property: { id: string } | undefined;
    for (let i = 0; i < 30 && !property; i++) {
      const number = String(Math.floor(Math.random() * 900) + 100);
      try {
        property = await call<{ id: string }>(
          "POST",
          "/properties",
          { number, name: `E2E Schadensmeldung ${run}`, management_type: "rental" },
          201,
        );
      } catch (e) {
        if (!String(e).includes(": 409 ")) throw e;
      }
    }
    const ownerContact = await call<{ id: string }>(
      "POST",
      "/contacts",
      { kind: "company", company_name: `Vermieter Meldung ${run} GmbH` },
      201,
    );
    const ownerParty = (await call<{ id: string }>("POST", "/parties", { members: [{ contact_id: ownerContact.id }] }, 201)).id;
    await call("POST", `/properties/${property!.id}/owners`, { party_id: ownerParty, valid_from: "2020-01-01" }, 201);
    const building = (await call<{ id: string }>("POST", `/properties/${property!.id}/buildings`, { name: "Haus" }, 201)).id;
    const unit = (await call<{ id: string }>("POST", `/properties/${property!.id}/units`, { building_id: building, number: "02", unit_type: "apartment" }, 201)).id;
    const party = (await call<{ id: string }>("POST", "/parties", { members: [{ contact_id: contact.id }] }, 201)).id;
    await call("POST", "/contracts", { kind: "tenancy", unit_id: unit, party_id: party, start_date: "2023-01-01" }, 201);
    const { email, password } = await invitePortalUser(call, contact.id, `mieter-meldung-${run}`);

    await page.goto("/anmelden");
    await page.getByLabel("E-Mail").fill(email);
    await page.getByLabel("Passwort").fill(password);
    await page.getByRole("button", { name: "Weiter" }).click();
    await expect(page).toHaveURL(/\/start$/);
    await page.getByRole("link", { name: "Schäden und Anliegen melden" }).click();
    await expect(page).toHaveURL(/\/meldungen$/);
    await expect(page.getByRole("heading", { name: "Meldungen", level: 1 })).toBeVisible();
    await expect(page.getByText("Keine Meldungen vorhanden.")).toBeVisible();

    // Client side validation first: a title alone is not enough.
    const title = `Wasserfleck Decke Bad ${run}`;
    await page.getByLabel("Titel").fill(title);
    await page.getByRole("button", { name: "Melden" }).click();
    await expect(page.getByRole("alert")).toContainText("Bitte eine Beschreibung eingeben.");

    // Submit without a photo (the upload is optional).
    await page.getByLabel("Beschreibung").fill("Seit gestern ein feuchter Fleck an der Badezimmerdecke, etwa 30 cm groß.");
    await page.getByRole("button", { name: "Melden" }).click();
    await expect(page.getByText("Meldung wurde übermittelt.")).toBeVisible();
    await expect(page.getByLabel("Titel")).toHaveValue("");

    // The report is listed with its number and status and opens on its own page.
    const link = page.getByRole("link", { name: new RegExp(title) });
    await expect(link).toBeVisible();
    await expect(link).toContainText("Neu");
    await link.click();
    await expect(page).toHaveURL(/\/meldungen\/[0-9a-f-]{36}$/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(title);

    // The CRM sees the report as a ticket of the tenant.
    const tickets = await call<{ title: string; source: string }[]>("GET", `/tickets?q=${encodeURIComponent(run)}`);
    const ticket = tickets.find((t) => t.title === title);
    expect(ticket).toBeDefined();
  });
});
