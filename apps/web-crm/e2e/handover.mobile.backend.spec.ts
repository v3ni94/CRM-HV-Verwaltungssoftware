import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { api, apiToken, uiLogin } from "./auth";
import { expectCoarsePointer, expectHeaderOneRow, expectNoHorizontalOverflow, expectTouchTarget } from "./mobile-layout";

// Shell and the complete handover path on phone and tablet viewports (M31 WP4) against a real
// API (E2E_BACKEND=1, scripts/e2e-backend.sh with MHVP_E2E_PW_ARGS="--project phone"). Runs
// only in the projects phone, tablet and tablet-landscape (grep @mobile in playwright.config.ts).
// Everything is created through the API first (rule 0.1.4); the browser then records a room,
// a defect with a photo, a meter reading and a signature and completes the protocol.
const PHOTO = path.resolve(process.cwd(), "e2e/fixtures/photo.jpg");

async function drawSignature(page: Page, canvas: ReturnType<Page["locator"]>) {
  const box = await canvas.boundingBox();
  if (!box) throw new Error("signature canvas has no box");
  const x0 = box.x + box.width * 0.2;
  const y0 = box.y + box.height * 0.5;
  try {
    await page.mouse.move(x0, y0);
    await page.mouse.down();
    await page.mouse.move(x0 + box.width * 0.2, y0 - 20, { steps: 8 });
    await page.mouse.move(x0 + box.width * 0.5, y0 + 20, { steps: 8 });
    await page.mouse.up();
  } catch {
    // Fallback: synthetic pointer events straight on the canvas.
    await canvas.dispatchEvent("pointerdown", { clientX: x0, clientY: y0, pointerId: 1, pointerType: "touch", isPrimary: true, buttons: 1 });
    await canvas.dispatchEvent("pointermove", { clientX: x0 + 60, clientY: y0 - 10, pointerId: 1, pointerType: "touch", isPrimary: true, buttons: 1 });
    await canvas.dispatchEvent("pointerup", { clientX: x0 + 60, clientY: y0 - 10, pointerId: 1, pointerType: "touch", isPrimary: true });
  }
}

test.describe("CRM shell and handover on phone and tablet @backend @mobile", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("start page: one row header, drawer or icon rail, no overflow @backend @mobile", async ({ page }, testInfo) => {
    test.setTimeout(120_000);
    await uiLogin(page, "/start");
    await expect(page).toHaveURL(/\/start$/);
    await expectCoarsePointer(page);
    await expectHeaderOneRow(page);
    await expectNoHorizontalOverflow(page);
    const toggle = page.getByTestId("nav-toggle");
    if (testInfo.project.name === "tablet-landscape") {
      // Icon rail from lg (1024 px): no hamburger, the rail head button opens the drawer.
      await expect(toggle).toBeHidden();
      const railOpen = page.getByTestId("rail-open-nav");
      await expectTouchTarget(railOpen);
      await railOpen.click();
    } else {
      await expectTouchTarget(toggle);
      await toggle.click();
    }
    const drawer = page.getByRole("dialog");
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("button", { name: "Schließen" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(drawer).toBeHidden();
    // Header controls are touch targets.
    await expectTouchTarget(page.getByRole("button", { name: "Suche und Befehle öffnen" }));
  });

  test("handover list: cards on phones, table on tablets @backend @mobile", async ({ page }, testInfo) => {
    test.setTimeout(120_000);
    const call = api(await apiToken());
    const run = Date.now().toString(36);
    const p = await call<{ id: string }>("POST", "/handover/protocols", { kind: "rental" }, 201);
    await call("PATCH", `/handover/protocols/${p.id}`, { street: `Kartenweg ${run}`, house_number: "1", postal_code: "40789", city: "Monheim am Rhein" }, 200);
    await uiLogin(page, "/makler/uebergabe");
    await expect(page).toHaveURL(/\/makler\/uebergabe$/);
    await expectNoHorizontalOverflow(page);
    if (testInfo.project.name === "phone") {
      await expect(page.getByTestId("handover-cards")).toBeVisible();
      await expect(page.getByTestId("handover")).toBeHidden();
      await expect(page.getByTestId("handover-card").filter({ hasText: `Kartenweg ${run}` })).toBeVisible();
    } else {
      await expect(page.getByTestId("handover")).toBeVisible();
      await expect(page.getByTestId("handover-cards")).toBeHidden();
      await expect(page.getByTestId("handover").getByRole("row").filter({ hasText: `Kartenweg ${run}` })).toBeVisible();
    }
  });

  test("handover path: steps, room, defect with photo, meter, signature, completion, read view @backend @mobile", async ({ page }) => {
    test.setTimeout(240_000);
    const call = api(await apiToken());
    const run = Date.now().toString(36);
    const p = await call<{ id: string }>("POST", "/handover/protocols", { kind: "rental" }, 201);
    await call("PATCH", `/handover/protocols/${p.id}`, { street: `Handyweg ${run}`, house_number: "3", postal_code: "40789", city: "Monheim am Rhein", handover_date: "2026-09-29" }, 200);
    await call("POST", `/handover/protocols/${p.id}/participants`, { role: "tenant", first_name: "Mara", last_name: `Muster ${run}` }, 201);
    const bff = new RegExp(`/api/bff/handover/protocols/${p.id}$`);

    await uiLogin(page, `/makler/uebergabe/${p.id}`);
    await expect(page).toHaveURL(new RegExp(`/makler/uebergabe/${p.id}$`));
    await expect(page.getByTestId("handover-editor")).toBeVisible();
    await expectCoarsePointer(page);
    await expectNoHorizontalOverflow(page);

    // Every step chip is a touch target; Weiter switches and persists current_step (200),
    // also for Mängel, which the API rejected before M31 (422).
    for (const step of ["object", "participants", "deposit", "internal", "meters", "rooms", "defects", "keys", "items", "notes", "attachments", "signatures", "summary"]) {
      await expectTouchTarget(page.getByTestId(`step-${step}`));
    }
    const footer = page.getByTestId("step-footer");
    await expectTouchTarget(footer.getByRole("button", { name: "Weiter" }));
    const [patch] = await Promise.all([
      page.waitForResponse((r) => bff.test(r.url()) && r.request().method() === "PATCH"),
      footer.getByRole("button", { name: "Weiter" }).click(),
    ]);
    expect(patch.status()).toBe(200);
    expect(patch.request().postDataJSON()).toMatchObject({ current_step: "participants" });
    await expect(page.getByTestId("step-participants")).toHaveAttribute("aria-current", "step");
    const [patchDefects] = await Promise.all([
      page.waitForResponse((r) => bff.test(r.url()) && r.request().method() === "PATCH"),
      page.getByTestId("step-defects").click(),
    ]);
    expect(patchDefects.status()).toBe(200);
    expect(patchDefects.request().postDataJSON()).toMatchObject({ current_step: "defects" });

    // Room with counter 1 on the chip.
    await page.getByTestId("step-rooms").click();
    await page.getByRole("button", { name: "Raum hinzufügen" }).click();
    const roomForm = page.getByTestId("item-form-rooms");
    await roomForm.getByLabel("Bezeichnung").fill("Küche");
    await roomForm.getByRole("button", { name: "Speichern" }).click();
    await expect(page.getByTestId("section-rooms").getByText("Küche")).toBeVisible();
    await expect(page.getByTestId("step-rooms")).toContainText("1");
    await expectNoHorizontalOverflow(page);

    // Defect with a photo picked through the gallery input (capture first): status Fertig,
    // thumbnail request answered with no-store.
    await page.getByTestId("step-defects").click();
    await page.getByRole("button", { name: "Mangel hinzufügen" }).click();
    const defectForm = page.getByTestId("item-form-defects");
    await defectForm.getByLabel("Titel").fill(`Kratzer ${run}`);
    await defectForm.getByLabel("Raum").selectOption({ label: "Küche" });
    await expect(page.getByTestId("photo-capture")).toHaveAttribute("capture", "environment");
    await page.getByTestId("photo-pick").setInputFiles(PHOTO);
    const thumbnail = page.waitForResponse((r) => r.url().includes("/thumbnail") && r.request().method() === "GET");
    await defectForm.getByRole("button", { name: "Speichern" }).click();
    await expect(page.getByTestId("upload-status").locator("[data-state=done]")).toHaveCount(1, { timeout: 30_000 });
    const thumb = await thumbnail;
    expect(thumb.status()).toBe(200);
    expect(thumb.headers()["cache-control"]).toContain("no-store");
    await expect(page.getByTestId("section-defects").getByText(`Kratzer ${run}`)).toBeVisible();
    await expect(page.getByTestId("photo-strip").locator("img").first()).toBeVisible();

    // Meter reading with a decimal comma, shown formatted.
    await page.getByTestId("step-meters").click();
    await page.getByRole("button", { name: "Zähler hinzufügen" }).click();
    const meterForm = page.getByTestId("item-form-meters");
    await meterForm.getByLabel("Zählerart").selectOption("electricity");
    await meterForm.getByLabel("Zählerstand").fill("1234,5");
    await meterForm.getByLabel("Einheit").selectOption("kWh");
    await meterForm.getByRole("button", { name: "Speichern" }).click();
    await expect(page.getByTestId("section-meters")).toContainText("1.234,5");

    // Signature of the participant in the full screen sheet.
    await page.getByTestId("step-signatures").click();
    const signButton = page.getByRole("button", { name: `Unterschrift von Mara Muster ${run}` });
    await expectTouchTarget(signButton);
    await signButton.click();
    const sheet = page.getByTestId("signature-sheet");
    await expect(sheet).toBeVisible();
    await expect(sheet.getByText(`Bitte das Gerät an Mara Muster ${run} übergeben.`)).toBeVisible();
    const canvas = sheet.locator("canvas");
    const canvasBox = await canvas.boundingBox();
    expect(canvasBox?.height ?? 0, "signature canvas height").toBeGreaterThanOrEqual(200);
    await drawSignature(page, canvas);
    const [signed] = await Promise.all([
      page.waitForResponse((r) => r.url().includes(`/handover/protocols/${p.id}/signatures`) && r.request().method() === "POST"),
      sheet.getByRole("button", { name: "Unterschrift speichern" }).click(),
    ]);
    expect(signed.status()).toBe(201);
    await expect(sheet).toBeHidden();
    await expect(page.getByRole("button", { name: `Unterschrift von Mara Muster ${run}` })).toHaveCount(0);
    await expect(page.locator("img[src*='/api/handover-files/documents/']").first()).toBeVisible();

    // Completion via ConfirmSheet (with force because hints such as missing keys remain),
    // then the read view without inputs and a same tab PDF link.
    await page.getByTestId("step-summary").click();
    await expect(page.getByTestId("handover-summary")).toBeVisible();
    const complete = page.getByRole("button", { name: "Protokoll verbindlich abschließen" });
    await complete.click();
    const force = page.getByRole("button", { name: "Trotz Hinweisen verbindlich abschließen" });
    if (await force.isVisible()) await force.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expectTouchTarget(dialog.getByRole("button", { name: "Protokoll verbindlich abschließen" }));
    const [completed] = await Promise.all([
      page.waitForResponse((r) => r.url().includes(`/handover/protocols/${p.id}/complete`) && r.request().method() === "POST"),
      dialog.getByRole("button", { name: "Protokoll verbindlich abschließen" }).click(),
    ]);
    expect(completed.status()).toBe(200);
    await page.reload();
    await expect(page.getByTestId("handover-summary")).toBeVisible();
    await expect(page.getByTestId("handover-summary").locator("input, textarea, select")).toHaveCount(0);
    await expect(page.getByTestId("handover-editor").locator("input:not([type=hidden]), textarea")).toHaveCount(0);
    const pdf = page.getByTestId("summary-pdf");
    await expect(pdf).toHaveAttribute("href", `/api/handover-files/handover/protocols/${p.id}/pdf`);
    await expect(pdf).not.toHaveAttribute("target", /.+/);
    await expect(page.locator("a[target='_blank']")).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
  });
});
