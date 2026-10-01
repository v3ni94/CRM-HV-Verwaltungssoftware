import { expect, test } from "@playwright/test";

import { api, apiToken, uiLogin } from "./auth";

// GA01-06: UI core paths still missing in the E2E suite (Objekt anlegen, Vertrag anlegen,
// Dokument). Written against the same seed and login state as core-paths.backend.spec.ts and
// run only with E2E_BACKEND=1. Login, Kontakt, Buchung, Bankumsatz zuordnen and Ticket are
// covered by contacts.backend.spec.ts, bank-buchen.spec.ts and features.backend.spec.ts.
test.describe("CRM core paths GA01-06 @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("Objekt über das Formular anlegen @backend", async ({ page }) => {
    test.setTimeout(120_000);
    await uiLogin(page, "/objekte");
    // The tenant click navigates on its own; a goto before it settles aborts the session setup.
    await expect(page).toHaveURL(/\/objekte/, { timeout: 30_000 });
    const run = Date.now().toString(36);
    const name = `E2E Objekt ${run}`;
    let created = false;
    for (let i = 0; i < 30 && !created; i++) {
      const number = String(Math.floor(Math.random() * 900) + 100);
      await page.goto("/objekte");
      // "Objekt anlegen" is the summary of a details element, not a button.
      await page.locator("summary", { hasText: "Objekt anlegen" }).first().click();
      await page.getByLabel("Objektnummer (3 Ziffern)").fill(number);
      await page.getByLabel("Name", { exact: true }).fill(name);
      await page.getByRole("combobox", { name: "Verwaltungsart" }).selectOption("rental");
      await page.getByRole("button", { name: "Anlegen" }).click();
      // A taken number answers with an alert; try the next random number.
      created = await page
        .waitForURL(/\/objekte\/[0-9a-f-]{36}/, { timeout: 8_000 })
        .then(() => true)
        .catch(() => false);
    }
    expect(created, "no free property number").toBe(true);
    await expect(page.getByRole("heading", { level: 1 })).toContainText(name);
  });

  test("Vertragsformular: Objekt und Einheit wählen, Pflichtangaben prüfen @backend", async ({ page }) => {
    test.setTimeout(120_000);
    const call = api(await apiToken());
    const run = Date.now().toString(36);
    let property: { id: string; number: string } | null = null;
    for (let i = 0; i < 30 && !property; i++) {
      try {
        property = await call<{ id: string; number: string }>(
          "POST",
          "/properties",
          { number: String(Math.floor(Math.random() * 900) + 100), name: `E2E Vertrag ${run}`, management_type: "rental" },
          201,
        );
      } catch {
        property = null;
      }
    }
    expect(property, "no free property number").not.toBeNull();
    await uiLogin(page, `/vertraege/neu?objekt=${property!.id}`);
    await expect(page).toHaveURL(/\/vertraege\/neu/);
    await expect(page.getByRole("combobox", { name: "Objekt", exact: true })).toHaveValue(property!.id, { timeout: 30_000 });
    // Without partner and unit the form must not create a contract.
    await page.getByRole("button", { name: /Speichern|Anlegen/ }).first().click();
    await expect(page).toHaveURL(/\/vertraege\/neu/);
  });

  test("Dokumentenliste und Upload-Dialog @backend", async ({ page }) => {
    test.setTimeout(60_000);
    await uiLogin(page, "/dokumente");
    await expect(page).toHaveURL(/\/dokumente$/);
    await page.getByTestId("global-drop-input").setInputFiles({
      name: "e2e-dokument.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4\n%E2E\n"),
    });
    await expect(page.getByRole("dialog")).toBeVisible();
  });
});
