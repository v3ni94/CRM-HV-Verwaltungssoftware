import { expect, test, type Page } from "@playwright/test";

import { api, apiToken, uiLogin } from "./auth";

// Core paths of the new pages of waves 2 and 3 against a real API (E2E_BACKEND=1, one worker).
// Pattern: wave-2026-09-27.backend.spec.ts. Each page must render its heading without the error
// boundary; where the page has a stable empty state or a safe read-only interaction it is checked.
test.describe("Pages of waves 2 and 3 @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  async function open(page: Page, path: string, heading: string) {
    await uiLogin(page, path);
    await expect(page).toHaveURL(new RegExp(`${path.replace(/\//g, "\\/")}$`));
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
    await expect(page.getByText(/Etwas ist schiefgelaufen|Application error/i)).toHaveCount(0);
  }

  const pages: [string, string, string][] = [
    ["payment run", "/bank/zahllauf", "Zahllauf"],
    ["administration fee", "/buchhaltung/verwalterhonorar", "Verwalterhonorar"],
    ["creditors", "/rechnungen/kreditoren", "Kreditoren"],
    ["recurring invoice plans", "/rechnungen/plaene", "Rechnungspläne"],
    ["bank accounts settings", "/einstellungen/bank", "Bank (finAPI)"],
    ["SEPA overview", "/vertraege/sepa", "SEPA Mandate"],
    ["contact merge", "/kontakte/zusammenfuehrung", "Kontakte zusammenführen"],
    ["privacy admin", "/einstellungen/datenschutz", "Datenschutz"],
    ["rent index", "/vermietung/mietspiegel", "Mietspiegel"],
    ["notification settings", "/einstellungen/benachrichtigungen", "Benachrichtigungen"],
  ];
  for (const [name, path, heading] of pages) {
    test(`${name} page renders @backend`, async ({ page }) => {
      test.setTimeout(90_000);
      await open(page, path, heading);
    });
  }

  test("licensing page renders for a platform admin or says it is forbidden @backend", async ({ page }) => {
    test.setTimeout(90_000);
    await uiLogin(page, "/plattform/lizenzen");
    await expect(page).toHaveURL(/\/plattform\/lizenzen$/);
    const title = page.getByRole("heading", { name: "Lizenzen und Preisliste", level: 1 });
    const forbidden = page.getByRole("alert");
    await expect(title.or(forbidden).first()).toBeVisible();
  });

  test("mail compact view: list loads and a message opens with the compact card if one exists @backend", async ({ page }) => {
    test.setTimeout(90_000);
    await uiLogin(page, "/mail");
    await expect(page).toHaveURL(/\/mail$/);
    await expect(page.getByTestId("mail-filters")).toBeVisible();
    const first = page.locator("a[href^='/mail/']:not([href='/mail/postausgang']):not([href='/mail/playbooks'])").first();
    // No seed endpoint for inbound mail exists (mail only arrives via a connected mailbox).
    test.skip((await first.count()) === 0, "no mail message seeded, compact card not reachable");
    await first.click();
    await expect(page.getByTestId("mail-compact")).toBeVisible();
  });

  test("HOA reserves: page shows the title or the no-ledger notice for a fresh WEG @backend", async ({ page }) => {
    test.setTimeout(90_000);
    const call = api(await apiToken());
    let id = "";
    for (let i = 0; i < 30 && !id; i++) {
      const number = String(Math.floor(Math.random() * 900) + 100);
      try {
        id = (await call<{ id: string }>("POST", "/properties", { number, name: `E2E WEG Rücklagen ${Date.now().toString(36)}`, management_type: "hoa" }, 201)).id;
      } catch (e) {
        if (!String(e).includes(": 409 ")) throw e;
      }
    }
    expect(id).not.toBe("");
    await uiLogin(page, `/weg/${id}/ruecklagen`);
    await expect(page).toHaveURL(/\/ruecklagen$/);
    const title = page.getByRole("heading", { name: "Rücklagen", level: 1 });
    const noLedger = page.getByText("Für dieses Objekt ist kein Buchungskreis der Gemeinschaft angelegt.");
    await expect(title.or(noLedger).first()).toBeVisible();
  });
});
