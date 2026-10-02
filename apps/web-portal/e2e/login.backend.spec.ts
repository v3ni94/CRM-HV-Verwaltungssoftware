import { expect, test } from "@playwright/test";

import { adminToken, api, invitePortalUser } from "./auth";

// GAI-622 (AJ25): portal login as its own case against a real API (E2E_BACKEND=1): a protected
// page redirects to the login, a wrong password is refused, the correct one opens the overview,
// and without the session cookies the overview is closed again.
test.describe("Portal login @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("Portal-Anmeldung mit falschem und richtigem Passwort @backend", async ({ page, context }) => {
    test.setTimeout(180_000);
    const call = api(await adminToken());
    const run = Date.now().toString(36);
    const contact = await call<{ id: string }>(
      "POST",
      "/contacts",
      { kind: "person", first_name: "Erika", last_name: `Login${run}` },
      201,
    );
    const { email, password } = await invitePortalUser(call, contact.id, `login-${run}`);

    await page.goto("/start");
    await expect(page).toHaveURL(/\/anmelden/, { timeout: 60_000 });

    await page.getByLabel("E-Mail").fill(email);
    await page.getByLabel("Passwort").fill("falsches-Passwort-AJ25");
    await page.getByRole("button", { name: "Weiter" }).click();
    await expect(page.locator('p[role="alert"]').first()).toBeVisible({ timeout: 60_000 });
    await expect(page).toHaveURL(/\/anmelden/);

    await page.getByLabel("Passwort").fill(password);
    await page.getByRole("button", { name: "Weiter" }).click();
    await expect(page).toHaveURL(/\/start$/, { timeout: 60_000 });
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Übersicht");

    await context.clearCookies();
    await page.goto("/start");
    await expect(page).toHaveURL(/\/anmelden/, { timeout: 60_000 });
  });
});
