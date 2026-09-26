import { expect, test } from "@playwright/test";

import { uiLogin } from "./auth";

// Immoware24 import assistant against a real API (E2E_BACKEND=1, see scripts/e2e-backend.sh):
// report type, CSV upload, column mapping saved as a template, validation, test run. The test
// run must not change the portfolio (A71, M8 "Playwright flow"). Nothing is applied here.
test.describe("Immoware24 import assistant against the API @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("upload a small CSV, map columns, validate and run a test run @backend", async ({ page }) => {
    test.setTimeout(120_000);
    const run = Date.now().toString(36);
    // Three rows: two valid, one with a property number that is not three digits.
    const csv = [
      "Objekt-Nr;Bezeichnung;Typ;Straße;Nr;PLZ;Ort",
      `901;E2E Import WEG ${run};WEG;Lindenweg;4;40789;Monheim am Rhein`,
      `902;E2E Import Miete ${run};Miete;Am Markt;1;41812;Erkelenz`,
      `7;E2E Import defekt ${run};WEG;;;;`,
    ].join("\n");

    await uiLogin(page, "/importe/immoware24");
    await expect(page).toHaveURL(/\/importe\/immoware24$/);
    await expect(page.getByRole("heading", { name: "Importassistent", level: 1 })).toBeVisible();
    const before = Number((await page.locator("dl dt", { hasText: /^Objekte$/ }).locator("xpath=following-sibling::dd").textContent()) ?? "0");

    // Step 1: report type (properties is preselected).
    await page.getByRole("radio", { name: /^Objekte/ }).check();
    await page.getByRole("button", { name: "Weiter" }).click();

    // Step 2: file.
    await expect(page.getByRole("heading", { name: /Datei hochladen: Objekte/ })).toBeVisible();
    await page.getByLabel("Datei (xlsx oder csv)").setInputFiles({
      name: `objekte-${run}.csv`,
      mimeType: "text/csv",
      buffer: Buffer.from(csv, "utf8"),
    });
    await page.getByRole("button", { name: "Hochladen und einlesen" }).click();

    // Step 3: mapping; required fields are Objektnummer, Bezeichnung and Verwaltungsart.
    await expect(page.getByRole("heading", { name: "Spalten zuordnen" })).toBeVisible();
    await expect(page.getByText(/Objekte: 3 Zeilen, 7 Spalten/)).toBeVisible();
    await expect(page.getByTestId("required-missing")).toBeVisible();
    await page.getByLabel(/Objektnummer \(dreistellig\)/).selectOption("Objekt-Nr");
    await page.getByLabel(/^Bezeichnung/).selectOption("Bezeichnung");
    await page.getByLabel(/^Verwaltungsart/).selectOption("Typ");
    await page.getByLabel(/^Straße/).selectOption("Straße");
    await page.getByLabel(/^Hausnummer/).selectOption("Nr");
    await page.getByLabel(/^PLZ/).selectOption("PLZ");
    await page.getByLabel(/^Ort/).selectOption("Ort");
    await expect(page.getByTestId("required-missing")).toHaveCount(0);
    // Value map for the choice field: WEG -> hoa, Miete -> rental.
    const valueMap = page.getByTestId("value-map-management_type");
    await expect(valueMap).toBeVisible();
    // The wrapping label's text includes the option texts, so the accessible name is used.
    await valueMap.getByRole("combobox", { name: "WEG" }).selectOption("hoa");
    await valueMap.getByRole("combobox", { name: "Miete" }).selectOption("rental");
    await page.getByLabel("Name der Vorlage").fill(`E2E Objekte ${run}`);
    await page.getByRole("button", { name: "Als neue Vorlagenversion speichern und prüfen" }).click();

    // Step 4: validation report: 2 valid, 1 invalid; then the test run changes nothing.
    await expect(page.getByRole("heading", { name: "Prüfbericht" })).toBeVisible();
    await expect(page.getByTestId("validation-counts")).toContainText("2");
    await expect(page.getByTestId("validation-counts")).toContainText("gültig");
    await expect(page.getByTestId("validation-counts")).toContainText("fehlerhaft");
    await page.getByLabel("Zeilen nach Status").selectOption("invalid");
    await expect(page.getByTestId("validation-rows")).toContainText("4");
    await page.getByRole("button", { name: "Testlauf starten" }).click();
    await expect(page.getByTestId("test-run-notice")).toContainText("Es wurde nichts gespeichert");
    await expect(page.getByTestId("test-run-report")).toContainText("angelegt");
    await expect(page.getByTestId("test-run-report")).toContainText("2");
    // The wizard's own button; the list imports on the same page have their own (disabled) ones.
    const wizard = page.locator("section", { has: page.getByRole("heading", { name: "Prüfbericht" }) });
    await expect(wizard.getByRole("button", { name: "Übernehmen" }).first()).toBeEnabled();

    // The portfolio count is unchanged after the test run.
    await page.goto("/importe/immoware24");
    const after = Number((await page.locator("dl dt", { hasText: /^Objekte$/ }).locator("xpath=following-sibling::dd").textContent()) ?? "0");
    expect(after).toBe(before);
  });
});
