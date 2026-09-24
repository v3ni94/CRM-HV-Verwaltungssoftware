import { expect, test } from "@playwright/test";

import { api, apiToken, uiLogin } from "./auth";

// Letting, incoming invoice and owners' meeting against a real API (E2E_BACKEND=1). Four eyes
// locks must hold: the seeded admin is the only user and cannot approve its own work.
test.describe("workflows against the API @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("rent increase, invoice review, meeting vote and announcement @backend", async ({ page }) => {
    test.setTimeout(240_000);
    const call = api(await apiToken());
    const run = Date.now().toString(36);
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
      return { contact: c.id, party: (await call<{ id: string }>("POST", "/parties", { members: [{ contact_id: c.id }] }, 201)).id };
    };

    // Rental unit, 60 m², rent 600,00.
    const prop = await property<{ id: string }>(`E2E Vermietung ${run}`, "rental");
    await call("POST", `/properties/${prop.id}/owners`, { party_id: (await party("Vermieter")).party, valid_from: "2020-01-01" }, 201);
    const building = (await call<{ id: string }>("POST", `/properties/${prop.id}/buildings`, { name: "Haus" }, 201)).id;
    const unit = (await call<{ id: string }>("POST", `/properties/${prop.id}/units`, { building_id: building, number: "01", unit_type: "apartment", living_area_sqm: "60" }, 201)).id;
    const contract = await call<{ id: string; number: string }>("POST", "/contracts", { kind: "tenancy", unit_id: unit, party_id: (await party("Mieter")).party, start_date: "2023-01-01" }, 201);
    await call("POST", `/contracts/${contract.id}/payments`, { payment_type_code: "rent", net: "600.00", gross: "600.00", valid_from: "2023-01-01" }, 201);

    // HOA with two owners for the meeting and an invoice ledger.
    const hoaProp = await property<{ id: string; legal_entities: { id: string; kind: string }[] }>(`E2E Versammlung ${run}`, "hoa");
    const hoa = hoaProp.legal_entities.find((e) => e.kind === "hoa")!.id;
    const hb = (await call<{ id: string }>("POST", `/properties/${hoaProp.id}/buildings`, { name: "Haus" }, 201)).id;
    for (const no of ["01", "02"]) {
      const u = (await call<{ id: string }>("POST", `/properties/${hoaProp.id}/units`, { building_id: hb, number: no, unit_type: "apartment" }, 201)).id;
      await call("POST", "/contracts", { kind: "ownership", unit_id: u, party_id: (await party(`Eigentuemer${no}`)).party, start_date: "2020-01-01", title_transfer_date: "2020-01-01", acquisition_kind: "first_acquisition" }, 201);
    }
    const template = await call<{ id: string }>("POST", "/accounting/templates/default", undefined, 201);
    const hoaLedger = (await call<{ id: string }>("POST", "/accounting/ledgers", { legal_entity_id: hoa, template_id: template.id }, 201)).id;
    await party("Dachdecker");
    const meeting = await call<{ id: string }>("POST", "/hoa/meetings", { legal_entity_id: hoa, scheduled_at: "2026-11-20T10:00:00+01:00" }, 201);
    await call("POST", `/hoa/meetings/${meeting.id}/agenda`, { title: "Dachrinne erneuern", proposal: "Die Dachrinne wird erneuert." }, 201);
    await call("POST", `/hoa/meetings/${meeting.id}/invite`, { invited_at: "2026-10-20" });

    // 1. Rent increase: arithmetic check, then the creator cannot approve.
    await uiLogin(page, "/vermietung");
    await expect(page.getByRole("heading", { name: "Vermietung", level: 1 })).toBeVisible();
    await page.getByLabel("Mietvertrag").selectOption(contract.id);
    await page.getByLabel("Zielmiete netto").fill("690,00");
    await page.getByLabel("Wirksam ab").fill("2026-12-01");
    await page.getByLabel("Ausgangsmiete (Kappung)").fill("600,00");
    await page.getByLabel("Kappungsgrenze in %").fill("15");
    await page.getByLabel("Vergleichsmiete je m²").fill("11,50");
    await page.getByLabel("Quelle der Werte").fill("Testwerte ohne Rechtsquelle");
    await page.getByRole("button", { name: "Anlegen und rechnerisch prüfen" }).click();
    await expect(page).toHaveURL(/\/vermietung\/mieterhoehung\/[0-9a-f-]{36}$/);
    await expect(page.getByText("Keine rechnerischen Hinweise.")).toBeVisible();
    await expect(page.getByText(/15,00 %/)).toBeVisible();
    await page.getByRole("button", { name: "Freigeben (zweite Person)" }).click();
    await expect(page.getByRole("alert")).toBeVisible();

    // 2. Incoming invoice: hints, three review steps, release refused for the creator.
    await page.goto("/rechnungen");
    await page.getByLabel("Buchungskreis").selectOption(hoaLedger);
    await page.getByLabel("Aussteller suchen").fill(`Dachdecker ${run}`);
    await page.locator("main").getByRole("button", { name: "Suchen" }).click();
    await page.getByRole("combobox", { name: "Aussteller", exact: true }).selectOption({ label: `Dachdecker ${run} GmbH` });
    await page.getByLabel("Rechnungsnummer").fill(`D-${run}`);
    await page.getByLabel("Rechnungsdatum").fill("2026-09-01");
    await page.getByLabel("Leistung ab").fill("2026-08-01");
    await page.getByLabel("Netto").fill("1000");
    await page.getByLabel("Kostenkonto").selectOption({ index: 1 });
    await expect(page.getByTestId("gross")).toContainText("1190,00");
    await page.getByRole("button", { name: "Rechnung erfassen" }).click();
    await expect(page).toHaveURL(/\/rechnungen\/[0-9a-f-]{36}$/);
    await expect(page.getByTestId("findings")).toContainText("Originalbeleg fehlt");
    for (const step of ["Vollständigkeit", "sachliche Prüfung", "rechnerische und steuerliche Prüfung"]) {
      await page.getByLabel("Prüfschritt").selectOption({ label: step });
      await page.getByLabel("Begründung").fill(`${step} geprüft`);
      await page.getByRole("button", { name: "Prüfschritt erfassen" }).click();
      await expect(page.getByText(`${step} geprüft`)).toBeVisible();
    }
    await expect(page.getByText(/ohne Beanstandung abgeschlossen/).first()).toBeVisible();
    await page.getByRole("button", { name: "Rechnung freigeben (zweite Person)" }).click();
    await expect(page.getByRole("alert")).toBeVisible();

    // 3. Meeting: attendance, votes, tally 2 : 0 (head principle), announcement.
    await page.goto(`/weg/${hoaProp.id}/versammlung/${meeting.id}`);
    for (const no of ["01", "02"]) {
      const row = page.getByRole("row", { name: new RegExp(`^${no} `) });
      await row.getByRole("button", { name: "anwesend" }).click();
      await expect(row.getByText("anwesend")).toBeVisible();
    }
    for (const no of ["01", "02"]) {
      await page.getByRole("button", { name: `${no} TOP 1 Ja` }).click();
      await expect(page.getByRole("row", { name: new RegExp(`^${no} `) }).getByText("Ja", { exact: true })).toBeVisible();
    }
    await page.getByRole("button", { name: "Auszählen" }).click();
    await expect(page.getByText("Ja 2 · Nein 0 · Enthaltung 0")).toBeVisible();
    page.once("dialog", (d) => void d.accept());
    await page.getByRole("button", { name: "Verkünden: angenommen" }).click();
    await expect(page.getByText(/Beschluss Nr\. \d+: angenommen/)).toBeVisible();
  });
});
