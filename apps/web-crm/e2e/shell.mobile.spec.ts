import { expect, test } from "@playwright/test";

import { expectCoarsePointer, expectFontSizeAtLeast, expectNoHorizontalOverflow, expectTouchTarget } from "./mobile-layout";

// Shell smoke on phone and tablet viewports (M31 WP4) without a backend: the login page must
// fit the screen, its fields must be touch targets and, on phones, use 16 px text so iOS does
// not zoom on focus. The signed in header and drawer are covered by handover.mobile.backend.spec.ts.
test.describe("CRM shell on phone and tablet @mobile", () => {
  test("login page fits the viewport and uses touch targets @mobile", async ({ page }, testInfo) => {
    await page.goto("/anmelden");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Willkommen zurück");
    await expectCoarsePointer(page);
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

  test("login page has no horizontal scroll after focusing a field @mobile", async ({ page }) => {
    await page.goto("/anmelden");
    await page.getByLabel("E-Mail").focus();
    await page.getByLabel("E-Mail").fill("objektbetreuer@example.org");
    await expectNoHorizontalOverflow(page);
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const width = await page.evaluate(() => Math.min(window.innerWidth, window.visualViewport?.width ?? Infinity));
    expect(scrollWidth, `document is ${scrollWidth} px wide on a ${width} px viewport`).toBeLessThanOrEqual(width + 1);
  });
});
