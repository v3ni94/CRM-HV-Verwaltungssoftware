import { expect, test } from "@playwright/test";

import { api, apiToken, uiLogin } from "./auth";
import { expectCoarsePointer, expectNoHorizontalOverflow, expectTouchTarget } from "./mobile-layout";

// Data pages a property manager opens on site (M31 WP3) on phone and tablet viewports (WP4):
// calendar toolbar, contact tabs, unit cards of a property, ticket section navigation and the
// document list. Each page is checked for overflow and touch targets; data comes from the API.
test.describe("CRM data pages on phone and tablet @backend @mobile", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("calendar: toolbar fits and its controls are touch targets @backend @mobile", async ({ page }) => {
    test.setTimeout(120_000);
    await uiLogin(page, "/kalender");
    await expect(page).toHaveURL(/\/kalender$/);
    await expectCoarsePointer(page);
    const toolbar = page.getByTestId("calendar-toolbar");
    await expect(toolbar).toBeVisible();
    await expectTouchTarget(page.getByTestId("calendar-today"));
    await expectTouchTarget(toolbar.getByRole("button", { name: /^Vorherige/ }).first());
    await expectTouchTarget(toolbar.getByRole("button", { name: /^Nächste/ }).first());
    await expectNoHorizontalOverflow(page);
  });

  test("contact: tab row is reachable and the page fits @backend @mobile", async ({ page }) => {
    test.setTimeout(120_000);
    const call = api(await apiToken());
    const run = Date.now().toString(36);
    const contact = await call<{ id: string }>("POST", "/contacts", { kind: "person", first_name: "Mobil", last_name: `Kontakt ${run}` }, 201);
    await uiLogin(page, `/kontakte/${contact.id}`);
    await expect(page).toHaveURL(new RegExp(`/kontakte/${contact.id}`));
    const tabs = page.getByTestId("contact-tabs");
    await expect(tabs).toBeVisible();
    for (const link of await tabs.getByRole("link").all()) await expectTouchTarget(link);
    await tabs.getByRole("link", { name: "Kommunikation" }).click();
    await expect(page).toHaveURL(/tab=/);
    await expectNoHorizontalOverflow(page);
  });

  test("property: units as cards on phones, table on tablets @backend @mobile", async ({ page }, testInfo) => {
    test.setTimeout(120_000);
    const call = api(await apiToken());
    const run = Date.now().toString(36);
    let property: { id: string } | null = null;
    for (let i = 0; i < 30 && !property; i++) {
      const number = String(Math.floor(Math.random() * 900) + 100);
      try {
        property = await call<{ id: string }>("POST", "/properties", { number, name: `E2E Mobil ${run}`, management_type: "rental" }, 201);
      } catch (e) {
        if (!String(e).includes(": 409 ")) throw e;
      }
    }
    if (!property) throw new Error("no free property number");
    const building = (await call<{ id: string }>("POST", `/properties/${property.id}/buildings`, { name: "Haus" }, 201)).id;
    await call("POST", `/properties/${property.id}/units`, { building_id: building, number: "01", unit_type: "apartment", living_area_sqm: "50" }, 201);
    await uiLogin(page, `/objekte/${property.id}`);
    await expect(page).toHaveURL(new RegExp(`/objekte/${property.id}$`));
    if (testInfo.project.name === "phone") {
      await expect(page.getByTestId("units-cards")).toBeVisible();
      await expect(page.getByTestId("units-card")).toHaveCount(1);
      await expect(page.getByTestId("units")).toBeHidden();
    } else {
      await expect(page.getByTestId("units")).toBeVisible();
      await expect(page.getByTestId("units-cards")).toBeHidden();
    }
    await expectNoHorizontalOverflow(page);
  });

  test("ticket: section navigation and list bulk bar on phones @backend @mobile", async ({ page }, testInfo) => {
    test.setTimeout(120_000);
    const call = api(await apiToken());
    const run = Date.now().toString(36);
    const ticket = await call<{ id: string }>("POST", "/tickets", { title: `Mobil ${run}` }, 201);
    await uiLogin(page, `/tickets/${ticket.id}`);
    await expect(page).toHaveURL(new RegExp(`/tickets/${ticket.id}$`));
    const nav = page.getByTestId("ticket-section-nav");
    await expect(nav).toBeVisible();
    await expectTouchTarget(page.getByTestId("ticket-section-link-kommentare"));
    await expectTouchTarget(page.getByTestId("ticket-section-link-verlauf"));
    await page.getByTestId("ticket-section-link-kommentare").click();
    await expect(page).toHaveURL(/#kommentare$/);
    await expectNoHorizontalOverflow(page);

    await page.goto("/tickets");
    await expect(page).toHaveURL(/\/tickets/);
    if (testInfo.project.name === "phone") {
      const card = page.getByTestId("ticket-card").filter({ hasText: `Mobil ${run}` });
      await expect(card).toBeVisible();
      await card.getByRole("checkbox").check();
      const bar = page.getByTestId("bulk-bar");
      await expect(bar).toBeVisible();
      const box = await bar.boundingBox();
      const height = await page.evaluate(() => window.innerHeight);
      expect(box!.y + box!.height, "bulk bar bottom edge").toBeLessThanOrEqual(height + 1);
    }
    await expectNoHorizontalOverflow(page);
  });

  test("documents: cards on phones, table on tablets @backend @mobile", async ({ page }, testInfo) => {
    test.setTimeout(120_000);
    await uiLogin(page, "/dokumente");
    await expect(page).toHaveURL(/\/dokumente/);
    const cards = page.getByTestId("documents-cards");
    const table = page.getByTestId("documents");
    if ((await cards.count()) + (await table.count()) > 0) {
      if (testInfo.project.name === "phone") await expect(table).toBeHidden();
      else await expect(cards).toBeHidden();
    }
    await expectNoHorizontalOverflow(page);
  });
});
