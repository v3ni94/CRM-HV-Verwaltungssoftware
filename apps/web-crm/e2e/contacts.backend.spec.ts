import { expect, test } from "@playwright/test";
import * as OTPAuth from "otpauth";

import { rememberSecret } from "./auth";

// Runs only with E2E_BACKEND=1 against a real API (see scripts/e2e-backend.sh).
const email = process.env.E2E_ADMIN_EMAIL ?? "";
const password = process.env.E2E_ADMIN_PASSWORD ?? "";

test.describe("CRM against the API @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("login with TOTP setup, tenant selection, contact CRUD and search @backend", async ({ page }) => {
    test.setTimeout(120_000);
    expect(email, "E2E_ADMIN_EMAIL must be set").not.toBe("");

    // Unauthenticated users are sent to the login page.
    await page.goto("/kontakte");
    await expect(page).toHaveURL(/\/anmelden/);

    await page.getByLabel("E-Mail").fill(email);
    await page.getByLabel("Passwort").fill(password);
    await page.getByRole("button", { name: "Weiter" }).click();

    // First login: TOTP setup with QR code and secret.
    await expect(page).toHaveURL(/\/anmelden\/zweiter-faktor\?einrichten=1/);
    await expect(page.getByRole("img", { name: "QR-Code für die Authenticator-App" })).toBeVisible();
    const secret = (await page.getByTestId("totp-secret").textContent())?.trim() ?? "";
    expect(secret).toMatch(/^[A-Z2-7]+=*$/);
    rememberSecret(secret);
    const totp = new OTPAuth.TOTP({ secret: OTPAuth.Secret.fromBase32(secret), digits: 6, period: 30 });
    await page.getByLabel("Code").fill(totp.generate());
    await page.getByRole("button", { name: "Bestätigen" }).click();

    // The seed admin belongs to both tenants: tenant selection appears.
    await expect(page).toHaveURL(/\/mandant/);
    await page.getByRole("button", { name: "Hausverwaltung Müller GmbH" }).click();
    await expect(page).toHaveURL(/\/kontakte$/);
    await expect(page.getByRole("heading", { name: "Kontakte", level: 1 })).toBeVisible();
    await expect(page.locator("#tenant-switcher")).toHaveValue(/.+/);

    // Create a contact.
    const unique = `E2e${Date.now().toString(36)}`;
    await page.getByRole("link", { name: "Neuer Kontakt" }).click();
    await expect(page).toHaveURL(/\/kontakte\/neu$/);
    await page.getByLabel("Vorname").fill("Erika");
    await page.getByLabel("Nachname").fill(unique);
    await page.getByRole("button", { name: "E-Mail-Adressen: Hinzufügen" }).click();
    await page.getByLabel("E-Mail", { exact: true }).fill(`${unique.toLowerCase()}@example.org`);
    await page.getByRole("button", { name: "Speichern" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(`Erika ${unique}`, { timeout: 15_000 }).catch(async () => {
      // Display name order is defined by the API; accept "Nachname, Vorname" as well.
      await expect(page.getByRole("heading", { level: 1 })).toContainText(unique);
    });
    const detailUrl = page.url();
    expect(detailUrl).toMatch(/\/kontakte\/[0-9a-f-]{36}$/);

    // Find it via the list search.
    await page.goto("/kontakte");
    await page.getByRole("searchbox", { name: "Suche" }).fill(unique);
    await page.getByRole("button", { name: "Filtern" }).click();
    await expect(page).toHaveURL(new RegExp(`q=${unique}`));
    await expect(page.getByRole("link", { name: new RegExp(unique) })).toBeVisible();

    // Find it via Strg+K.
    await page.keyboard.press("Control+k");
    const dialog = page.getByRole("dialog", { name: "Globale Suche" });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("combobox").fill(unique);
    await expect(dialog.getByRole("option", { name: new RegExp(unique) })).toBeVisible();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(detailUrl);

    // Edit it (PUT with If-Match).
    await page.getByRole("link", { name: "Bearbeiten" }).click();
    await expect(page).toHaveURL(/\/bearbeiten$/);
    await page.getByLabel("Nachname").fill(`${unique}x`);
    await page.getByRole("button", { name: "Speichern" }).click();
    await expect(page).toHaveURL(detailUrl);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(`${unique}x`);

    // Delete it.
    await page.getByRole("button", { name: "Löschen" }).click();
    await page.getByRole("button", { name: "Endgültig löschen" }).click();
    await expect(page).toHaveURL(/\/kontakte$/);
    await page.goto(`/kontakte?q=${unique}`);
    await expect(page.getByText("Keine Kontakte gefunden.")).toBeVisible();
  });
});
