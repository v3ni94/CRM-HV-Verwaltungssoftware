import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PricingAdmin, type Pricing } from "./PricingAdmin";

const base = {
  min_units: 1,
  max_units: 50,
  unit: "unit_month",
  trial_days: null,
  sort_order: 1,
  active: true,
};
const pricing = (over: Partial<Pricing> = {}): Pricing => ({
  items: [
    { ...base, id: "i1", kind: "tier", code: "s", label: "Stufe S", amount: null, amount_missing: true },
    { ...base, id: "i2", kind: "module", code: "m", label: "Modul Messdaten", amount: "4.50", amount_missing: false, min_units: null, max_units: null },
  ],
  complete: false,
  missing_amounts: ["s"],
  ...over,
});

describe("PricingAdmin (GAH-407)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("marks missing amounts and invents none", () => {
    renderIntl(<PricingAdmin initial={pricing()} />);
    expect(screen.getByText("1 aktive Zeilen ohne Betrag. Angebote bleiben Entwurf.")).toBeInTheDocument();
    expect(screen.getByText("Betrag fehlt")).toBeInTheDocument();
    expect(screen.getByLabelText("Betrag netto Stufe S")).toHaveValue("");
    expect(screen.getByLabelText("Betrag netto Modul Messdaten")).toHaveValue("4.50");
  });

  it("shows the complete state", () => {
    renderIntl(<PricingAdmin initial={pricing({ complete: true, missing_amounts: [] })} />);
    expect(screen.getByText("Alle aktiven Zeilen haben einen Betrag.")).toBeInTheDocument();
  });

  it("saves a comma amount as decimal string", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(pricing()));
    renderIntl(<PricingAdmin initial={pricing()} />);
    await userEvent.type(screen.getByLabelText("Betrag netto Stufe S"), "1,25");
    await userEvent.click(screen.getAllByRole("button", { name: "Speichern" })[0]!);
    const patch = fetchMock.mock.calls[0];
    expect(String(patch?.[0])).toBe("/api/bff/platform/pricing/items/i1");
    expect(patch?.[1]?.method).toBe("PATCH");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ amount: "1.25" });
  });

  it("clears the amount when the field is empty", async () => {
    fetchMock.mockImplementation(async () => jsonResponse(pricing()));
    renderIntl(<PricingAdmin initial={pricing()} />);
    await userEvent.clear(screen.getByLabelText("Betrag netto Modul Messdaten"));
    await userEvent.click(screen.getAllByRole("button", { name: "Speichern" })[1]!);
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ clear_amount: true });
  });

  it("shows the refusal of the API", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ code: "X", title: "Ungültiger Betrag", status: 422 }, 422));
    renderIntl(<PricingAdmin initial={pricing()} />);
    await userEvent.click(screen.getAllByRole("button", { name: "Deaktivieren" })[0]!);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("builds the offer download link with encoded customer and numeric units", async () => {
    renderIntl(<PricingAdmin initial={pricing()} />);
    await userEvent.type(screen.getByLabelText("Interessent"), "A&B GmbH");
    await userEvent.type(screen.getByLabelText("Einheiten laut Angabe"), "1x2");
    const link = screen.getByRole("link", { name: "Angebotsentwurf herunterladen" });
    expect(link).toHaveAttribute("href", "/api/bff/platform/pricing/offer.pdf?customer_name=A%26B%20GmbH&units=12");
  });
});
