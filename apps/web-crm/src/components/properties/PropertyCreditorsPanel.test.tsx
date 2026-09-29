import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PropertyCreditorsPanel, type CreditorRow } from "./PropertyCreditorsPanel";

const PID = "0192abcd-0000-7000-8000-000000000321";
const ROWS: CreditorRow[] = [
  { id: "0192abcd-0000-7000-8000-000000000401", property_id: PID, contact_id: "0192abcd-0000-7000-8000-000000000501", contact_name: "Rohr frei GmbH", contact_roles: ["dienstleister"], trade: "Sanitär", since: "2024-03-01", source: "proposal", source_transaction_id: null, phone: "+4921731234567", email: "info@rohrfrei.example", last_invoice_date: "2026-08-12", last_invoice_amount: "1234.56", open_invoice_amount: "250.00", work_orders_count: 3 },
  { id: "0192abcd-0000-7000-8000-000000000402", property_id: PID, contact_id: "0192abcd-0000-7000-8000-000000000502", contact_name: "Blitz Elektro", contact_roles: ["dienstleister"], trade: "Elektro", since: null, source: "manual", source_transaction_id: null, phone: null, email: null, last_invoice_date: null, last_invoice_amount: null, open_invoice_amount: null, work_orders_count: 0 },
];

type Call = { url: string; method: string; body: unknown };

function mockFetch(calls: Call[]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (url.startsWith("/api/bff/contacts?")) return jsonResponse({ items: [{ id: "0192abcd-0000-7000-8000-000000000503", display_name: "Dach Meier" }] });
    if (url.endsWith("/backfill")) return jsonResponse({ scanned: 4, created: 2 });
    if (method === "DELETE") return new Response(null, { status: 204 });
    if (method === "POST") return jsonResponse({ ...ROWS[1], id: "new" }, 201);
    if (method === "PATCH") return jsonResponse({ ...ROWS[0], trade: "Heizung" });
    return jsonResponse(ROWS);
  });
}

describe("PropertyCreditorsPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists creditors with trade, contact links, last invoice, open invoices and work orders, filtered by trade", async () => {
    mockFetch([]);
    renderIntl(<PropertyCreditorsPanel propertyId={PID} canEdit={false} />);
    expect(await screen.findByRole("link", { name: "Rohr frei GmbH" })).toHaveAttribute("href", "/kontakte/0192abcd-0000-7000-8000-000000000501");
    expect(screen.getByRole("link", { name: "+4921731234567" })).toHaveAttribute("href", "tel:+4921731234567");
    expect(screen.getByRole("link", { name: "info@rohrfrei.example" })).toHaveAttribute("href", "mailto:info@rohrfrei.example");
    expect(screen.getByText("12.08.2026, 1.234,56 EUR")).toBeInTheDocument();
    expect(screen.getByText("250,00 EUR")).toBeInTheDocument();
    expect(screen.getByText("aus Buchung")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Kreditor verknüpfen" })).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Gewerk"), "Elektro");
    expect(screen.queryByText("Rohr frei GmbH")).not.toBeInTheDocument();
    expect(screen.getByText("Blitz Elektro")).toBeInTheDocument();
  });

  it("links a contact, edits the trade, unlinks and backfills with properties:update", async () => {
    const calls: Call[] = [];
    mockFetch(calls);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<PropertyCreditorsPanel propertyId={PID} canEdit />);
    await screen.findByText("Rohr frei GmbH");
    await userEvent.click(screen.getByRole("button", { name: "Kreditor verknüpfen" }));
    await userEvent.type(screen.getByTestId("creditor-contact"), "Da");
    await userEvent.click(await screen.findByRole("button", { name: "Dach Meier" }));
    await userEvent.type(screen.getByPlaceholderText("z. B. Sanitär, Elektro"), "Dach");
    await userEvent.click(screen.getByRole("button", { name: "Verknüpfen" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.url === `/api/bff/properties/${PID}/creditors`)?.body).toEqual({ contact_id: "0192abcd-0000-7000-8000-000000000503", trade: "Dach" }));
    expect(await screen.findByText("Kreditor verknüpft.")).toBeInTheDocument();

    await userEvent.click(screen.getAllByRole("button", { name: "Gewerk ändern" })[0]!);
    const input = screen.getByRole("textbox", { name: "Gewerk" });
    await userEvent.clear(input);
    await userEvent.type(input, "Heizung");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ trade: "Heizung" }));

    await userEvent.click(screen.getAllByRole("button", { name: "Lösen" })[0]!);
    await waitFor(() => expect(calls.find((c) => c.method === "DELETE")?.url).toBe(`/api/bff/properties/${PID}/creditors/${ROWS[0]!.id}`));

    await userEvent.click(screen.getByRole("button", { name: "Aus Buchungen nachziehen" }));
    expect(await screen.findByText("2 Verknüpfungen aus vorhandenen Buchungen und Rechnungen ergänzt.")).toBeInTheDocument();
    expect(calls.find((c) => c.url.endsWith("/backfill"))?.body).toEqual({ property_id: PID });
  });
});
