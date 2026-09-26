import { expect, test } from "@playwright/test";

import { api, apiToken, uiLogin } from "./auth";

// Additional smoke coverage against a real API (E2E_BACKEND=1, see scripts/e2e-backend.sh):
// the KI chat widget, the SLA settings page and creating an Übergabeprotokoll for a manually
// entered object (not from the portfolio). Reuses the shared admin login/TOTP state of
// contacts.backend.spec.ts (workers: 1, so this runs after it in the same seed).
test.describe("CRM feature smoke against the API @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("KI chat widget opens @backend", async ({ page }) => {
    test.setTimeout(60_000);
    await uiLogin(page, "/kontakte");
    await expect(page).toHaveURL(/\/kontakte$/);
    await page.getByRole("button", { name: "KI-Assistent öffnen" }).click();
    await expect(page.getByRole("region", { name: "KI-Assistent" })).toBeVisible();
    await expect(page.getByRole("button", { name: "KI-Assistent schließen" })).toBeVisible();
  });

  test("SLA settings page loads @backend", async ({ page }) => {
    test.setTimeout(60_000);
    await uiLogin(page, "/einstellungen/sla");
    await expect(page).toHaveURL(/\/einstellungen\/sla$/);
    await expect(page.getByRole("heading", { name: "SLA und Bereitschaft", level: 1 })).toBeVisible();
  });

  test("Übergabeprotokoll: create with a manually entered object @backend", async ({ page }) => {
    test.setTimeout(60_000);
    const run = Date.now().toString(36);
    await uiLogin(page, "/makler/uebergabe/neu");
    await expect(page).toHaveURL(/\/makler\/uebergabe\/neu$/);
    await page.getByTestId("handover-object-manual").check();
    await page.getByLabel("Straße").fill("Beispielstraße");
    await page.getByLabel("Hausnummer").fill("12");
    await page.getByLabel("Postleitzahl").fill("40000");
    await page.getByLabel("Ort").fill(`Musterstadt ${run}`);
    await page.getByRole("button", { name: "Anlegen" }).click();
    await expect(page).toHaveURL(/\/makler\/uebergabe\/[0-9a-f-]{36}$/);
    await expect(page.getByText(`Musterstadt ${run}`)).toBeVisible();
  });

  test("ticket mail thread and reply form load @backend", async ({ page }) => {
    test.setTimeout(90_000);
    const run = Date.now().toString(36);
    const ticket = await api(await apiToken())<{ id: string; number: number }>("POST", "/tickets", { title: `Mailverlauf ${run}` }, 201);
    await uiLogin(page, `/tickets/${ticket.id}`);
    await expect(page).toHaveURL(new RegExp(`/tickets/${ticket.id}$`));
    await expect(page.getByRole("heading", { level: 1 })).toContainText(`#${ticket.number} Mailverlauf ${run}`);
    const section = page.getByTestId("ticket-mail-section");
    await expect(section.getByRole("heading", { name: "Mailverlauf", level: 2 })).toBeVisible();
    await expect(section.getByText("Zu diesem Ticket liegen keine E-Mails vor.")).toBeVisible();
    await expect(section.getByText("Der Mailverlauf konnte nicht geladen werden.")).toHaveCount(0);
    const reply = page.getByTestId("ticket-reply-panel");
    await expect(reply.getByRole("heading", { name: "Antworten", level: 2 })).toBeVisible();
    await expect(page.getByTestId("ticket-reply-form")).toBeVisible();
    // Without a mailbox for the ticket the form is shown but marked as not sendable.
    await expect(reply.getByRole("alert")).toContainText("kein sendefähiges Postfach");
    await expect(reply.getByText("An", { exact: true })).toBeVisible();
    await expect(reply.getByText("Betreff", { exact: true })).toBeVisible();
    await expect(reply.getByText("Text", { exact: true })).toBeVisible();
  });

  test("automation settings page loads @backend", async ({ page }) => {
    test.setTimeout(60_000);
    await uiLogin(page, "/einstellungen/automatisierung");
    await expect(page).toHaveURL(/\/einstellungen\/automatisierung$/);
    await expect(page.getByRole("heading", { name: "Automatisierung", level: 1 })).toBeVisible();
    await expect(page.getByText(/Regeln lösen keine Buchungen/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Neue Regel" })).toBeVisible();
  });
});
