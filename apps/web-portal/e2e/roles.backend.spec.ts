import { expect, test } from "@playwright/test";

import { adminToken, api, invitePortalUser } from "./auth";

// Portal start page per role, against a real API (E2E_BACKEND=1, see scripts/e2e-backend.sh
// and apps/web-crm/e2e for the CRM counterpart). Run against a freshly seeded admin (no TOTP
// set up yet): this spec logs the admin in with password only ("ok" status, M2 rule that TOTP
// is mandatory only for administrators), which fails once the CRM @backend suite has put that
// admin through TOTP setup in the same seed.
test.describe("portal start page per role @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("tenant/owner sees documents and tickets tiles @backend", async ({ page }) => {
    test.setTimeout(60_000);
    const call = api(await adminToken());
    const run = Date.now().toString(36);
    const contact = await call<{ id: string }>(
      "POST",
      "/contacts",
      { kind: "person", first_name: "Erika", last_name: `Portal${run}` },
      201,
    );
    let property: { id: string } | undefined;
    for (let i = 0; i < 30 && !property; i++) {
      const number = String(Math.floor(Math.random() * 900) + 100);
      try {
        property = await call<{ id: string }>(
          "POST",
          "/properties",
          { number, name: `E2E Portalrolle Mieter ${run}`, management_type: "rental" },
          201,
        );
      } catch (e) {
        if (!String(e).includes(": 409 ")) throw e;
      }
    }
    const ownerContact = await call<{ id: string }>(
      "POST",
      "/contacts",
      { kind: "company", company_name: `Vermieter Portal ${run} GmbH` },
      201,
    );
    const ownerParty = (await call<{ id: string }>("POST", "/parties", { members: [{ contact_id: ownerContact.id }] }, 201)).id;
    await call("POST", `/properties/${property!.id}/owners`, { party_id: ownerParty, valid_from: "2020-01-01" }, 201);
    const building = (await call<{ id: string }>("POST", `/properties/${property!.id}/buildings`, { name: "Haus" }, 201)).id;
    const unit = (await call<{ id: string }>("POST", `/properties/${property!.id}/units`, { building_id: building, number: "01", unit_type: "apartment" }, 201)).id;
    const party = (await call<{ id: string }>("POST", "/parties", { members: [{ contact_id: contact.id }] }, 201)).id;
    await call("POST", "/contracts", { kind: "tenancy", unit_id: unit, party_id: party, start_date: "2023-01-01" }, 201);
    const { email, password } = await invitePortalUser(call, contact.id, `mieter-${run}`);

    await page.goto("/anmelden");
    await page.getByLabel("E-Mail").fill(email);
    await page.getByLabel("Passwort").fill(password);
    await page.getByRole("button", { name: "Weiter" }).click();
    await expect(page).toHaveURL(/\/start$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Übersicht");
    await expect(page.getByRole("link", { name: "Dokumente einsehen und herunterladen" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Schäden und Anliegen melden" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Aufträge bearbeiten" })).toHaveCount(0);
  });

  test("provider sees only the orders tile @backend", async ({ page }) => {
    test.setTimeout(60_000);
    const call = api(await adminToken());
    const run = Date.now().toString(36);
    const contact = await call<{ id: string }>(
      "POST",
      "/contacts",
      { kind: "company", company_name: `Glaser Portal ${run}` },
      201,
    );
    let property: { id: string } | undefined;
    for (let i = 0; i < 30 && !property; i++) {
      const number = String(Math.floor(Math.random() * 900) + 100);
      try {
        property = await call<{ id: string }>(
          "POST",
          "/properties",
          { number, name: `E2E Portalrolle ${run}`, management_type: "rental" },
          201,
        );
      } catch (e) {
        if (!String(e).includes(": 409 ")) throw e;
      }
    }
    const ticket = await call<{ id: string }>(
      "POST",
      "/tickets",
      { title: `Fenster ${run}`, property_id: property!.id },
      201,
    );
    await call(
      "POST",
      "/work-orders",
      { ticket_id: ticket.id, property_id: property!.id, provider_contact_id: contact.id, description: "Fenster richten" },
      201,
    );
    const { email, password } = await invitePortalUser(call, contact.id, `dienstleister-${run}`);

    await page.goto("/anmelden");
    await page.getByLabel("E-Mail").fill(email);
    await page.getByLabel("Passwort").fill(password);
    await page.getByRole("button", { name: "Weiter" }).click();
    await expect(page).toHaveURL(/\/start$/);
    await expect(page.getByRole("link", { name: "Aufträge bearbeiten" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Dokumente einsehen und herunterladen" })).toHaveCount(0);
  });

  // M31 WP5: a helper invited from the protocol (POST /handover/protocols/{id}/helper-access,
  // code shown once instead of a mail draft) sees the menu entry Übergabe and the protocol.
  test("handover helper sees the Übergabe menu entry @backend", async ({ page }) => {
    test.setTimeout(90_000);
    const call = api(await adminToken());
    const run = Date.now().toString(36);
    const p = await call<{ id: string }>("POST", "/handover/protocols", { kind: "rental" }, 201);
    await call("PATCH", `/handover/protocols/${p.id}`, { street: "Portalweg", house_number: "1", postal_code: "40789", city: "Monheim am Rhein" }, 200);
    const email = `gehilfe-${run}@example.org`;
    const password = "Test-Passwort-1!";
    const access = await call<{ invitation_token: string | null }>(
      "POST",
      `/handover/protocols/${p.id}/helper-access`,
      { name: `Gerd Gehilfe ${run}`, email, kind: "helper", invitation_as_mail_draft: false },
      201,
    );
    await call("POST", "/portal/invitations/accept", { token: access.invitation_token, password });

    await page.goto("/anmelden");
    await page.getByLabel("E-Mail").fill(email);
    await page.getByLabel("Passwort").fill(password);
    await page.getByRole("button", { name: "Weiter" }).click();
    await expect(page).toHaveURL(/\/start$/);
    const toggle = page.getByRole("button", { name: "Menü öffnen" });
    if (await toggle.isVisible()) await toggle.click();
    await expect(page.getByRole("link", { name: "Übergabe" })).toBeVisible();
    await page.getByRole("link", { name: "Übergabe" }).click();
    await expect(page).toHaveURL(/\/uebergabe$/);
    await page.getByRole("link", { name: /UP-/ }).first().click();
    await expect(page.getByTestId("handover-fill")).toBeVisible();
    await expect(page.locator("a[target='_blank']")).toHaveCount(0);
  });
});
