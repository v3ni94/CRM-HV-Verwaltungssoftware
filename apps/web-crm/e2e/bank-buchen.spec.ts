import { expect, test } from "@playwright/test";

import { api, apiBase, apiToken, uiLogin } from "./auth";

// Core path of the bank work (BK-2, plan M12 step S2) against a real API (E2E_BACKEND=1):
// a HOA with a bank account linked to the ledger, one CAMT.053 statement with an incoming and
// an outgoing transaction, then in the CRM: filter by direction, book the outgoing payment
// against a cost account in the booking dialog, book the incoming payment by taking over the
// unambiguous proposal, and read the reconciliation of the account (B09). Release gates stay
// closed: the ledger is not leading, the postings are comparison postings.
test.describe("bank booking dialog against the API @backend", () => {
  test.skip(process.env.E2E_BACKEND !== "1", "requires E2E_BACKEND=1");

  test("outgoing against cost account, incoming from proposal, reconciliation @backend", async ({ page }) => {
    test.setTimeout(240_000);
    const token = await apiToken();
    const call = api(token);
    const run = Date.now().toString(36);
    const bankIban = "DE02120300000000202051";
    const payerIban = "DE89370400440532013000";

    const property = async <T,>(name: string): Promise<T> => {
      for (let i = 0; i < 30; i++) {
        const number = String(Math.floor(Math.random() * 900) + 100);
        try {
          return await call<T>("POST", "/properties", { number, name, management_type: "hoa" }, 201);
        } catch (e) {
          if (!String(e).includes(": 409 ")) throw e;
        }
      }
      throw new Error("no free property number");
    };
    const prop = await property<{ id: string; legal_entities: { id: string; kind: string }[] }>(`E2E Bank ${run}`);
    const hoa = prop.legal_entities.find((e) => e.kind === "hoa")!.id;
    const bankAccount = await call<{ id: string }>(
      "POST",
      `/properties/${prop.id}/bank-accounts`,
      { legal_entity_id: hoa, kind: "hoa", iban: bankIban, holder: `GdWE E2E ${run}`, valid_from: "2020-01-01" },
      201,
    );
    const contact = await call<{ id: string }>(
      "POST",
      "/contacts",
      { kind: "person", first_name: "Eigen", last_name: `E2E ${run}`, bank_accounts: [{ iban: payerIban, valid_from: "2020-01-01" }] },
      201,
    );
    const party = await call<{ id: string }>("POST", "/parties", { members: [{ contact_id: contact.id }] }, 201);
    const building = await call<{ id: string }>("POST", `/properties/${prop.id}/buildings`, { name: "Haus" }, 201);
    const unit = await call<{ id: string }>("POST", `/properties/${prop.id}/units`, { building_id: building.id, number: "01", unit_type: "apartment" }, 201);
    const contract = await call<{ id: string; number: string; unit_id: string }>(
      "POST",
      "/contracts",
      { kind: "ownership", unit_id: unit.id, party_id: party.id, start_date: "2020-01-01", title_transfer_date: "2020-01-01", acquisition_kind: "first_acquisition" },
      201,
    );
    const template = await call<{ id: string }>("POST", "/accounting/templates/default", undefined, 201);
    const ledger = (await call<{ id: string }>("POST", "/accounting/ledgers", { legal_entity_id: hoa, template_id: template.id }, 201)).id;
    const accounts = await call<{ id: string; number: string; category: string; unit_id: string | null }[]>("GET", `/accounting/ledgers/${ledger}/accounts`);
    await call("POST", `/accounting/ledgers/${ledger}/accounts`, { number: "001210", name: "WEG-Bank", category: "bank", type: "asset", property_bank_account_id: bankAccount.id }, 201);
    await call("POST", `/accounting/ledgers/${ledger}/accounts`, { number: "042000", name: "Hausmeister E2E", category: "cost", type: "expense" }, 201);
    const debtor = accounts.find((a) => a.category === "debtor" && a.unit_id === unit.id)!;
    const revenue = accounts.find((a) => a.number === "060100")!;
    const draft = await call<{ id: string }>(
      "POST",
      `/accounting/ledgers/${ledger}/entries`,
      {
        kind: "receivable",
        booking_date: "2026-01-01",
        text: "Hausgeld Januar",
        contract_id: contract.id,
        lines: [
          { account_id: debtor.id, debit: "250.00" },
          { account_id: revenue.id, credit: "250.00" },
        ],
      },
      201,
    );
    await call("POST", `/accounting/ledgers/${ledger}/entries/${draft.id}/post`);

    // Balance arithmetic of the reconciliation (B09, `mhvp.banking.services.reconcile`): the
    // statement side checks OPBD + movements = CLBD, the ledger side checks CLBD against the
    // posted lines on 001210 up to the closing date. Only the two bank postings of this test
    // land on 001210 (+250,00 and -79,90 = 170,10); an opening balance posting would need the
    // check by a second person (kind opening_balance, four eyes), which the single E2E admin
    // cannot give. The statement therefore opens at 0,00 and closes at 170,10 so that both
    // differences are 0,00.
    const entry = (ref: string, amount: string, ind: "CRDT" | "DBIT", iban: string, purpose: string) => {
      const partyTag = ind === "CRDT" ? "Dbtr" : "Cdtr";
      return `<Ntry><Amt Ccy="EUR">${amount}</Amt><CdtDbtInd>${ind}</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts><BookgDt><Dt>2026-01-05</Dt></BookgDt><ValDt><Dt>2026-01-05</Dt></ValDt><AcctSvcrRef>${ref}</AcctSvcrRef><NtryDtls><TxDtls><Refs><EndToEndId>NOTPROVIDED</EndToEndId></Refs><RltdPties><${partyTag}><Nm>Zahler ${run}</Nm></${partyTag}><${partyTag}Acct><Id><IBAN>${iban}</IBAN></Id></${partyTag}Acct></RltdPties><RmtInf><Ustrd>${purpose}</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>`;
    };
    const camt = `<?xml version="1.0" encoding="UTF-8"?><Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt><GrpHdr><MsgId>M-${run}</MsgId><CreDtTm>2026-02-01T08:00:00</CreDtTm></GrpHdr><Stmt><Id>S-${run}</Id><Acct><Id><IBAN>${bankIban}</IBAN></Id><Ccy>EUR</Ccy></Acct><Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">0.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-01-01</Dt></Dt></Bal><Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">170.10</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-01-31</Dt></Dt></Bal>${entry(`IN-${run}`, "250.00", "CRDT", payerIban, `Hausgeld ${contract.number}`)}${entry(`OUT-${run}`, "79.90", "DBIT", "DE75512108001245126199", `Hausmeister ${run}`)}</Stmt></BkToCstmrStmt></Document>`;
    const form = new FormData();
    form.set("file", new Blob([camt], { type: "application/xml" }), `e2e-${run}.xml`);
    const upload = await fetch(`${apiBase}/api/v1/documents`, { method: "POST", headers: { authorization: `Bearer ${token}` }, body: form });
    if (upload.status !== 201) throw new Error(`upload: ${upload.status} ${await upload.text()}`);
    const document = (await upload.json()) as { id: string };
    await call("POST", "/banking/imports", { document_id: document.id }, 201);

    // 1. Work list filtered by the account and direction: the outgoing payment is booked
    //    against the cost account in the dialog (no open item, contra account for the rest).
    await uiLogin(page, "/bank");
    const list = page.getByTestId("transaction-list");
    await list.getByLabel("Konto").selectOption(bankAccount.id);
    await list.getByLabel("Richtung").selectOption("out");
    const outgoing = list.getByTestId("transaction-row").filter({ hasText: `Hausmeister ${run}` });
    await expect(outgoing).toHaveCount(1);
    await outgoing.getByRole("button", { name: "Buchen" }).click();
    const dialog = page.getByTestId("booking-dialog");
    await expect(dialog.getByText("Ausgang")).toBeVisible();
    await dialog.getByLabel("Konto suchen (Nummer oder Name)").fill("Hausmeister");
    await dialog.getByRole("button", { name: "042000 Hausmeister E2E" }).click();
    await dialog.getByLabel("Buchungstext").fill(`Hausmeister ${run}`);
    await dialog.getByRole("button", { name: "Buchen", exact: true }).click();
    await expect(dialog.getByTestId("confirm-box")).toContainText("79,90 EUR");
    await dialog.getByRole("button", { name: "Buchung bestätigen" }).click();
    await expect(page.getByTestId("list-notice")).toContainText("Gebucht als");
    await list.getByLabel("Status").selectOption("booked");
    await expect(list.getByTestId("transaction-row").filter({ hasText: `Hausmeister ${run}` })).toHaveCount(1);

    // 2. Incoming payment: the unambiguous stage 1 proposal is taken over and booked.
    await list.getByLabel("Status").selectOption("new");
    await list.getByLabel("Richtung").selectOption("in");
    const incoming = list.getByTestId("transaction-row").filter({ hasText: contract.number });
    await expect(incoming).toHaveCount(1);
    await incoming.getByRole("button", { name: "Buchen" }).click();
    const row = dialog.getByTestId("proposal-row").first();
    await expect(row).toContainText("eindeutig");
    await row.getByRole("button", { name: "Übernehmen" }).click();
    await expect(dialog.getByTestId("rest")).toContainText("0,00 EUR");
    await dialog.getByRole("button", { name: "Buchen", exact: true }).click();
    await dialog.getByRole("button", { name: "Buchung bestätigen" }).click();
    await expect(page.getByTestId("list-notice")).toContainText("Gebucht als");
    const transactions = await call<{ bank_reference: string; status: string }[]>("GET", `/banking/transactions?bank_account_id=${bankAccount.id}`);
    expect(transactions.map((t) => t.status)).toEqual(["booked", "booked"]);

    // 3. Reconciliation B09: the statement closes at 170,10 (0,00 + 250,00 - 79,90) and the
    //    ledger account 001210 carries the same 170,10 from the two postings, so the statement
    //    difference and the ledger difference are both 0,00.
    await page.goto("/bank/abstimmung");
    await page.getByLabel("Bankkonto").selectOption(bankAccount.id);
    await expect(page.getByTestId("reconciliation-summary")).toContainText("Alle Auszüge stimmen ab.");
    await expect(page.getByText("170,10 EUR").first()).toBeVisible();

    // 4. Rules page shows the read only automation switch (default off) and the four eyes text.
    await page.goto("/bank/regeln");
    await expect(page.getByTestId("automation-state")).toContainText("ausgeschaltet");
    await expect(page.getByText(/Wer eine Regel vorschlägt, darf sie nicht freigeben/)).toBeVisible();

    // The postings are comparison postings: the ledger stays non leading.
    const ledgerRow = await call<{ leading_system: string }>("GET", `/accounting/ledgers/${ledger}`);
    expect(ledgerRow.leading_system).not.toBe("mhvp");
  });
});
