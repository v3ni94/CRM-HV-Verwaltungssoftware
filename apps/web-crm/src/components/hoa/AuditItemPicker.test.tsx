import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AuditItemPicker, type AuditCandidates } from "./AuditItemPicker";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));
const AUDIT = "0192abcd-0000-7000-8000-000000000201";

const candidates: AuditCandidates = {
  period_from: "2025-01-01",
  period_to: "2025-12-31",
  total: 2,
  truncated: false,
  items: [
    {
      journal_entry_id: "je1",
      booking_date: "2025-06-01",
      number: 3,
      text: "Reinigung Juni",
      amount: "120.00",
      document_id: "doc1",
      accounts: [{ id: "a1", number: "040300", name: "Reinigungskosten" }],
      vendor_contact_id: "v1",
      invoice_number: "R-1",
      selected: false,
    },
    {
      journal_entry_id: "je2",
      booking_date: "2025-09-15",
      number: 4,
      text: "Gartenpflege",
      amount: "80.00",
      document_id: null,
      accounts: [{ id: "a2", number: "040400", name: "Gartenarbeiten" }],
      vendor_contact_id: null,
      invoice_number: null,
      selected: true,
    },
  ],
};

describe("AuditItemPicker", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads candidates with the filters and adds a booking as audit position", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (init?.method === "POST") return jsonResponse({ id: "item-1", status: "open" }, 201);
      return jsonResponse(candidates);
    });
    const user = userEvent.setup();
    renderIntl(
      <AuditItemPicker
        auditId={AUDIT}
        accounts={[{ id: "a1", number: "040300", name: "Reinigungskosten" }]}
        periodFrom="2025-01-01"
        periodTo="2025-12-31"
      />,
    );
    await user.selectOptions(screen.getByLabelText("Konto"), "a1");
    await user.clear(screen.getByLabelText("Buchungsdatum von"));
    await user.type(screen.getByLabelText("Buchungsdatum von"), "2025-06-01");
    await user.type(screen.getByLabelText("Buchungstext"), "Reinigung");
    await user.click(screen.getByRole("button", { name: "Positionen laden" }));
    await waitFor(() => expect(screen.getByText("Reinigung Juni")).toBeInTheDocument());
    const url = new URL(String(fetchMock.mock.calls[0]?.[0]), "http://x");
    expect(url.pathname).toBe(`/api/bff/hoa/audits/${AUDIT}/candidates`);
    expect(url.searchParams.get("account_id")).toBe("a1");
    expect(url.searchParams.get("date_from")).toBe("2025-06-01");
    expect(url.searchParams.get("date_to")).toBe("2025-12-31");
    expect(url.searchParams.get("q")).toBe("Reinigung");
    expect(screen.getByText("2 Buchungen im Zeitraum 01.01.2025 bis 31.12.2025.")).toBeInTheDocument();
    expect(screen.getByText("Rechnung R-1", { exact: false })).toBeInTheDocument();
    // The second row is already a position; only the first offers the button.
    expect(screen.getByText("aufgenommen")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Als Prüfposition aufnehmen" }));
    await waitFor(() => expect(screen.getAllByText("aufgenommen")).toHaveLength(2));
    const add = fetchMock.mock.calls[1]!;
    expect(String(add[0])).toBe(`/api/bff/hoa/audits/${AUDIT}/items`);
    expect(JSON.parse(String(add[1]?.body))).toEqual({ journal_entry_id: "je1", document_id: "doc1", amount: "120.00" });
    expect(refresh).toHaveBeenCalled();
  });

  it("filters by vendor through the contact search", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      if (String(input).startsWith("/api/bff/contacts?")) return jsonResponse({ items: [{ id: "v1", display_name: "Gärtner GmbH" }] });
      return jsonResponse({ ...candidates, total: 1, items: [candidates.items[0]!] });
    });
    const user = userEvent.setup();
    renderIntl(<AuditItemPicker auditId={AUDIT} accounts={[]} periodFrom="2025-01-01" periodTo="2025-12-31" />);
    await user.type(screen.getByLabelText("Lieferant suchen"), "Gärtner");
    await user.click(screen.getByRole("button", { name: "Suchen" }));
    await user.click(await screen.findByRole("button", { name: "Gärtner GmbH" }));
    await user.click(screen.getByRole("button", { name: "Positionen laden" }));
    await waitFor(() => expect(screen.getByText("Reinigung Juni")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("kind=company");
    const url = new URL(String(fetchMock.mock.calls[1]?.[0]), "http://x");
    expect(url.searchParams.get("vendor_contact_id")).toBe("v1");
  });
});
