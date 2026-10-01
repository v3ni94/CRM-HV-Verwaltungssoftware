import { expect, test } from "@playwright/test";

import { adminToken, api } from "./auth";
import { expectCoarsePointer, expectNoHorizontalOverflow, expectTouchTarget } from "./mobile-layout";

// Portal handover for a helper on phone and tablet viewports (M31 WP4 and WP5): menu entry
// Übergabe, the protocol without overflow, camera and gallery inputs and a signature canvas of
// at least 200 px. Runs only with E2E_BACKEND=1 in the projects phone, tablet and tablet-landscape.
test.describe("Portal handover on phone and tablet @backend @mobile", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("helper opens the protocol with touch targets and two file inputs @backend @mobile", async ({ page }) => {
    test.setTimeout(120_000);
    const call = api(await adminToken());
    const run = Date.now().toString(36);
    const p = await call<{ id: string }>("POST", "/handover/protocols", { kind: "rental" }, 201);
    await call("PATCH", `/handover/protocols/${p.id}`, { street: "Portalweg", house_number: "2", postal_code: "40789", city: "Monheim am Rhein" }, 200);
    const email = `gehilfe-mobil-${run}@example.org`;
    const password = "Test-Passwort-1!";
    const access = await call<{ invitation_token: string | null }>(
      "POST",
      `/handover/protocols/${p.id}/helper-access`,
      { name: `Gerda Gehilfin ${run}`, email, kind: "helper", invitation_as_mail_draft: false },
      201,
    );
    await call("POST", "/portal/invitations/accept", { token: access.invitation_token, password });
    // One room so the section shows the photo picker of an existing entry.
    await call("POST", `/handover/protocols/${p.id}/rooms`, { name: "Flur" }, 201);

    await page.goto("/anmelden");
    await page.getByLabel("E-Mail").fill(email);
    await page.getByLabel("Passwort").fill(password);
    await page.getByRole("button", { name: "Weiter" }).click();
    await expect(page).toHaveURL(/\/start$/);
    await expectCoarsePointer(page);
    await expectNoHorizontalOverflow(page);
    const toggle = page.getByRole("button", { name: "Menü öffnen" });
    if (await toggle.isVisible()) {
      await expectTouchTarget(toggle);
      await toggle.click();
    }
    const entry = page.getByRole("link", { name: "Übergabe", exact: true });
    await expect(entry).toBeVisible();
    await expectTouchTarget(entry);
    await entry.click();
    await expect(page).toHaveURL(/\/uebergabe$/);
    await page.getByRole("link", { name: /UP-/ }).first().click();
    await expect(page).toHaveURL(new RegExp(`/uebergabe/${p.id}$`));
    await expect(page.getByTestId("handover-fill")).toBeVisible();
    await expectNoHorizontalOverflow(page);
    await expect(page.locator("a[target='_blank']")).toHaveCount(0);

    // Camera and gallery inputs of the photo picker (section Räume) and the signature canvas
    // (section Unterschriften); the section chips are touch targets.
    const tabs = page.getByRole("navigation", { name: "Abschnitte" });
    await expectTouchTarget(tabs.getByRole("button", { name: "Räume" }));
    await tabs.getByRole("button", { name: "Räume" }).click();
    await expect(page.getByText("Flur")).toBeVisible();
    const camera = page.getByTestId("photo-input-camera").first();
    const gallery = page.getByTestId("photo-input-gallery").first();
    await expect(camera).toHaveAttribute("capture", "environment");
    await expect(gallery).toHaveAttribute("multiple", "");
    await expectNoHorizontalOverflow(page);
    await tabs.getByRole("button", { name: "Unterschriften" }).click();
    const pad = page.getByTestId("signature-pad");
    await expect(pad).toBeVisible();
    const canvas = pad.locator("canvas");
    await canvas.scrollIntoViewIfNeeded();
    const box = await canvas.boundingBox();
    expect(box?.height ?? 0, "portal signature canvas height").toBeGreaterThanOrEqual(200);
    await expectNoHorizontalOverflow(page);
  });
});
