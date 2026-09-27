import { expect, test } from "@playwright/test";

import { api, apiToken, uiLogin } from "./auth";

// Additional core-path smoke coverage against a real API (E2E_BACKEND=1, see
// scripts/e2e-backend.sh): dashboard greeting, ticket filters collapsed/expanded, property
// deactivate/reactivate (superadmin only), contact role filter, mailbox filter bar and the
// admin-only ticket evaluation page. Reuses the shared admin login/TOTP state of
// contacts.backend.spec.ts (workers: 1, so this runs after it in the same seed).
test.describe("CRM core paths against the API @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("dashboard shows the greeting @backend", async ({ page }) => {
    test.setTimeout(60_000);
    await uiLogin(page, "/start");
    await expect(page).toHaveURL(/\/start$/);
    // Greeting.<window>.<variant> always renders the viewer's first name; the seeded admin's
    // display name/e-mail is only known at runtime, so only structure is asserted here.
    const heading = page.locator("p.mhvp-title");
    await expect(heading).toBeVisible();
    await expect(heading).not.toBeEmpty();
  });

  test("ticket list: filters start collapsed and expand @backend", async ({ page }) => {
    test.setTimeout(60_000);
    await uiLogin(page, "/tickets");
    await expect(page).toHaveURL(/\/tickets$/);
    const toggle = page.getByTestId("filters-toggle");
    const panel = page.getByTestId("filters-panel");
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(panel).toBeHidden();
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(panel).toBeVisible();
    // Collapses again.
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(panel).toBeHidden();
  });

  test("property: deactivate and reactivate as superadmin @backend", async ({ page }) => {
    test.setTimeout(120_000);
    const token = await apiToken();
    const call = api(token);
    const me = await call<{ is_superadmin: boolean }>("GET", "/auth/me");
    test.skip(!me.is_superadmin, "requires a superadmin seed (MHVP_SEED_ADMIN_SUPERADMIN=true)");

    const run = Date.now().toString(36);
    let property: { id: string; number: string } | null = null;
    for (let i = 0; i < 30; i++) {
      const number = String(Math.floor(Math.random() * 900) + 100);
      try {
        property = await call<{ id: string; number: string }>(
          "POST",
          "/properties",
          { number, name: `E2E Deaktivierung ${run}`, management_type: "rental" },
          201,
        );
        break;
      } catch (e) {
        if (!String(e).includes(": 409 ")) throw e;
      }
    }
    if (!property) throw new Error("no free property number");

    await uiLogin(page, `/objekte/${property.id}`);
    await expect(page).toHaveURL(new RegExp(`/objekte/${property.id}$`));

    // Deactivate ("Verwaltung beenden").
    const terminationSection = page.getByTestId("property-termination");
    await terminationSection.getByRole("button", { name: "Verwaltung beenden" }).click();
    const dialog = page.getByTestId("termination-dialog");
    await expect(dialog).toBeVisible();
    const today = new Date().toISOString().slice(0, 10);
    await dialog.locator("select").selectOption("hoa");
    const dateInputs = dialog.locator('input[type="date"]');
    await dateInputs.nth(0).fill(today);
    await dateInputs.nth(1).fill(today);
    await dialog.getByRole("button", { name: "Weiter" }).click();
    // The confirm step reuses the same label ("Verwaltung beenden") on the danger button.
    await dialog.getByRole("button", { name: "Verwaltung beenden" }).click();

    // Deactivated: banner with reactivate button for the superadmin.
    const banner = page.getByTestId("property-terminated");
    await expect(banner).toBeVisible();
    await banner.getByRole("button", { name: "Wieder aktivieren" }).click();
    const reactivateDialog = page.getByTestId("reactivate-dialog");
    await expect(reactivateDialog).toBeVisible();
    await reactivateDialog.getByRole("button", { name: /wieder aktivieren/i }).click();
    await expect(page.getByTestId("property-terminated")).toHaveCount(0);
    await expect(page.getByTestId("property-termination")).toBeVisible();
  });

  test("contact list: filter by role @backend", async ({ page }) => {
    test.setTimeout(60_000);
    await uiLogin(page, "/kontakte");
    await expect(page).toHaveURL(/\/kontakte$/);
    const roleGroup = page.getByRole("group", { name: "Rolle" });
    await expect(roleGroup).toBeVisible();
    await expect(roleGroup.getByRole("link", { name: "Alle Rollen" })).toHaveAttribute("aria-current", "true");
    const eigentuemer = roleGroup.getByRole("link", { name: "Eigentümer" });
    await eigentuemer.click();
    await expect(page).toHaveURL(/role=eigentuemer/);
    await expect(page.getByRole("group", { name: "Rolle" }).getByRole("link", { name: "Eigentümer" })).toHaveAttribute(
      "aria-current",
      "true",
    );
  });

  test("mail: filter bar loads @backend", async ({ page }) => {
    test.setTimeout(60_000);
    await uiLogin(page, "/mail");
    await expect(page).toHaveURL(/\/mail$/);
    const filters = page.getByTestId("mail-filters");
    await expect(filters).toBeVisible();
    await expect(filters.locator("select").first()).toBeVisible();
  });

  test("evaluation: admin only, 404 for a non-admin user @backend", async ({ page }) => {
    test.setTimeout(90_000);
    // Admin sees the page.
    await uiLogin(page, "/auswertung/tickets");
    await expect(page).toHaveURL(/\/auswertung\/tickets$/);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

    // A non-admin member of the same tenant (no tickets:delete) gets 404.
    const token = await apiToken();
    const call = api(token);
    const run = Date.now().toString(36);
    const email = `e2e-nonadmin-${run}@example.org`;
    const password = "E2eNonAdmin!2026";
    // "standard" role reads tickets but holds no tickets:delete, so it is no tenant
    // administrator (rule M2-07); it is deliberately not tenant_admin/support.
    await call(
      "POST",
      "/tenant/members",
      { email, display_name: `E2E Nonadmin ${run}`, password, role_codes: ["standard"] },
      201,
    );

    const newPage = await page.context().newPage();
    await newPage.goto("/anmelden");
    await newPage.getByLabel("E-Mail").fill(email);
    await newPage.getByLabel("Passwort").fill(password);
    await newPage.getByRole("button", { name: "Weiter" }).click();
    await newPage.waitForURL(/\/(mandant|anmelden\/zweiter-faktor|start|tickets)/);
    if (newPage.url().includes("/mandant")) {
      await newPage.getByRole("button", { name: "Hausverwaltung Müller GmbH" }).click();
    }
    const response = await newPage.goto("/auswertung/tickets");
    expect(response?.status()).toBe(404);
    await expect(newPage.getByText(/404|nicht gefunden|could not be found/i)).toBeVisible({ timeout: 15_000 });
    await newPage.close();
  });
});
