import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ContractCreateForm, ContractEditForm, parseAmount, splitProblem, type ContractOut } from "./ContractForm";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh, back: vi.fn() }) }));

const PROPERTY = "01920000-0000-7000-8000-0000000000p1";
const SEV_PROPERTY = "01920000-0000-7000-8000-0000000000p2";
const UNIT = "01920000-0000-7000-8000-0000000000u1";
const PARTY = "01920000-0000-7000-8000-0000000000c1";
const CONTRACT = "01920000-0000-7000-8000-0000000000k1";

const properties = [
  { id: PROPERTY, label: "0001 Musterstraße 1", management_type: "rental" as const },
  { id: SEV_PROPERTY, label: "0002 WEG Beispielweg 2", management_type: "hoa_with_sev" as const },
];

const contract: ContractOut = {
  id: CONTRACT,
  kind: "tenancy",
  number: "MV-0001",
  version: 1,
  property_id: PROPERTY,
  unit_id: UNIT,
  party_id: PARTY,
  legal_entity_id: "01920000-0000-7000-8000-0000000000l1",
  start_date: "2024-01-01",
  end_date: null,
  termination_date: null,
  termination_reason: null,
  direct_debit: false,
  sepa_mandate_id: null,
  dunning_block: false,
  dunning_block_reason: null,
  rent_increase_block_until: null,
  user_change_fee: false,
  allocation_loss_risk: false,
  vat_option: "none",
  sev_enabled: false,
  sev_fee_debtor_party_id: null,
  title_transfer_date: null,
  benefit_burden_date: null,
  acquisition_kind: null,
  special_succession_liability: false,
  notes: null,
  schedules: [{ id: "s1", interval: "monthly", due_day_rule: "day", due_day: 3, valid_from: "2024-01-01", valid_to: null }],
};

/** Answers the lookups of the form; mutations are recorded by the test. */
function lookups(url: string): Response | null {
  if (url.startsWith(`/api/bff/properties/${PROPERTY}/units`) || url.startsWith(`/api/bff/properties/${SEV_PROPERTY}/units`)) {
    return jsonResponse([{ id: UNIT, number: "WE 01", label: "EG links", unit_type: "apartment" }]);
  }
  if (url.includes("/legal-entities")) return jsonResponse([{ id: "le1", name: "Eigentümer A", kind: "owner" }]);
  if (url.startsWith("/api/bff/contacts?")) return jsonResponse({ items: [{ id: PARTY, display_name: "Erika Mustermann", roles: ["mieter"] }] });
  if (url.startsWith("/api/bff/sepa-mandates")) return jsonResponse([]);
  if (url === "/api/bff/catalogs/payment_type") {
    return jsonResponse([
      { id: "pt1", catalog: "payment_type", code: "rent", label: "Miete", active: true, is_system: true },
      { id: "pt2", catalog: "payment_type", code: "operating_cost_advance", label: "Betriebskosten-Vorauszahlung", active: true, is_system: true },
    ]);
  }
  return null;
}

async function fillBase(kind: "tenancy" | "ownership", propertyId = PROPERTY) {
  const user = userEvent.setup();
  await user.selectOptions(screen.getByLabelText("Vertragsart"), kind);
  await user.selectOptions(screen.getByLabelText("Objekt"), propertyId);
  await waitFor(() => expect(within(screen.getByLabelText("Einheit")).getByRole("option", { name: "WE 01 EG links" })).toBeInTheDocument());
  await user.selectOptions(screen.getByLabelText("Einheit"), UNIT);
  await user.type(screen.getByLabelText("Kontakt suchen"), "Muster{Enter}");
  await user.click(await screen.findByRole("button", { name: "Erika Mustermann" }));
  expect(screen.getByTestId("picked-party")).toHaveTextContent("Erika Mustermann");
  return user;
}

describe("ContractCreateForm", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    push.mockReset();
    refresh.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("creates a tenancy with schedule and deposit and opens the detail page", async () => {
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (method === "POST" && url === "/api/bff/contracts") return jsonResponse({ ...contract, schedules: [] }, 201);
      if (method === "POST" && url === `/api/bff/contracts/${CONTRACT}/schedules`) return jsonResponse(contract.schedules[0], 201);
      if (method === "POST" && url === `/api/bff/contracts/${CONTRACT}/deposits`) return jsonResponse({ id: "d1" }, 201);
      return lookups(url) ?? jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<ContractCreateForm properties={properties} />);
    const user = await fillBase("tenancy");
    // Role filter is preset from the kind and sent with the search.
    const search = fetchMock.mock.calls.find(([u]) => String(u).startsWith("/api/bff/contacts?"))!;
    expect(String(search[0])).toContain("role=mieter");

    await user.clear(screen.getByLabelText("Beginn"));
    await user.type(screen.getByLabelText("Beginn"), "2026-10-01");
    await user.click(screen.getByLabelText("Mahnsperre"));
    await user.type(screen.getByLabelText("Begründung der Mahnsperre"), "Ratenvereinbarung");
    // M13-01/M13-02: pro rata rule of the contract and payment mode of the schedule.
    // The option labels come from the catalogue (the next-intl fallback showed raw keys here).
    expect(within(screen.getByLabelText("Zeitanteilsregel")).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Standard des Mandanten",
      "Kalendertage",
      "30/360",
      "voller Monat",
    ]);
    await user.selectOptions(screen.getByLabelText("Zeitanteilsregel"), "thirty_360");
    await user.click(screen.getByLabelText("Zahlungsplan gleich anlegen"));
    expect(within(screen.getByLabelText("Zahlweise")).getAllByRole("option").map((o) => o.textContent)).toEqual(["im Voraus", "nachschüssig"]);
    await user.selectOptions(screen.getByLabelText("Zahlweise"), "arrears");
    expect(screen.queryByLabelText("Betragsbasis")).not.toBeInTheDocument(); // monthly: amount is per month
    await user.selectOptions(screen.getByLabelText("Intervall"), "quarterly");
    expect(within(screen.getByLabelText("Betragsbasis")).getAllByRole("option").map((o) => o.textContent)).toEqual(["je Monat", "je Rate"]);
    await user.selectOptions(screen.getByLabelText("Intervall"), "monthly");
    await user.clear(screen.getByLabelText("Fälligkeitstag"));
    await user.type(screen.getByLabelText("Fälligkeitstag"), "5");
    await user.clear(screen.getByLabelText("Gültig ab"));
    await user.type(screen.getByLabelText("Gültig ab"), "2026-10-01");
    await user.click(screen.getByLabelText("Kaution gleich erfassen"));
    await user.type(screen.getByLabelText("Betrag"), "1.500,00");
    expect(screen.getByText("1.500,00 EUR")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Notizen"), "Übergabe am Monatsanfang");
    await user.click(screen.getByRole("button", { name: "Vertrag anlegen" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith(`/vertraege/${CONTRACT}`));
    const posts = fetchMock.mock.calls.filter(([, i]) => i?.method === "POST");
    expect(posts.map(([u]) => String(u))).toEqual(["/api/bff/contracts", `/api/bff/contracts/${CONTRACT}/schedules`, `/api/bff/contracts/${CONTRACT}/deposits`]);
    expect(JSON.parse(String(posts[0]![1]!.body))).toEqual({
      kind: "tenancy",
      unit_id: UNIT,
      contact_id: PARTY,
      start_date: "2026-10-01",
      end_date: null,
      legal_entity_id: null,
      direct_debit: false,
      sepa_mandate_id: null,
      dunning_block: true,
      dunning_block_reason: "Ratenvereinbarung",
      rent_increase_block_until: null,
      user_change_fee: false,
      allocation_loss_risk: false,
      vat_option: "none",
      proration_method: "thirty_360",
      notes: "Übergabe am Monatsanfang",
    });
    expect(JSON.parse(String(posts[1]![1]!.body))).toEqual({ interval: "monthly", due_day_rule: "day", due_day: 5, valid_from: "2026-10-01", valid_to: null, payment_mode: "arrears", amount_basis: "per_month" });
    expect(JSON.parse(String(posts[2]![1]!.body))).toMatchObject({ kind: "cash", amount_due: "1500.00", installments: 1 });
  }, 20000);

  it("records standing amounts from the start date after creating the contract and reports a failed one", async () => {
    const paymentBodies: Record<string, unknown>[] = [];
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (method === "POST" && url === "/api/bff/contracts") return jsonResponse({ ...contract, schedules: [] }, 201);
      if (method === "POST" && url === `/api/bff/contracts/${CONTRACT}/payments`) {
        const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
        paymentBodies.push(body);
        if (body["payment_type_code"] === "operating_cost_advance") return jsonResponse({ title: "Konflikt", status: 409, detail: "Die Zahlung überschneidet sich mit einer bestehenden Zahlung." }, 409);
        return jsonResponse({ id: "a1", contract_id: CONTRACT, currency: "EUR", valid_to: null, ...body }, 201);
      }
      return lookups(url) ?? jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<ContractCreateForm properties={properties} />);
    const user = await fillBase("tenancy");
    await user.clear(screen.getByLabelText("Beginn"));
    await user.type(screen.getByLabelText("Beginn"), "2026-10-01");

    const addRow = await screen.findByRole("button", { name: "Sollbetrag hinzufügen" });
    await waitFor(() => expect(addRow).toBeEnabled());
    await user.click(addRow);
    await user.click(addRow);
    const first = within(screen.getByTestId("amount-draft-0"));
    const second = within(screen.getByTestId("amount-draft-1"));
    await user.type(first.getByLabelText("Netto"), "800,00");
    expect(screen.getByTestId("amount-draft-gross-0")).toHaveTextContent("Brutto: 800,00 EUR");
    // Same kind twice is rejected client side before any request.
    await user.type(second.getByLabelText("Netto"), "150");
    await user.click(screen.getByRole("button", { name: "Vertrag anlegen" }));
    expect(await screen.findByText("Jede Zahlungsart nur einmal; spätere Stände auf der Vertragsseite erfassen.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, i]) => i?.method === "POST")).toHaveLength(0);

    await user.selectOptions(second.getByLabelText("Zahlungsart"), "operating_cost_advance");
    await user.clear(second.getByLabelText("USt in %"));
    await user.type(second.getByLabelText("USt in %"), "19");
    expect(screen.getByTestId("amount-draft-gross-1")).toHaveTextContent("Brutto: 178,50 EUR");
    await user.click(screen.getByRole("button", { name: "Vertrag anlegen" }));

    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(paymentBodies).toEqual([
      { payment_type_code: "rent", net: "800.00", vat_percent: "0", gross: "800.00", valid_from: "2026-10-01", valid_to: null, reason: "initial" },
      { payment_type_code: "operating_cost_advance", net: "150.00", vat_percent: "19", gross: "178.50", valid_from: "2026-10-01", valid_to: null, reason: "initial" },
    ]);
    // The contract exists; the failed amount is reported as a notice on the detail page.
    const target = String(push.mock.calls[0]![0]);
    expect(target.startsWith(`/vertraege/${CONTRACT}?hinweis=`)).toBe(true);
    expect(decodeURIComponent(target)).toContain("der Sollbetrag Betriebskosten-Vorauszahlung jedoch nicht: Die Zahlung überschneidet sich mit einer bestehenden Zahlung.");
  }, 20000);

  it("creates an ownership with SEV in a hoa_with_sev property", async () => {
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "POST" && url === "/api/bff/contracts") return jsonResponse({ ...contract, kind: "ownership" }, 201);
      return lookups(url) ?? jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<ContractCreateForm properties={properties} />);
    const user = await fillBase("ownership", SEV_PROPERTY);
    expect(screen.queryByLabelText("Kaution gleich erfassen")).not.toBeInTheDocument();
    await user.clear(screen.getByLabelText("Beginn"));
    await user.type(screen.getByLabelText("Beginn"), "2026-03-01");
    await user.type(screen.getByLabelText("Eigentumsübergang (Grundbuch)"), "2026-02-15");
    await user.type(screen.getByLabelText("Nutzen- und Lastenwechsel"), "2026-03-01");
    await user.selectOptions(screen.getByLabelText("Erwerbsart"), "purchase");
    await user.click(screen.getByLabelText("Sondereigentumsverwaltung (SEV) aktiv"));
    await user.click(screen.getByRole("button", { name: "Vertrag anlegen" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith(`/vertraege/${CONTRACT}`));
    const [, init] = fetchMock.mock.calls.find(([u, i]) => String(u) === "/api/bff/contracts" && i?.method === "POST")!;
    expect(JSON.parse(String(init!.body))).toMatchObject({
      kind: "ownership",
      unit_id: UNIT,
      contact_id: PARTY,
      start_date: "2026-03-01",
      title_transfer_date: "2026-02-15",
      benefit_burden_date: "2026-03-01",
      acquisition_kind: "purchase",
      sev_enabled: true,
      sev_fee_debtor_contact_id: null,
      special_succession_liability: false,
    });
  });

  it("shows client side validation and maps 422 field errors of the API", async () => {
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "POST" && url === "/api/bff/contracts") {
        return jsonResponse(
          {
            title: "Validierungsfehler",
            status: 422,
            detail: "Bitte die markierten Angaben prüfen.",
            errors: [
              { location: ["body", "start_date"], field: "start_date", code: "date_from_datetime_parsing", message: "Ungültiges Datum." },
              { location: ["body"], field: "", code: "value_error", message: "Für die Einheit besteht im Zeitraum bereits ein Vertrag dieser Art." },
            ],
          },
          422,
        );
      }
      return lookups(url) ?? jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<ContractCreateForm properties={properties} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Vertrag anlegen" }));
    expect(await screen.findByText("Bitte eine Einheit wählen.")).toBeInTheDocument();
    expect(screen.getByText("Bitte einen Vertragspartner wählen.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, i]) => i?.method === "POST")).toBe(false);

    await fillBase("ownership");
    await user.clear(screen.getByLabelText("Beginn"));
    await user.type(screen.getByLabelText("Beginn"), "2026-03-01");
    await user.type(screen.getByLabelText("Ende"), "2026-02-01");
    await user.click(screen.getByRole("button", { name: "Vertrag anlegen" }));
    expect(await screen.findByText("Das Ende darf nicht vor dem Beginn liegen.")).toBeInTheDocument();
    expect(screen.getByText("Bei Eigentum ist der Eigentumsübergang laut Grundbuch Pflicht.")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Ende"));
    await user.type(screen.getByLabelText("Eigentumsübergang (Grundbuch)"), "2026-02-15");
    await user.click(screen.getByRole("button", { name: "Vertrag anlegen" }));
    expect(await screen.findByText("Ungültiges Datum.")).toBeInTheDocument();
    expect(screen.getByText(/bereits ein Vertrag dieser Art/)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  }, 20000);
});

describe("ContractEditForm", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    push.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shows the fixed data and posts a new version from the effective date", async () => {
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "POST" && url === `/api/bff/contracts/${CONTRACT}/versions`) return jsonResponse({ ...contract, id: "k2", version: 2 }, 201);
      return lookups(url) ?? jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<ContractEditForm contract={contract} partyName="Erika Mustermann" unitLabel="WE 01 EG links" propertyLabel="0001 Musterstraße 1" />);
    const fixed = screen.getByTestId("contract-fixed");
    expect(fixed).toHaveTextContent("MV-0001 (Version 1)");
    expect(fixed).toHaveTextContent("01.01.2024");
    expect(fixed).toHaveTextContent("unbefristet");
    expect(screen.getByText(/monatlich, Kalendertag 3, ab 01.01.2024/)).toBeInTheDocument();

    const user = userEvent.setup();
    const form = within(screen.getByTestId("contract-version-form"));
    await user.clear(form.getByLabelText("Gültig ab"));
    await user.type(form.getByLabelText("Gültig ab"), "2023-06-01");
    await user.click(form.getByRole("button", { name: "Neue Version speichern" }));
    expect(await form.findByText("Die Änderung muss nach dem Vertragsbeginn gelten.")).toBeInTheDocument();

    await user.clear(form.getByLabelText("Gültig ab"));
    await user.type(form.getByLabelText("Gültig ab"), "2026-11-01");
    await user.selectOptions(form.getByLabelText("Umsatzsteuer"), "commercial_full_vat");
    await user.click(form.getByLabelText("Nutzerwechselgebühr"));
    await user.click(form.getByRole("button", { name: "Neue Version speichern" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/vertraege/k2"));
    const [, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "POST")!;
    expect(JSON.parse(String(init!.body))).toEqual({
      effective_date: "2026-11-01",
      direct_debit: false,
      sepa_mandate_id: null,
      dunning_block: false,
      dunning_block_reason: null,
      rent_increase_block_until: null,
      user_change_fee: true,
      allocation_loss_risk: false,
      vat_option: "commercial_full_vat",
      proration_method: null,
      notes: null,
    });
  });

  it("ends a tenancy through the termination endpoint", async () => {
    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "POST" && url === `/api/bff/contracts/${CONTRACT}/termination`) return jsonResponse({ ...contract, end_date: "2026-12-31" });
      return lookups(url) ?? jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<ContractEditForm contract={contract} partyName="Erika Mustermann" unitLabel="WE 01" propertyLabel="0001" />);
    const user = userEvent.setup();
    const form = within(screen.getByTestId("contract-termination-form"));
    await user.type(form.getByLabelText("Vertragsende"), "2026-12-31");
    await user.type(form.getByLabelText("Grund"), "Kündigung des Mieters");
    await user.click(form.getByRole("button", { name: "Vertrag beenden" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/vertraege/${CONTRACT}`));
    const [, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "POST")!;
    expect(JSON.parse(String(init!.body))).toMatchObject({ end_date: "2026-12-31", termination_reason: "Kündigung des Mieters" });
  });
});

describe("helpers", () => {
  it("parses German amounts without float", () => {
    expect(parseAmount("1.234,56")).toBe("1234.56");
    expect(parseAmount("1234,5")).toBe("1234.50");
    expect(parseAmount("1500")).toBe("1500.00");
    expect(parseAmount("1500.00 EUR")).toBe("1500.00");
    expect(parseAmount("abc")).toBeNull();
    expect(parseAmount("")).toBeNull();
  });

  it("splits problem details into field and form messages", () => {
    const { fields, rest } = splitProblem(
      { errors: [{ location: ["body", "unit_id"], field: "unit_id", code: "x", message: "Feld" }, { location: ["body"], field: "", code: "y", message: "Allgemein" }] },
      ["unit_id"],
    );
    expect(fields).toEqual({ unit_id: "Feld" });
    expect(rest).toEqual(["Allgemein"]);
  });
});
