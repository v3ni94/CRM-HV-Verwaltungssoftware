import { expect, test, type Page } from "@playwright/test";

import { adminToken, api, apiBase, invitePortalUser } from "./auth";
import { expectCoarsePointer, expectNoHorizontalOverflow, expectTouchTarget } from "./mobile-layout";

// Portal core paths on phone width (GAJ-403, section 14 mobile first): damage report with a
// photo, meter reading, provider work order (quote, execution photos, invoice) and documents.
// Runs only with E2E_BACKEND=1 in the projects phone, tablet and tablet-landscape (@mobile).
// Each test builds its own world through the API with a run suffix; nothing is booked or paid,
// the invoice and the meter reading stay proposals for the management.

const PNG_1X1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);
// Minimal PDF for quote and invoice attachments.
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n");

type Call = ReturnType<typeof api>;

/** Rental property with one unit, a tenancy and an invited tenant portal account. */
async function world(call: Call, run: string) {
  let property: { id: string } | undefined;
  for (let i = 0; i < 30 && !property; i++) {
    const number = String(Math.floor(Math.random() * 900) + 100);
    try {
      property = await call<{ id: string }>("POST", "/properties", { number, name: `E2E Mobil ${run}`, management_type: "rental" }, 201);
    } catch (e) {
      if (!String(e).includes(": 409 ")) throw e;
    }
  }
  const pid = property!.id;
  const owner = await call<{ id: string }>("POST", "/contacts", { kind: "company", company_name: `Vermieter Mobil ${run} GmbH` }, 201);
  const ownerParty = (await call<{ id: string }>("POST", "/parties", { members: [{ contact_id: owner.id }] }, 201)).id;
  await call("POST", `/properties/${pid}/owners`, { party_id: ownerParty, valid_from: "2020-01-01" }, 201);
  const building = (await call<{ id: string }>("POST", `/properties/${pid}/buildings`, { name: "Haus" }, 201)).id;
  const unit = (await call<{ id: string }>("POST", `/properties/${pid}/units`, { building_id: building, number: "01", unit_type: "apartment" }, 201)).id;
  const tenant = await call<{ id: string }>("POST", "/contacts", { kind: "person", first_name: "Mia", last_name: `Mobil${run}` }, 201);
  const party = (await call<{ id: string }>("POST", "/parties", { members: [{ contact_id: tenant.id }] }, 201)).id;
  const contract = await call<{ id: string }>("POST", "/contracts", { kind: "tenancy", unit_id: unit, party_id: party, start_date: "2023-01-01" }, 201);
  const login = await invitePortalUser(call, tenant.id, `mieter-mobil-${run}`);
  return { pid, unit, contract: contract.id, login };
}

async function signIn(page: Page, login: { email: string; password: string }) {
  await page.goto("/anmelden");
  await page.getByLabel("E-Mail").fill(login.email);
  await page.getByLabel("Passwort").fill(login.password);
  await page.getByRole("button", { name: "Weiter" }).click();
  await expect(page).toHaveURL(/\/start$/);
  await expectCoarsePointer(page);
}

test.describe("Portal core paths on phone width @backend @mobile", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("tenant reports damage with a photo on a phone @backend @mobile", async ({ page }) => {
    test.setTimeout(120_000);
    const call = api(await adminToken());
    const run = Date.now().toString(36);
    const w = await world(call, run);
    await signIn(page, w.login);
    await page.goto("/meldungen");
    await expect(page.getByRole("heading", { name: "Meldungen", level: 1 })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    const title = `Schimmel Schlafzimmer ${run}`;
    await page.getByLabel("Titel").fill(title);
    await page.getByLabel("Beschreibung").fill("An der Außenwand im Schlafzimmer bildet sich Schimmel, siehe Foto.");
    await page.getByLabel(/Fotos anhängen/).setInputFiles({ name: `schimmel-${run}.png`, mimeType: "image/png", buffer: PNG_1X1 });
    const submit = page.getByRole("button", { name: "Melden", exact: true });
    await expectTouchTarget(submit);
    const upload = page.waitForResponse((r) => r.url().endsWith("/api/bff/portal/uploads") && r.request().method() === "POST");
    await submit.click();
    expect((await upload).status()).toBe(201);
    await expect(page.getByText("Meldung wurde übermittelt.")).toBeVisible();
    await expectNoHorizontalOverflow(page);

    await page.getByRole("link", { name: new RegExp(title) }).click();
    await expect(page).toHaveURL(/\/meldungen\/[0-9a-f-]{36}$/);
    await expect(page.getByRole("list", { name: "Anhänge der Meldung" }).getByText(`schimmel-${run}.png`)).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test("tenant reports a meter reading on a phone @backend @mobile", async ({ page }) => {
    test.setTimeout(120_000);
    const call = api(await adminToken());
    const run = Date.now().toString(36);
    const w = await world(call, run);
    const meter = await call<{ id: string }>(
      "POST",
      `/properties/${w.pid}/meters`,
      { unit_id: w.unit, meter_type_code: "cold_water", number: `KW-${run}`, valid_from: "2023-01-01" },
      201,
    );
    await signIn(page, w.login);
    await page.goto("/zaehlerstand");
    await expect(page.getByRole("heading", { name: "Zählerstand melden", level: 1 })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    // Validation first: a meter without value is rejected on the client.
    const meterField = page.getByLabel("Zähler-ID");
    if ((await meterField.evaluate((el) => el.tagName.toLowerCase())) === "select") {
      await meterField.selectOption(meter.id);
    } else {
      await meterField.fill(meter.id);
    }
    const submit = page.getByRole("button", { name: "Melden", exact: true });
    await expectTouchTarget(submit);
    await submit.click();
    await expect(page.getByText("Bitte einen Zählerstand eingeben.")).toBeVisible();

    await page.getByLabel("Zählerstand", { exact: true }).fill("1234,5");
    await page.getByLabel("Ablesedatum").fill("2026-09-30");
    // The photo field is added in parallel (AM06); attach a photo only when the form has one.
    const photo = page.locator("form input[type=file]:not([capture])").first();
    if ((await photo.count()) > 0) {
      await photo.setInputFiles({ name: `zaehler-${run}.png`, mimeType: "image/png", buffer: PNG_1X1 });
    }
    const sent = page.waitForResponse((r) => r.url().endsWith("/api/bff/portal/meter-readings") && r.request().method() === "POST");
    await submit.click();
    expect((await sent).status()).toBe(201);
    await expect(page.getByText("Der Zählerstand wurde als Vorschlag übermittelt.")).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test("provider handles a work order with quote, photos and invoice on a phone @backend @mobile", async ({ page }) => {
    test.setTimeout(150_000);
    const call = api(await adminToken());
    const run = Date.now().toString(36);
    const w = await world(call, run);
    const provider = await call<{ id: string }>("POST", "/contacts", { kind: "company", company_name: `Sanitär Mobil ${run} GmbH` }, 201);
    const login = await invitePortalUser(call, provider.id, `dienstleister-mobil-${run}`);
    const description = `Wasserhahn Küche tauschen ${run}`;
    const order = await call<{ id: string }>("POST", "/work-orders", { property_id: w.pid, provider_contact_id: provider.id, description }, 201);
    await call("POST", `/work-orders/${order.id}/steps`, { status: "requested" });

    await signIn(page, login);
    await page.goto("/auftraege");
    await expectNoHorizontalOverflow(page);
    const link = page.getByRole("link", { name: new RegExp(description) });
    await expectTouchTarget(link);
    await link.click();
    await expect(page).toHaveURL(new RegExp(`/auftraege/${order.id}$`));
    await expectNoHorizontalOverflow(page);

    // Quote with a file.
    const quote = page.getByRole("form", { name: "Angebot abgeben" });
    await quote.getByLabel("Angebotsbetrag (EUR)").fill("245,90");
    await quote.getByLabel("Angebot als Datei anhängen (optional)").setInputFiles({ name: `angebot-${run}.pdf`, mimeType: "application/pdf", buffer: PDF });
    await quote.getByRole("button", { name: "Angebot abgeben" }).click();
    await expect(page.getByText("Das Angebot wurde übermittelt.")).toBeVisible();

    // The management approves the quote and schedules the order; the provider documents the execution with a photo.
    await call("POST", `/work-orders/${order.id}/steps`, { status: "approved" });
    await call("POST", `/work-orders/${order.id}/steps`, { status: "scheduled", scheduled_at: "2026-10-06T08:00:00Z" });
    await page.reload();
    const complete = page.getByRole("form", { name: "Ausführung dokumentieren" });
    // Camera input (GAJ-404) only checked where the build already contains it.
    const camera = complete.getByTestId("photos-camera");
    if ((await camera.count()) > 0) await expect(camera).toHaveAttribute("capture", "environment");
    await complete.getByLabel("Ausführungsbericht").fill("Wasserhahn getauscht, Dichtheit geprüft.");
    await complete.locator("#photos").setInputFiles({ name: `ausfuehrung-${run}.png`, mimeType: "image/png", buffer: PNG_1X1 });
    await complete.getByRole("button", { name: "Ausführung dokumentieren" }).click();
    await expect(page.getByText("Die Ausführung wurde dokumentiert.")).toBeVisible();
    await expect(page.getByText(new RegExp(`ausfuehrung-${run}\\.png`))).toBeVisible();

    // Invoice as proposal for review (no booking, no payment).
    const invoice = page.getByRole("form", { name: "Rechnung einreichen" });
    await invoice.getByLabel("Rechnungsnummer").fill(`RE-${run}`);
    await invoice.getByLabel("Rechnungsdatum").fill("2026-10-02");
    await invoice.getByLabel("Rechnungsbetrag brutto (EUR)").fill("245,90");
    await invoice.getByLabel("Rechnung als Datei anhängen").setInputFiles({ name: `rechnung-${run}.pdf`, mimeType: "application/pdf", buffer: PDF });
    await invoice.getByRole("button", { name: "Rechnung einreichen" }).click();
    await expect(page.getByText("Die Rechnung wurde als Vorschlag zur Prüfung eingereicht.")).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  test("tenant finds, selects and downloads documents on a phone @backend @mobile", async ({ page }) => {
    test.setTimeout(120_000);
    const token = await adminToken();
    const call = api(token);
    const run = Date.now().toString(36);
    const w = await world(call, run);
    const titles: [string, string] = [`Hausordnung ${run}`, `Mietvertrag Nachtrag ${run}`];
    for (const title of titles) {
      const form = new FormData();
      form.append("title", title);
      form.append("links", JSON.stringify([{ entity_type: "contract", entity_id: w.contract }]));
      form.append("file", new Blob([title], { type: "text/plain" }), `${title}.txt`);
      const res = await fetch(`${apiBase}/api/v1/documents`, { method: "POST", headers: { authorization: `Bearer ${token}` }, body: form });
      expect(res.status, await res.clone().text()).toBe(201);
      const doc = (await res.json()) as { id: string };
      await call("PATCH", `/documents/${doc.id}`, { visibility: ["tenant"] });
    }

    await signIn(page, w.login);
    await page.goto("/dokumente");
    await expect(page.getByRole("heading", { name: "Dokumente", level: 1 })).toBeVisible();
    for (const title of titles) await expect(page.getByText(title)).toBeVisible();
    await expectNoHorizontalOverflow(page);

    // Search narrows the list inside the visible documents.
    await page.getByRole("search").getByRole("searchbox").fill("Hausordnung");
    await page.getByRole("button", { name: "Anwenden" }).click();
    await expect(page.getByText(titles[0])).toBeVisible();
    await expect(page.getByText(titles[1])).toHaveCount(0);

    // Single download through the portal file proxy.
    const single = page.getByRole("link", { name: "Herunterladen" }).first();
    await expectTouchTarget(single);
    const [file] = await Promise.all([page.waitForEvent("download"), single.click()]);
    expect(file.suggestedFilename()).toContain("Hausordnung");

    // Bundle download of all documents.
    await page.goto("/dokumente");
    await page.getByRole("button", { name: "Alle auswählen" }).click();
    const bundle = page.getByRole("button", { name: /Sammel-Download \(2 ausgewählt\)/ });
    await expectTouchTarget(bundle);
    const [zip] = await Promise.all([page.waitForEvent("download"), bundle.click()]);
    expect(zip.suggestedFilename()).toMatch(/\.zip$/);
    await expectNoHorizontalOverflow(page);
  });
});
