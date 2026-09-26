import { expect, test } from "@playwright/test";

import { api, apiToken, uiLogin } from "./auth";

// Money paths against a real API (E2E_BACKEND=1). Master data comes from the API; the steps
// run through the screens. Release gates stay closed: the test checks that locks hold.
test.describe("money paths against the API @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("receivables, open items, dunning lock, operating cost statement, HOA plan @backend", async ({ page }) => {
    test.setTimeout(240_000);
    const call = api(await apiToken());
    const run = Date.now().toString(36);
    // Property numbers are NNN and unique per tenant; repeated runs pick a free one.
    const property = async <T,>(name: string, management_type: string): Promise<T> => {
      for (let i = 0; i < 30; i++) {
        const number = String(Math.floor(Math.random() * 900) + 100);
        try {
          return await call<T>("POST", "/properties", { number, name, management_type }, 201);
        } catch (e) {
          if (!String(e).includes(": 409 ")) throw e;
        }
      }
      throw new Error("no free property number");
    };
    const party = async (name: string) => {
      const c = await call<{ id: string }>("POST", "/contacts", { kind: "company", company_name: `${name} ${run} GmbH` }, 201);
      return (await call<{ id: string }>("POST", "/parties", { members: [{ contact_id: c.id }] }, 201)).id;
    };

    // Rental property with one let unit, rent 500,00 from 01.01.2024, due on the 3rd.
    const prop = await property<{ id: string }>(`E2E Miete ${run}`, "rental");
    const owner = await party("Vermieter");
    const entity = (await call<{ legal_entity_id: string }>("POST", `/properties/${prop.id}/owners`, { party_id: owner, valid_from: "2020-01-01" }, 201)).legal_entity_id;
    const keys = await call<{ id: string; code: string }[]>("GET", `/properties/${prop.id}/allocation-keys`);
    const wfl = keys.find((k) => k.code === "WFL")!.id;
    const building = (await call<{ id: string }>("POST", `/properties/${prop.id}/buildings`, { name: "Haus" }, 201)).id;
    const unit = (await call<{ id: string }>("POST", `/properties/${prop.id}/units`, { building_id: building, number: "01", unit_type: "apartment", living_area_sqm: "60" }, 201)).id;
    await call("POST", `/units/${unit}/allocation-values`, { allocation_key_id: wfl, value: "60", valid_from: "2020-01-01" }, 201);
    const contract = await call<{ id: string }>("POST", "/contracts", { kind: "tenancy", unit_id: unit, party_id: await party("Mieter"), start_date: "2024-01-01" }, 201);
    await call("POST", `/contracts/${contract.id}/payments`, { payment_type_code: "rent", net: "500.00", gross: "500.00", valid_from: "2024-01-01" }, 201);
    await call("POST", `/contracts/${contract.id}/schedules`, { valid_from: "2024-01-01", due_day: 3 }, 201);
    const template = await call<{ id: string }>("POST", "/accounting/templates/default", undefined, 201);
    const ledger = (await call<{ id: string }>("POST", "/accounting/ledgers", { legal_entity_id: entity, template_id: template.id }, 201)).id;
    const revenue = (await call<{ id: string }>("POST", `/accounting/ledgers/${ledger}/accounts`, { number: "061000", name: "Mieteinnahmen", category: "revenue", type: "income" }, 201)).id;
    await call("PUT", `/accounting/ledgers/${ledger}/payment-type-accounts`, { payment_type_code: "rent", account_id: revenue });
    // Tenant default first (the API refuses a property override without it), then the object.
    await call("PUT", "/accounting/dunning-settings", {
      levels: [{ level: 1, min_days_overdue: 14, text: "Zahlungserinnerung" }],
    });
    await call("PUT", "/accounting/dunning-settings", {
      property_id: prop.id,
      levels: [{ level: 1, min_days_overdue: 14, text: "Zahlungserinnerung" }],
    });

    // 1. Receivable run: preview, confirm, post.
    await uiLogin(page, "/buchhaltung/sollstellungen");
    await expect(page.getByRole("heading", { name: "Sollstellungen", level: 1 })).toBeVisible();
    await page.getByLabel("Monat").fill("2026-01");
    await page.getByRole("button", { name: "Vorschau erstellen" }).click();
    await expect(page.getByTestId("run-status")).toContainText("Vorschau");
    page.once("dialog", (d) => void d.accept());
    await page.getByRole("button", { name: /Sollstellungen buchen/ }).click();
    await expect(page.getByTestId("run-status")).toContainText("gebucht");

    // 2. Open items of the ledger: 500,00 due on 03.01.2026.
    await page.goto(`/buchhaltung/${ledger}`);
    await expect(page.getByTestId("open-total")).toContainText("500,00");

    // 3. Dunning: preview only; the ledger is not leading, so nothing can be approved.
    await page.goto("/buchhaltung/mahnwesen");
    await page.getByLabel("Stichtag").fill("2026-03-01");
    await page.getByRole("button", { name: "Vorschau erstellen" }).click();
    await expect(page).toHaveURL(/\/buchhaltung\/mahnwesen\/[0-9a-f-]{36}$/);
    await expect(page.getByText(/nicht führend/).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Mahnlauf freigeben" })).toHaveCount(0);

    // 4. Operating cost statement: caretaker 1.200,00 by living area, one unit let all year.
    await page.goto("/abrechnung");
    await page.getByLabel("Buchungskreis").selectOption(ledger);
    await page.getByLabel("Von").fill("2026-01-01");
    await page.getByLabel("Bis").fill("2026-12-31");
    await page.getByRole("button", { name: "Abrechnung anlegen" }).click();
    await expect(page).toHaveURL(/\/abrechnung\/[0-9a-f-]{36}$/);
    await page.getByLabel("Bezeichnung").fill("Hausmeister");
    await page.getByLabel("Betrag").fill("1200,00");
    await page.getByLabel("Umlageschlüssel").selectOption(wfl);
    await page.getByLabel("Grundlage").fill("Mietvertrag Anlage Betriebskosten");
    await page.getByRole("button", { name: "Position hinzufügen" }).click();
    await expect(page.getByRole("cell", { name: "Hausmeister" })).toBeVisible();
    await page.getByRole("button", { name: "Berechnen" }).click();
    await expect(page.getByRole("heading", { name: "Ergebnis je Einheit" })).toBeVisible();
    await expect(page.getByRole("cell", { name: /1\.200,00/ }).first()).toBeVisible();
    // Four eyes: the creator cannot approve internally.
    await page.getByRole("button", { name: "Intern freigeben" }).click();
    await expect(page.getByRole("alert")).toBeVisible();

    // 5. HOA economic plan: 1.200,00 by MEA on one unit -> 100,00 per month.
    const hoaProp = await property<{ id: string; legal_entities: { id: string; kind: string }[] }>(`E2E WEG ${run}`, "hoa");
    const hoa = hoaProp.legal_entities.find((e) => e.kind === "hoa")!.id;
    const hoaKeys = await call<{ id: string; code: string }[]>("GET", `/properties/${hoaProp.id}/allocation-keys`);
    const mea = hoaKeys.find((k) => k.code === "MEA")!.id;
    const hb = (await call<{ id: string }>("POST", `/properties/${hoaProp.id}/buildings`, { name: "Haus" }, 201)).id;
    const hu = (await call<{ id: string }>("POST", `/properties/${hoaProp.id}/units`, { building_id: hb, number: "01", unit_type: "apartment" }, 201)).id;
    await call("POST", `/units/${hu}/allocation-values`, { allocation_key_id: mea, value: "1000", valid_from: "2020-01-01" }, 201);
    await call("POST", "/accounting/ledgers", { legal_entity_id: hoa, template_id: template.id }, 201);
    await page.goto(`/weg/${hoaProp.id}`);
    await page.getByLabel("Jahr").first().fill("2027");
    await page.getByRole("button", { name: "Plan anlegen" }).click();
    await expect(page).toHaveURL(/\/plan\/[0-9a-f-]{36}$/);
    await page.getByLabel("Bezeichnung").fill("Bewirtschaftung");
    await page.getByLabel("Betrag").fill("1200");
    await page.getByLabel("Schlüssel").selectOption(mea);
    await page.getByRole("button", { name: "Position hinzufügen" }).click();
    await expect(page.getByRole("cell", { name: "Bewirtschaftung" })).toBeVisible();
    await page.getByRole("button", { name: "Berechnen" }).click();
    await expect(page.getByRole("cell", { name: /100,00/ }).first()).toBeVisible();
  });
});
