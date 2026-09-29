import { expect, test } from "@playwright/test";

import { expectCoarsePointer, expectFontSizeAtLeast, expectHeaderOneRow, expectNoHorizontalOverflow, expectTouchTarget } from "./mobile-layout";

// Portal shell smoke on phone and tablet viewports (M31 WP4) without a backend: home page and
// login page fit the screen, the login fields are touch targets with 16 px text on phones.
// Manifest, icons and service worker stay in smoke.spec.ts (project chromium).
test.describe("Portal shell on phone and tablet @mobile", () => {
  test("home page fits the viewport @mobile", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("MH Verwaltungsplattform");
    await expectCoarsePointer(page);
    await expectNoHorizontalOverflow(page);
    if ((await page.locator("header").count()) > 0) await expectHeaderOneRow(page);
  });

  test("login page uses touch targets and 16 px fields on phones @mobile", async ({ page }, testInfo) => {
    await page.goto("/anmelden");
    await expectNoHorizontalOverflow(page);
    const email = page.getByLabel("E-Mail");
    const password = page.getByLabel("Passwort");
    await expectTouchTarget(email);
    await expectTouchTarget(password);
    await expectTouchTarget(page.getByRole("button", { name: "Weiter" }));
    if (testInfo.project.name === "phone") {
      await expectFontSizeAtLeast(email, 16);
      await expectFontSizeAtLeast(password, 16);
    }
  });
});
