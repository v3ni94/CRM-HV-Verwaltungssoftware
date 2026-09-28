import { execFileSync } from "node:child_process";

import { expect, test, type Page } from "@playwright/test";
import * as OTPAuth from "otpauth";

import { TENANT, api, apiBase, apiToken, uiLogin } from "./auth";

// Core paths of the CRM versions 1.37.0 to 1.40.0 against a real API (E2E_BACKEND=1, see
// scripts/e2e-backend.sh): day and evening mode in the user menu, To/Cc lines and reply to all
// for a user with TOTP enabled (production 500 fixed in 1.38.0), rule proposals of the learning
// workflow (rule M9-11), follow-up ticket instead of reopening (rule M19-10) and the contact
// links of the units tab. Pattern and shared admin login: core-paths.backend.spec.ts.
//
// Inbound mails are created like the API tests do: .eml upload (POST /documents) and
// POST /mail/ingest. That needs the object store (scripts/e2e-backend.sh starts a moto server);
// without one the upload answers MHVP-DOC-0007 and the mail tests are skipped with a reason.

type Call = ReturnType<typeof api>;

const run = Date.now().toString(36);
let counter = 0;

function rfc2822(date: Date): string {
  return date.toUTCString().replace("GMT", "+0000");
}

type Eml = {
  from: string;
  to: string[];
  cc?: string[];
  subject: string;
  messageId: string;
  inReplyTo?: string;
  body?: string;
};

function eml(m: Eml): string {
  const headers = [
    `From: ${m.from}`,
    `To: ${m.to.join(", ")}`,
    ...(m.cc && m.cc.length ? [`Cc: ${m.cc.join(", ")}`] : []),
    `Subject: ${m.subject}`,
    `Message-ID: ${m.messageId}`,
    ...(m.inReplyTo ? [`In-Reply-To: ${m.inReplyTo}`, `References: ${m.inReplyTo}`] : []),
    `Date: ${rfc2822(new Date())}`,
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=utf-8",
    "Content-Transfer-Encoding: 8bit",
  ];
  return `${headers.join("\r\n")}\r\n\r\n${m.body ?? "Guten Tag, bitte um Rueckmeldung."}\r\n`;
}

/** Uploads the .eml as a document; null when the object store is not available (503). */
async function uploadEml(token: string, raw: string): Promise<string | null> {
  const form = new FormData();
  counter += 1;
  form.append("file", new Blob([raw], { type: "message/rfc822" }), `e2e-${run}-${counter}.eml`);
  const res = await fetch(`${apiBase}/api/v1/documents`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}` },
    body: form,
  });
  const text = await res.text();
  if (res.status === 503 && text.includes("MHVP-DOC-0007")) return null;
  if (res.status !== 201) throw new Error(`POST /documents: ${res.status} ${text}`);
  return (JSON.parse(text) as { id: string }).id;
}

type Ingested = { id: string; ticket_id: string | null };

async function ingest(
  token: string,
  raw: string,
  extra: { mailbox_id?: string; auto_ticket?: boolean } = {},
): Promise<Ingested | null> {
  const doc = await uploadEml(token, raw);
  if (doc === null) return null;
  return api(token)<Ingested>("POST", "/mail/ingest", { document_id: doc, ...extra }, 201);
}

async function mailbox(call: Call, address: string): Promise<{ id: string; address: string }> {
  return call("POST", "/mail/mailboxes", { address, secret: "e2e-geheim" }, 201);
}

async function freshProperty(call: Call, name: string, management_type: "hoa" | "hoa_with_sev" | "rental") {
  for (let i = 0; i < 30; i++) {
    const number = String(Math.floor(Math.random() * 900) + 100);
    try {
      return await call<{ id: string }>("POST", "/properties", { number, name, management_type }, 201);
    } catch (e) {
      if (!String(e).includes(": 409 ")) throw e;
    }
  }
  throw new Error("no free property number");
}

async function person(call: Call, first: string, last: string) {
  return call<{ id: string; display_name: string }>("POST", "/contacts", { kind: "person", first_name: first, last_name: last }, 201);
}

/** Direct SQL through the app role inside the tenant scope (RLS), like the API tests'
 *  ``_backdate``: the API never lets a user set ``resolved_at``. */
function tenantSql(tenantId: string, sql: string): void {
  const url = (process.env.MHVP_DATABASE_URL ?? "").replace("postgresql+psycopg://", "postgresql://");
  if (!url) throw new Error("MHVP_DATABASE_URL is required to backdate a ticket");
  execFileSync(
    "psql",
    [url, "-v", "ON_ERROR_STOP=1", "-Atc", `BEGIN; SELECT set_config('app.tenant_id', '${tenantId}', true); ${sql}; COMMIT;`],
    { stdio: "pipe" },
  );
}

const TOTP_PERIOD_MS = 30_000;

/** TOTP code of a time step later than ``lastStep`` (the API rejects a reused step). */
async function freshCode(secret: string, lastStep: number): Promise<{ code: string; step: number }> {
  let step = Math.floor(Date.now() / TOTP_PERIOD_MS);
  if (step <= lastStep) {
    await new Promise((r) => setTimeout(r, (lastStep + 1) * TOTP_PERIOD_MS - Date.now() + 500));
    step = Math.floor(Date.now() / TOTP_PERIOD_MS);
  }
  const totp = new OTPAuth.TOTP({ secret: OTPAuth.Secret.fromBase32(secret), digits: 6, period: 30 });
  return { code: totp.generate(), step };
}

/** New tenant administrator with the second factor (TOTP) enabled; returns the credentials,
 *  the secret and the last used time step. */
async function totpAdmin(call: Call): Promise<{ email: string; password: string; secret: string; lastStep: number }> {
  const email = `e2e-totp-${run}@example.org`;
  const password = "E2eTotpAdmin!2026";
  await call("POST", "/tenant/members", { email, display_name: `E2E Totp ${run}`, password, role_codes: ["tenant_admin"] }, 201);
  const login = await fetch(`${apiBase}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const issued = (await login.json()) as { status: string; access_token: string };
  expect(issued.status).toBe("ok");
  const own = api(issued.access_token);
  const setup = await own<{ secret: string }>("POST", "/auth/totp/setup");
  const first = await freshCode(setup.secret, 0);
  await own("POST", "/auth/totp/confirm", { code: first.code }, 204);
  return { email, password, secret: setup.secret, lastStep: first.step };
}

async function loginWithTotp(page: Page, user: { email: string; password: string; secret: string; lastStep: number }, target: string) {
  await page.goto(target);
  await expect(page).toHaveURL(/\/anmelden/);
  await page.getByLabel("E-Mail").fill(user.email);
  await page.getByLabel("Passwort").fill(user.password);
  await page.getByRole("button", { name: "Weiter" }).click();
  await expect(page).toHaveURL(/\/anmelden\/zweiter-faktor/);
  const { code, step } = await freshCode(user.secret, user.lastStep);
  user.lastStep = step;
  await page.getByLabel("Code").fill(code);
  await page.getByRole("button", { name: "Bestätigen" }).click();
  await page.waitForURL((url) => !url.pathname.startsWith("/anmelden"));
  if (new URL(page.url()).pathname.startsWith("/mandant")) {
    await page.getByRole("button", { name: TENANT }).click();
  }
}

test.describe("CRM 1.37.0 to 1.40.0 core paths @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("theme: Tag, Abend and Automatisch in the user menu set data-theme and survive a reload @backend", async ({ page }) => {
    test.setTimeout(90_000);
    await uiLogin(page, "/start");
    await expect(page).toHaveURL(/\/start$/);
    const html = page.locator("html");

    // Waits for the server side save: after a reload the app shell applies the stored
    // preference of the account (serverThemeScript), so a reload before the PATCH would race.
    const choose = async (label: "Tag" | "Abend" | "Automatisch", expected: string) => {
      await page.getByRole("button", { name: "Benutzermenü" }).click();
      const group = page.getByRole("radiogroup", { name: "Darstellung" });
      await expect(group).toBeVisible();
      const saved = page.waitForResponse(
        (r) => r.url().includes("/auth/me/preferences") && r.request().method() === "PATCH",
      );
      await group.getByRole("radio", { name: label, exact: true }).click();
      expect((await saved).ok()).toBe(true);
      await expect(group.getByRole("radio", { name: label, exact: true })).toHaveAttribute("aria-checked", "true");
      await expect(html).toHaveAttribute("data-theme", expected);
      await page.keyboard.press("Escape");
      await page.reload();
      await expect(html).toHaveAttribute("data-theme", expected);
      await page.getByRole("button", { name: "Benutzermenü" }).click();
      await expect(
        page.getByRole("radiogroup", { name: "Darstellung" }).getByRole("radio", { name: label, exact: true }),
      ).toHaveAttribute("aria-checked", "true");
      await page.keyboard.press("Escape");
    };

    await choose("Abend", "evening");
    await choose("Tag", "day");
    // Automatisch: evening from 19 to 7 o'clock browser time (lib/theme.ts); the browser hour
    // decides the expected mode (checked right before, a switch at the full hour is ignored).
    const autoMode = await page.evaluate(() => {
      const h = new Date().getHours();
      return h >= 19 || h < 7 ? "evening" : "day";
    });
    await choose("Automatisch", autoMode);
    // Stored per user account, not only in this browser (PATCH through the BFF).
    const me = await api(await apiToken())<{ ui_preferences: { theme?: string } }>("GET", "/auth/me");
    expect(me.ui_preferences.theme).toBe("auto");

    // Automatisch follows the clock: a fixed evening and a fixed day time after a reload.
    const today = new Date();
    await page.clock.setFixedTime(new Date(today.getFullYear(), today.getMonth(), today.getDate(), 21, 0, 0));
    await page.reload();
    await expect(html).toHaveAttribute("data-theme", "evening");
    await page.clock.setFixedTime(new Date(today.getFullYear(), today.getMonth(), today.getDate(), 10, 0, 0));
    await page.reload();
    await expect(html).toHaveAttribute("data-theme", "day");
  });

  test("mail: An and Kopie lines, Antworten creates a reply-all draft for a TOTP user @backend", async ({ page }) => {
    test.setTimeout(150_000);
    const token = await apiToken();
    const call = api(token);
    const box = await mailbox(call, `info-e2e-${run}@example.com`);
    const sender = `mieterin-${run}@example.org`;
    const neighbour = `nachbar-${run}@example.org`;
    const board = `beirat-${run}@example.org`;
    const subject = `E2E Antworten an alle ${run}`;
    const msg = await ingest(
      token,
      eml({
        from: `Mieterin <${sender}>`,
        to: [box.address, neighbour],
        cc: [board, box.address],
        subject,
        messageId: `<e2e-reply-${run}@example.org>`,
      }),
      { mailbox_id: box.id },
    );
    test.skip(msg === null, "object store not available (MHVP-DOC-0007): no inbound mail can be ingested");

    // Production 500 of 1.37.0: Antworten failed for users with TOTP enabled (fixed in 1.38.0).
    // The seeded admin has no second factor (TOTP is optional, M2-01), so a second tenant
    // administrator with TOTP enabled answers here.
    const user = await totpAdmin(call);
    await loginWithTotp(page, user, `/mail?message=${msg!.id}`);
    await expect(page).toHaveURL(new RegExp(`/mail\\?message=${msg!.id}`));
    await expect(page.getByRole("heading", { name: subject })).toBeVisible({ timeout: 15_000 });

    // Von, An and Kopie each on a line of their own; the own mailbox is marked.
    const line = (label: string, address: string) =>
      page
        .locator("p")
        .filter({ has: page.locator("span", { hasText: new RegExp(`^\\s*${label}\\s*$`) }) })
        .filter({ hasText: address })
        .first();
    await expect(line("Von", sender)).toBeVisible();
    const toLine = line("An", neighbour);
    const ccLine = line("Kopie", board);
    await expect(toLine).toContainText(box.address);
    await expect(toLine).toContainText(neighbour);
    await expect(toLine).toContainText("eigenes Postfach");
    await expect(ccLine).toContainText(board);

    await page.getByRole("button", { name: "Antworten", exact: true }).first().click();
    const draft = page.getByTestId("mail-reply-draft");
    await expect(draft).toBeVisible({ timeout: 15_000 });
    await expect(draft.getByRole("heading", { name: "Antwortentwurf" })).toBeVisible();
    await expect(draft.getByTestId("mail-draft-editor")).toBeVisible();
    // Reply to all: the sender in An, the other recipients in Kopie, never the own mailbox.
    await expect(draft.getByLabel("An (kommagetrennt)")).toHaveValue(sender);
    await expect(draft.getByLabel("Kopie (Cc, kommagetrennt)")).toHaveValue(`${neighbour}, ${board}`);
    await expect(draft.getByLabel("Betreff")).toHaveValue(new RegExp(subject));
    await expect(page.getByText("Interner Fehler")).toHaveCount(0);
    // Only alerts with text: Next.js keeps an empty route announcer with role alert.
    await expect(page.getByRole("alert").filter({ hasText: /\S/ })).toHaveCount(0);
  });

  test("rule proposals: page, accept and reject after five manual decisions, threshold save @backend", async ({ page }) => {
    test.setTimeout(180_000);
    const token = await apiToken();
    const call = api(token);
    // Five equal manual decisions per sender: the ticket topic set by a member (ticket.topic_changed).
    const senders = [`lern-a-${run}@lern-a-${run}.example.org`, `lern-b-${run}@lern-b-${run}.example.org`];
    for (const sender of senders) {
      for (let i = 0; i < 5; i++) {
        const msg = await ingest(
          token,
          eml({ from: sender, to: ["info@example.com"], subject: `E2E Lernen ${run} ${i}`, messageId: `<e2e-lern-${run}-${sender.slice(5, 6)}-${i}@x>` }),
          { auto_ticket: true },
        );
        test.skip(msg === null, "object store not available (MHVP-DOC-0007): no inbound mail can be ingested");
        expect(msg!.ticket_id).toBeTruthy();
        await call("PATCH", `/tickets/${msg!.ticket_id}`, { topic: "vertrag" });
      }
    }
    type Proposal = { id: string; sender_key: string; field: string; scope: string; evidence_count: number };
    const proposals = await call<Proposal[]>("GET", "/automation/rule-proposals?status=proposed&limit=500");
    for (const sender of senders) {
      const row = proposals.find((p) => p.sender_key === sender && p.field === "topic" && p.scope === "address");
      expect(row, `proposal for ${sender}`).toBeTruthy();
      expect(row!.evidence_count).toBe(5);
    }

    await uiLogin(page, "/einstellungen/regelvorschlaege");
    await expect(page).toHaveURL(/\/einstellungen\/regelvorschlaege$/);
    await expect(page.getByRole("heading", { name: "Regelvorschläge", level: 1 })).toBeVisible();

    const rowA = page.getByTestId("rule-proposal").filter({ hasText: `Absender ${senders[0]}` });
    const rowB = page.getByTestId("rule-proposal").filter({ hasText: `Absender ${senders[1]}` });
    await expect(rowA).toContainText("Ticket: Thema Vertrag");
    await expect(rowA).toContainText("5 gleiche manuelle Entscheidungen ohne Widerspruch (Schwelle 5)");
    await expect(rowB).toBeVisible();

    // Accept: an active rule of the rule engine, the proposal leaves the list.
    await rowA.getByRole("button", { name: "Annehmen und Regel aktivieren" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Regel angelegt und aktiv." })).toBeVisible();
    await expect(page.getByRole("link", { name: "Zur Automatisierung" })).toBeVisible();
    await expect(rowA).toHaveCount(0);

    // Reject with a reason.
    await rowB.getByRole("button", { name: "Ablehnen", exact: true }).click();
    await rowB.getByLabel("Grund der Ablehnung (optional)").fill("E2E: kein fester Zusammenhang");
    await rowB.getByRole("button", { name: "Ablehnung bestätigen" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Vorschlag abgelehnt." })).toBeVisible();
    await expect(rowB).toHaveCount(0);

    const accepted = await call<(Proposal & { rule_id: string | null })[]>("GET", "/automation/rule-proposals?status=accepted&limit=500");
    const acceptedA = accepted.find((p) => p.sender_key === senders[0] && p.field === "topic");
    expect(acceptedA?.rule_id).toBeTruthy();
    const rejected = await call<Proposal[]>("GET", "/automation/rule-proposals?status=rejected&limit=500");
    expect(rejected.some((p) => p.sender_key === senders[1] && p.field === "topic")).toBe(true);

    // Threshold: invalid input is refused, a valid one is saved and shown after a reload;
    // restored to the default afterwards.
    const threshold = page.getByTestId("rule-proposal-threshold");
    await threshold.fill("1");
    await page.getByRole("button", { name: "Schwelle speichern" }).click();
    await expect(page.getByRole("alert").filter({ hasText: "Bitte eine ganze Zahl zwischen 2 und 50 eingeben." })).toBeVisible();
    await threshold.fill("7");
    await page.getByRole("button", { name: "Schwelle speichern" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Schwelle gespeichert." })).toBeVisible();
    await page.reload();
    await expect(page.getByTestId("rule-proposal-threshold")).toHaveValue("7");
    await page.getByTestId("rule-proposal-threshold").fill("5");
    await page.getByRole("button", { name: "Schwelle speichern" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Schwelle gespeichert." })).toBeVisible();
    expect((await call<{ rule_proposal_threshold: number }>("GET", "/tenant/settings")).rule_proposal_threshold).toBe(5);
  });

  test("ticket: a mail to a ticket closed 40 days ago creates a follow-up linked both ways @backend", async ({ page }) => {
    test.setTimeout(120_000);
    const token = await apiToken();
    const call = api(token);
    const me = await call<{ user_id: string; tenant_id: string }>("GET", "/auth/me");
    const settings = await call<{ ticket_reopen_window_days: number }>("GET", "/tenant/settings");
    expect(settings.ticket_reopen_window_days).toBe(30);

    const box = await mailbox(call, `info-folge-${run}@example.com`);
    const sender = `mieter-folge-${run}@example.org`;
    const firstId = `<e2e-folge-1-${run}@example.org>`;
    const first = await ingest(
      token,
      eml({ from: `Mieter <${sender}>`, to: [box.address], subject: `E2E Fenster ${run}`, messageId: firstId }),
      { mailbox_id: box.id },
    );
    test.skip(first === null, "object store not available (MHVP-DOC-0007): no inbound mail can be ingested");
    const old = await call<{ ticket_id: string; number: number }>("POST", `/mail/messages/${first!.id}/ticket`, undefined, 201);
    await call("PATCH", `/tickets/${old.ticket_id}`, {
      assignee_user_id: me.user_id,
      status: "done",
      resolution: { kind: "auskunft_erteilt" },
    });
    // Closed 40 calendar days ago (window 30 days): no API sets resolved_at, so it is backdated
    // in the tenant scope like the API test test_m19_ticket_follow_up.py does.
    tenantSql(me.tenant_id, `UPDATE ticket SET resolved_at = now() - interval '40 days' WHERE id = '${old.ticket_id}'`);

    const reply = await ingest(
      token,
      eml({
        from: `Mieter <${sender}>`,
        to: [box.address],
        subject: `Re: E2E Fenster ${run}`,
        messageId: `<e2e-folge-2-${run}@example.org>`,
        inReplyTo: firstId,
        body: "Das Fenster schliesst wieder nicht.",
      }),
      { mailbox_id: box.id },
    );
    expect(reply!.ticket_id).toBeTruthy();
    expect(reply!.ticket_id).not.toBe(old.ticket_id);
    const oldDetail = await call<{ status: string }>("GET", `/tickets/${old.ticket_id}`);
    expect(oldDetail.status).toBe("done");

    // Follow-up: "Folgevorgang zu Ticket #<old>" links to the predecessor.
    await uiLogin(page, `/tickets/${reply!.ticket_id}`);
    const predecessor = page.getByTestId("ticket-follow-up-of");
    await expect(predecessor).toBeVisible({ timeout: 15_000 });
    await expect(predecessor).toContainText("Folgevorgang zu Ticket");
    const back = predecessor.getByRole("link", { name: new RegExp(`^#${old.number}\\b`) });
    await expect(back).toHaveAttribute("href", `/tickets/${old.ticket_id}`);
    await back.click();

    // Predecessor: "Folgevorgang #<new>" links to the follow-up.
    await expect(page).toHaveURL(new RegExp(`/tickets/${old.ticket_id}$`));
    const successors = page.getByTestId("ticket-follow-ups");
    await expect(successors).toBeVisible();
    await expect(successors).toContainText("Folgevorgang");
    await expect(successors.getByRole("link")).toHaveAttribute("href", `/tickets/${reply!.ticket_id}`);
  });

  test("property units tab: owner and tenant names link to their contacts @backend", async ({ page }) => {
    test.setTimeout(90_000);
    const call = api(await apiToken());
    const prop = await freshProperty(call, `E2E Einheitenlinks ${run}`, "hoa_with_sev");
    const building = (await call<{ id: string }>("POST", `/properties/${prop.id}/buildings`, { name: "Haus" }, 201)).id;
    const unit = (await call<{ id: string }>("POST", `/properties/${prop.id}/units`, { building_id: building, number: "01", unit_type: "apartment" }, 201)).id;
    // WEG with SEV (a pure WEG holds no tenancies; the tenancy needs an ownership with SEV).
    // Two owners in one party: each is linked on its own. One tenant.
    const ownerA = await person(call, "Olga", `Eigentuemerin${run}`);
    const ownerB = await person(call, "Otto", `Eigentuemer${run}`);
    const tenant = await person(call, "Mia", `Mieterin${run}`);
    const owners = await call<{ id: string }>("POST", "/parties", { members: [{ contact_id: ownerA.id }, { contact_id: ownerB.id }] }, 201);
    const tenants = await call<{ id: string }>("POST", "/parties", { members: [{ contact_id: tenant.id }] }, 201);
    await call("POST", "/contracts", { kind: "ownership", unit_id: unit, party_id: owners.id, start_date: "2020-01-01", title_transfer_date: "2020-01-01", acquisition_kind: "first_acquisition", sev_enabled: true }, 201);
    await call("POST", "/contracts", { kind: "tenancy", unit_id: unit, party_id: tenants.id, start_date: "2024-01-01" }, 201);

    await uiLogin(page, `/objekte/${prop.id}`);
    const table = page.getByTestId("units");
    await expect(table).toBeVisible({ timeout: 15_000 });
    const row = table.locator("tbody tr").first();
    for (const c of [ownerA, ownerB, tenant]) {
      await expect(row.getByRole("link", { name: c.display_name, exact: true })).toHaveAttribute("href", `/kontakte/${c.id}`);
    }
    await row.getByRole("link", { name: tenant.display_name, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/kontakte/${tenant.id}$`));
    await expect(page.getByRole("heading", { level: 1 })).toContainText(`Mieterin${run}`);
  });
});
