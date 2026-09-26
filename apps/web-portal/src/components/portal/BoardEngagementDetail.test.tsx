import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BoardEngagementDetail } from "./BoardEngagementDetail";
import type { BoardEngagementDetail as Detail, BoardReport } from "./types";

const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh }),
}));

const detail: Detail = {
  id: "e1",
  legal_entity_id: "le1",
  legal_entity_name: "WEG Musterstraße 1",
  statement_id: null,
  period_from: "2025-01-01",
  period_to: "2025-12-31",
  purpose: "Stichprobe Jahresabrechnung 2025",
  sampling: "sample",
  status: "open",
  snapshot_hash: null,
  overall_status: "eingeschränkt: offene Positionen oder Beanstandungen",
  population: { entries: 0 },
  positions: [
    {
      id: "p1",
      journal_entry_id: null,
      document_id: "d1",
      amount: "120.00",
      status: "checked",
      note: null,
      question: null,
      answer: null,
      outdated_reason: null,
      booking_date: "2025-06-01",
      booking_text: "Gartenpflege Juni",
      booking_reference: null,
      accounts: [{ id: "a1", number: "040300", name: "Gartenpflege" }],
      vendor_contact_id: "v1",
      vendor_name: "Gärtner GmbH",
    },
    {
      id: "p2",
      journal_entry_id: null,
      document_id: null,
      amount: "80.00",
      status: "outdated",
      note: null,
      question: null,
      answer: null,
      outdated_reason: "Rechnung nach Prüfung geändert",
      booking_date: null,
      booking_text: null,
      booking_reference: null,
    },
  ],
  cost_items: [],
  documents: [{ id: "d1", title: "Rechnung Gartenpflege", filename: "garten.pdf", mime_type: "application/pdf", created_at: "2025-06-02T00:00:00Z", audit_item_id: "p1" }],
  notes: [
    { id: "n1", engagement_id: "e1", audit_item_id: "p1", cost_item_id: null, kind: "answered", text: "Warum ohne Angebot?", answer: "Unter der Wertgrenze.", created_at: "2025-07-01T00:00:00Z", answered_at: "2025-07-02T00:00:00Z" },
  ],
  read_receipt_note: "Indiz für den Abruf über das Portal.",
  positions_total: 2,
  filter: { account_id: null, vendor_contact_id: null, date_from: null, date_to: null, q: null },
  filter_options: {
    accounts: [
      { id: "a1", number: "040300", name: "Gartenpflege" },
      { id: "a2", number: "040400", name: "Reinigung" },
    ],
    vendors: [{ id: "v1", name: "Gärtner GmbH" }],
  },
};

const report: BoardReport = {
  id: "r1",
  engagement_id: "e1",
  version: 1,
  created_at: "2025-08-01T10:00:00Z",
  content: {
    date: "2025-08-01",
    scope_note: "Stichprobe: geprüft sind nur die ausgewählten Positionen.",
    overall_status: "Stichprobe geprüft",
    checked_count: 1,
    checked_value: "120.00",
    unchecked_count: 1,
    unchecked_value: "80.00",
    findings: "Ohne Beanstandung",
    recommendation: "Entlastung",
  },
  board_statement: null,
  board_statement_history: [],
};

describe("BoardEngagementDetail", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    refresh.mockReset();
    push.mockReset();
  });

  it("shows positions with status, the outdated marker, the released receipt and the answered question", () => {
    renderIntl(<BoardEngagementDetail detail={detail} />);
    expect(screen.getAllByText("Position 1: Gartenpflege Juni")).toHaveLength(2); // card and select option
    expect(screen.getByText("Geprüft")).toBeInTheDocument();
    expect(screen.getByText("Rechnung nach Prüfung geändert")).toBeInTheDocument();
    expect(screen.getByText("Rechnung Gartenpflege")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Beleg öffnen" })).toHaveAttribute(
      "href",
      "/api/portal-files/portal/board/engagements/e1/documents/d1",
    );
    expect(screen.getByText("Warum ohne Angebot?")).toBeInTheDocument();
    expect(screen.getByText(/Unter der Wertgrenze\./)).toBeInTheDocument();
    // No booking, release or statement action exists for the board role.
    expect(screen.queryByText(/buchen/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/freigeben/i)).not.toBeInTheDocument();
  });

  it("sends a question for a position and refreshes", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: "n2", kind: "question" }, 201));
    renderIntl(<BoardEngagementDetail detail={detail} />);
    await user.selectOptions(screen.getByLabelText("Position"), "p1");
    await user.type(screen.getByLabelText("Text"), "Bitte das Angebot nachreichen.");
    await user.click(screen.getByRole("button", { name: "Absenden" }));
    await waitFor(() => expect(screen.getByText("Die Rückfrage wurde an die Verwaltung übermittelt.")).toBeInTheDocument(), { timeout: 5000 });
    expect(fetch).toHaveBeenCalledWith(
      "/api/bff/portal/board/engagements/e1/notes",
      expect.objectContaining({ method: "POST" }),
    );
    const body = JSON.parse(vi.mocked(fetch).mock.calls[0]?.[1]?.body as string);
    expect(body).toEqual({ kind: "question", text: "Bitte das Angebot nachreichen.", audit_item_id: "p1" });
    expect(refresh).toHaveBeenCalled();
  });

  it("A77: offers account and vendor of the positions as filter values and navigates with the query", async () => {
    const user = userEvent.setup();
    renderIntl(<BoardEngagementDetail detail={detail} />);
    expect(screen.getByText("2 Positionen, ungefiltert.")).toBeInTheDocument();
    expect(screen.getByText(/Konto: 040300 · Lieferant: Gärtner GmbH/)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Konto"), "a2");
    await user.selectOptions(screen.getByLabelText("Lieferant"), "v1");
    await user.type(screen.getByLabelText("Buchungsdatum von"), "2025-06-01");
    await user.type(screen.getByLabelText("Buchungstext"), "Garten");
    await user.click(screen.getByRole("button", { name: "Filter anwenden" }));
    expect(push).toHaveBeenCalledWith("/pruefung/e1?account_id=a2&vendor_contact_id=v1&date_from=2025-06-01&q=Garten");
    // No reset button without an active filter.
    expect(screen.queryByRole("button", { name: "Filter zurücksetzen" })).not.toBeInTheDocument();
  });

  it("A77: shows the active filter with count and resets to the unfiltered page", async () => {
    const user = userEvent.setup();
    const filtered: Detail = {
      ...detail,
      positions: [],
      filter: { account_id: "a2", vendor_contact_id: null, date_from: null, date_to: null, q: null },
    };
    renderIntl(<BoardEngagementDetail detail={filtered} />);
    expect(screen.getByText("0 von 2 Positionen angezeigt.")).toBeInTheDocument();
    expect(screen.getByText("Keine Position entspricht dem Filter.")).toBeInTheDocument();
    expect(screen.getByLabelText("Konto")).toHaveValue("a2");
    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    expect(push).toHaveBeenCalledWith("/pruefung/e1");
  });

  it("A76: shows the report and records the board statement without any release action", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ ...report, board_statement: { text: "Zur Kenntnis genommen.", recorded_at: "2025-08-02T09:00:00Z", recorded_by_account: "acc", source: "portal" } }),
    );
    renderIntl(<BoardEngagementDetail detail={detail} reports={[report]} />);
    expect(screen.getByText("Prüfbericht Version 1")).toBeInTheDocument();
    expect(screen.getByText(/Feststellungen: Ohne Beanstandung/)).toBeInTheDocument();
    expect(screen.getByText(/1 geprüft \(120,00 EUR\), 1 ungeprüft \(80,00 EUR\)/)).toBeInTheDocument();
    expect(screen.getByText("Noch keine Stellungnahme erfasst.")).toBeInTheDocument();
    const save = screen.getByRole("button", { name: "Stellungnahme speichern" });
    expect(save).toBeDisabled();
    await user.type(screen.getByLabelText("Text der Stellungnahme"), "Zur Kenntnis genommen.");
    await user.click(save);
    await waitFor(() => expect(screen.getByText("Die Stellungnahme wurde gespeichert.")).toBeInTheDocument(), { timeout: 5000 });
    expect(fetch).toHaveBeenCalledWith(
      "/api/bff/portal/board/engagements/e1/reports/r1/statement",
      expect.objectContaining({ method: "POST" }),
    );
    expect(JSON.parse(vi.mocked(fetch).mock.calls[0]?.[1]?.body as string)).toEqual({ text: "Zur Kenntnis genommen." });
    expect(refresh).toHaveBeenCalled();
    expect(screen.queryByText(/freigeben/i)).not.toBeInTheDocument();
  });

  it("A76: shows an existing statement with time, source and history and allows replacing it", async () => {
    const user = userEvent.setup();
    const withStatement: BoardReport = {
      ...report,
      board_statement: { text: "Ergänzung des Beirats.", recorded_at: "2025-08-02T09:00:00Z", recorded_by_account: "acc", source: "portal" },
      board_statement_history: [{ text: "Erste Fassung.", recorded_at: "2025-08-01T12:00:00Z", recorded_by_account: "acc", source: "portal" }],
    };
    renderIntl(<BoardEngagementDetail detail={detail} reports={[withStatement]} />);
    expect(screen.getByText("Ergänzung des Beirats.")).toBeInTheDocument();
    const meta = screen.getByText(/Erfasst am/);
    expect(meta.textContent).toMatch(/Erfasst am 02\.08\.2025,? 11:00 · über das Portal · eine frühere Fassung/);
    expect(screen.queryByLabelText("Text der Stellungnahme")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Stellungnahme ändern" }));
    expect(screen.getByLabelText("Text der Stellungnahme")).toHaveValue("Ergänzung des Beirats.");
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByLabelText("Text der Stellungnahme")).not.toBeInTheDocument();
  });
});
