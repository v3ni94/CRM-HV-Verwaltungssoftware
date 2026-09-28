import { expect, test } from "@playwright/test";

import { adminToken, api, invitePortalUser } from "./auth";

// Portal day and evening mode (1.40.0) against a real API (E2E_BACKEND=1, see
// scripts/e2e-backend.sh): the header switch Hell, Dunkel, Automatisch sets data-theme on
// <html>, the choice is kept in this browser (localStorage) across a reload, and Automatisch
// follows the operating system preference (prefers-color-scheme), also live.

test.describe("portal theme switch @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("Hell, Dunkel and Automatisch set data-theme and persist after a reload @backend", async ({ page }) => {
    test.setTimeout(120_000);
    const call = api(await adminToken());
    const run = Date.now().toString(36);
    const contact = await call<{ id: string }>("POST", "/contacts", { kind: "person", first_name: "Hanna", last_name: `Darstellung${run}` }, 201);
    const { email, password } = await invitePortalUser(call, contact.id, `darstellung-${run}`);

    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/anmelden");
    await page.getByLabel("E-Mail").fill(email);
    await page.getByLabel("Passwort").fill(password);
    await page.getByRole("button", { name: "Weiter" }).click();
    await expect(page).toHaveURL(/\/start$/);

    const html = page.locator("html");
    const group = page.getByRole("banner").getByRole("radiogroup", { name: "Darstellung" });
    const radio = (name: string) => group.getByRole("radio", { name, exact: true });
    // Default: Automatisch, resolved from the (emulated light) operating system preference.
    await expect(radio("Automatisch")).toHaveAttribute("aria-checked", "true");
    await expect(html).toHaveAttribute("data-theme", "day");

    await radio("Dunkel").click();
    await expect(radio("Dunkel")).toHaveAttribute("aria-checked", "true");
    await expect(html).toHaveAttribute("data-theme", "evening");
    await page.reload();
    await expect(html).toHaveAttribute("data-theme", "evening");
    await expect(radio("Dunkel")).toHaveAttribute("aria-checked", "true");

    await radio("Hell").click();
    await expect(html).toHaveAttribute("data-theme", "day");
    await page.reload();
    await expect(html).toHaveAttribute("data-theme", "day");
    await expect(radio("Hell")).toHaveAttribute("aria-checked", "true");

    // Automatisch follows the operating system preference, live and after a reload.
    await radio("Automatisch").click();
    await expect(html).toHaveAttribute("data-theme", "day");
    await page.emulateMedia({ colorScheme: "dark" });
    await expect(html).toHaveAttribute("data-theme", "evening");
    await page.reload();
    await expect(html).toHaveAttribute("data-theme", "evening");
    await expect(radio("Automatisch")).toHaveAttribute("aria-checked", "true");
    await page.emulateMedia({ colorScheme: "light" });
    await expect(html).toHaveAttribute("data-theme", "day");
  });
});
