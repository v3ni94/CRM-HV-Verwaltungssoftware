import { expect, test } from "@playwright/test";

import { uiLogin } from "./auth";

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
});
