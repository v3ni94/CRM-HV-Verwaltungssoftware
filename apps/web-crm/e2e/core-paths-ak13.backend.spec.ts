import { expect, test } from "@playwright/test";

import { api, apiToken, uiLogin } from "./auth";

// GAI-621 (AK13, rest of AJ25): create a contact and a ticket through the CRM forms against a
// real API (E2E_BACKEND=1, scripts/e2e-backend.sh) and read the stored records back from the
// API. Booking and bank transaction run in bank-buchen.spec.ts, the contract form in
// core-paths-aj25.backend.spec.ts.
test.describe("CRM core paths AK13 @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("Kontakt und Ticket über die Oberfläche anlegen @backend", async ({ page }) => {
    test.setTimeout(300_000);
    const call = api(await apiToken());
    const run = `Ak${Date.now().toString(36)}`;

    // 1. Contact through the form "Neuer Kontakt".
    await uiLogin(page, "/kontakte/neu");
    await expect(page).toHaveURL(/\/kontakte\/neu$/, { timeout: 60_000 });
    await page.getByLabel("Vorname").fill("Erika");
    await page.getByLabel("Nachname").fill(run);
    await page.getByRole("button", { name: "Speichern" }).click();
    // Earlier runs may have left a similar contact behind: the duplicate check then asks for a
    // confirmation before saving.
    const confirmAnyway = page.getByRole("button", { name: "Trotzdem speichern" });
    await Promise.race([
      page.waitForURL(/\/kontakte\/[0-9a-f-]{36}$/, { timeout: 60_000 }).catch(() => undefined),
      confirmAnyway.waitFor({ state: "visible", timeout: 60_000 }).catch(() => undefined),
    ]);
    if (await confirmAnyway.isVisible()) await confirmAnyway.click();
    await expect(page).toHaveURL(/\/kontakte\/[0-9a-f-]{36}$/, { timeout: 90_000 });
    await expect(page.getByRole("heading", { level: 1 })).toContainText(run);
    const contactId = /\/kontakte\/([0-9a-f-]{36})$/.exec(page.url())![1];
    const contact = await call<{ kind: string; first_name: string; last_name: string }>("GET", `/contacts/${contactId}`);
    expect(contact.kind).toBe("person");
    expect(contact.first_name).toBe("Erika");
    expect(contact.last_name).toBe(run);

    // 2. Ticket through the create form on the ticket list.
    await page.goto("/tickets");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 60_000 });
    const create = page.locator("#ticket-anlegen");
    await create.getByLabel("Titel", { exact: true }).fill(`Heizung ${run}`);
    await create.getByLabel("Beschreibung", { exact: true }).fill(`Heizkörper kalt ${run}`);
    await create.getByLabel("Priorität").selectOption("urgent");
    await create.getByRole("button", { name: "Ticket anlegen" }).click();
    await expect(page).toHaveURL(/\/tickets\/[0-9a-f-]{36}$/, { timeout: 90_000 });
    await expect(page.getByRole("heading", { level: 1 })).toContainText(`Heizung ${run}`);
    const ticketId = /\/tickets\/([0-9a-f-]{36})$/.exec(page.url())![1];
    const ticket = await call<{ title: string; priority: string; status: string }>("GET", `/tickets/${ticketId}`);
    expect(ticket.title).toBe(`Heizung ${run}`);
    expect(ticket.priority).toBe("urgent");
    expect(ticket.status).toBe("new");
  });
});
