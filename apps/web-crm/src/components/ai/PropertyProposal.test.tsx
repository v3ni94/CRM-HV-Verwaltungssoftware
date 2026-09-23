import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { Proposal } from "@/lib/ai";
import { vatMap } from "@/lib/ai";
import { jsonResponse, renderIntl } from "@/test/intl";

import { PropertyProposal } from "./PropertyProposal";

const ID = "01920000-0000-7000-8000-0000000000p2";

const proposal: Proposal = {
  id: ID,
  task_run_id: "01920000-0000-7000-8000-0000000000r2",
  entity_type: "property",
  context_id: null,
  decision: "pending",
  decided_by: null,
  decided_at: null,
  import_run_id: null,
  proposed: {
    property: { number: null, name: "Musterstraße 1", management_type: "hoa", street: "Musterstraße", house_number: "1", postal_code: "40721", city: "Hilden" },
    buildings: ["Vorderhaus"],
    units: [{ number: "1", label: null, building: "Vorderhaus", location: "EG links", unit_type: "apartment", living_area_sqm: "72.5", mea: "125.5", source: "TE S. 3", confidence: 0.9 }],
    parties: [
      {
        role: "owner",
        unit_number: "1",
        kind: "person",
        salutation: "Frau",
        first_name: "Erika",
        last_name: "Mustermann",
        company_name: null,
        start_date: "2020-01-01",
        payments: [
          { payment_type_code: "hoa_fee", gross: "1234.5", valid_from: null },
          { payment_type_code: "reserve", gross: "50", valid_from: null },
        ],
        source: null,
        confidence: 0.8,
      },
    ],
    questions: ["Gibt es ein Hinterhaus?"],
    notes: ["Einheit 2: Fläche 'ca. 60' unlesbar."],
  },
};

describe("vatMap", () => {
  it("drops empty inputs, accepts comma and rejects invalid rates", () => {
    expect(vatMap({ rent: "", hoa_fee: "0", garage: "19,0", other: "abc" })).toEqual({
      map: { hoa_fee: "0", garage: "19.0" },
      invalid: ["other"],
    });
  });
});

describe("PropertyProposal", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders the tree with units, parties and payments, notes and questions", () => {
    renderIntl(<PropertyProposal proposal={proposal} />);
    expect(screen.getByText("Objekt Musterstraße 1")).toBeInTheDocument();
    expect(screen.getByText("Gebäude Vorderhaus")).toBeInTheDocument();
    expect(screen.getByText(/72,50 m², MEA 125,5000/)).toBeInTheDocument();
    expect(screen.getByText("Eigentümer: Erika Mustermann")).toBeInTheDocument();
    expect(screen.getByText(/Hausgeld: 1\.234,50 EUR brutto/)).toBeInTheDocument();
    expect(screen.getByText("Gibt es ein Hinterhaus?")).toBeInTheDocument();
    expect(screen.getByText("Einheit 2: Fläche 'ca. 60' unlesbar.")).toBeInTheDocument();
  });

  it("explains that an empty VAT rate means the payment is not created", async () => {
    renderIntl(<PropertyProposal proposal={proposal} />);
    expect(screen.getByTestId("vat-skip-hoa_fee")).toHaveTextContent("wird diese Zahlung nicht angelegt");
    expect(screen.getByTestId("vat-summary")).toHaveTextContent("Hausgeld, Erhaltungsrücklage");
    await userEvent.type(screen.getByLabelText("Steuersatz Hausgeld in %"), "0");
    expect(screen.queryByTestId("vat-skip-hoa_fee")).not.toBeInTheDocument();
    expect(screen.getByTestId("vat-summary")).toHaveTextContent("Erhaltungsrücklage");
    expect(screen.getByTestId("vat-summary")).not.toHaveTextContent("Hausgeld");
  });

  it("requires number, management type and as-of date and sends only confirmed rates", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ id: "01920000-0000-7000-8000-0000000000i2", source: "ai:extract_property", status: "applied", summary: { notes: ["Erika Mustermann: Zahlung reserve ohne bestätigten Steuersatz, nicht angelegt."] }, created_at: "2026-09-23T08:00:00Z", undone_at: null, items: [] }, 201),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<PropertyProposal proposal={proposal} />);
    const confirm = screen.getByRole("button", { name: "Bestätigen und übernehmen" });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Objektnummer (3 Ziffern)"), "12a3");
    await userEvent.type(screen.getByLabelText("Stichtag für Miteigentumsanteile"), "2026-01-01");
    await userEvent.type(screen.getByLabelText("Steuersatz Hausgeld in %"), "0");
    expect(confirm).toBeEnabled();
    await userEvent.click(confirm);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe(`/api/bff/ai/proposals/${ID}/apply`);
    expect(JSON.parse(init.body as string)).toEqual({
      property: { number: "123", name: "Musterstraße 1", management_type: "hoa", as_of: "2026-01-01", vat_percent_by_payment_type: { hoa_fee: "0" } },
    });
    expect(await screen.findByText(/Zahlung reserve ohne bestätigten Steuersatz/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rückgängig" })).toBeInTheDocument();
  });

  it("blocks an invalid VAT entry", async () => {
    renderIntl(<PropertyProposal proposal={proposal} />);
    await userEvent.type(screen.getByLabelText("Objektnummer (3 Ziffern)"), "123");
    await userEvent.type(screen.getByLabelText("Stichtag für Miteigentumsanteile"), "2026-01-01");
    await userEvent.type(screen.getByLabelText("Steuersatz Erhaltungsrücklage in %"), "neunzehn");
    expect(screen.getByText("Bitte einen Prozentsatz wie 0, 7 oder 19 eingeben.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Bestätigen und übernehmen" })).toBeDisabled();
  });
});
