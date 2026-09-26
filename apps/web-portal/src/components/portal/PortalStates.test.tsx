/** Bedienbarkeitsprüfung 26.09.2026: leere Zustände, Fehlermeldungen, Formate und
 *  Barrierefreiheit der Portalseiten (docs/reviews/2026-09-26-portal-bedienbarkeit.md). */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BoardEngagementDetail } from "./BoardEngagementDetail";
import { HoaAccountTable } from "./HoaAccountTable";
import { PortalForms } from "./PortalForms";
import { ResolutionList } from "./ResolutionList";
import { TicketComments } from "./TicketComments";
import { WorkOrderDetail } from "./WorkOrderDetail";
import type { BoardEngagementDetail as Detail, HoaAccount, PortalForm, WorkOrder } from "./types";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh }),
}));

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
  refresh.mockReset();
});

describe("HoaAccountTable states", () => {
  const account: HoaAccount = {
    note: "Keine Abrechnung.",
    legacy_note: null,
    contracts: [
      {
        contract_number: "WEG-1",
        note: null,
        charges: "1534.56",
        credits: "300.00",
        balance: "1234.56",
        entries: [
          { booking_date: "2026-02-01", due_date: null, text: "Hausgeld Februar", kind: "charge", direction: "charge", amount: "1234.56", reversed: true },
          { booking_date: "2026-02-01", due_date: null, text: "Hausgeld Februar", kind: "charge", direction: "charge", amount: "300.00", reversed: false },
          { booking_date: "2026-02-05", due_date: null, text: "Zahlung", kind: "payment", direction: "credit", amount: "300.00", reversed: false },
        ],
      },
    ],
  };

  it("shows the empty notice without contracts and keeps the API note", () => {
    renderIntl(<HoaAccountTable account={{ ...account, contracts: [] }} />);
    expect(screen.getByText("Keine Abrechnung.")).toBeInTheDocument();
    expect(screen.getByText("Kein Eigentumsvertrag zugeordnet.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("renders a scrollable table with caption, column headers, formatted amounts and a reversal hint", () => {
    renderIntl(<HoaAccountTable account={account} />);
    const table = screen.getByRole("table", { name: /Gebuchte Sollstellungen und Zahlungen WEG-1/ });
    expect(table.parentElement).toHaveClass("overflow-x-auto");
    expect(screen.getAllByRole("columnheader")).toHaveLength(4);
    expect(screen.getAllByText("1.234,56 EUR").length).toBeGreaterThan(0);
    // The reversal hint exists once in the card (below md) and once in the table (from md).
    const hints = screen.getAllByText("(storniert)");
    expect(hints).toHaveLength(2);
    hints.forEach((hint) => expect(hint).toHaveClass("sr-only"));
    expect(screen.getByText("(offener Betrag)")).toBeInTheDocument();
  });
});

describe("WorkOrderDetail states", () => {
  const order: WorkOrder = {
    id: "o1",
    description: "Heizung reparieren",
    status: "approved",
    quote_amount: "1234.5",
    scheduled_at: null,
    appointment_proposals: [],
    photos: [],
  };

  it("has a page heading and shows the quote amount as 1.234,56 EUR", () => {
    renderIntl(<WorkOrderDetail order={order} />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Heizung reparieren");
    expect(screen.getByText("1.234,50 EUR")).toBeInTheDocument();
  });

  it("names the missing input instead of failing silently", async () => {
    const user = userEvent.setup();
    renderIntl(<WorkOrderDetail order={order} />);
    await user.click(screen.getByRole("button", { name: "Angebot abgeben" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte den Angebotsbetrag eingeben.");
    await user.click(screen.getByRole("button", { name: "Termin festlegen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte einen Termin auswählen.");
    await user.click(screen.getByRole("button", { name: "Ausführung dokumentieren" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte den Ausführungsbericht eingeben.");
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Angebotsbetrag (EUR)")).toHaveAttribute("aria-required", "true");
  });

  it("falls back to the raw status for unknown values", () => {
    renderIntl(<WorkOrderDetail order={{ ...order, status: "unbekannt" }} />);
    expect(screen.getByText("unbekannt")).toBeInTheDocument();
  });
});

describe("PortalForms accessibility", () => {
  const form: PortalForm = {
    id: "f1",
    name: "Antrag Tierhaltung",
    description: null,
    audience: "all",
    fields: [{ key: "art", label: "Tierart", type: "text", required: true, options: null }],
  };

  it("moves focus to the opened form, marks required fields and explains the asterisk", async () => {
    const user = userEvent.setup();
    renderIntl(<PortalForms forms={[form]} />);
    await user.click(screen.getByRole("button", { name: /Antrag Tierhaltung/ }));
    expect(screen.getByRole("heading", { name: "Antrag Tierhaltung" })).toHaveFocus();
    expect(screen.getByText("Mit * gekennzeichnete Felder sind Pflichtfelder.")).toBeInTheDocument();
    expect(screen.getByLabelText("Tierart *")).toHaveAttribute("aria-required", "true");
  });
});

describe("TicketComments states", () => {
  it("shows the empty history and announces an API error", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ title: "Fehler", status: 422, detail: "Text zu lang." }, 422));
    renderIntl(<TicketComments ticketId="t1" comments={[]} />);
    expect(screen.getByText("Keine Meldungen vorhanden.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Nachricht"), "Hallo");
    await user.click(screen.getByRole("button", { name: "Senden" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Text zu lang.");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("announces the sent comment as status", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: "c1" }, 201));
    renderIntl(<TicketComments ticketId="t1" comments={["Erste Nachricht"]} />);
    await user.type(screen.getByLabelText("Nachricht"), "Hallo");
    await user.click(screen.getByRole("button", { name: "Senden" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Nachricht wurde gesendet."));
  });
});

describe("BoardEngagementDetail states", () => {
  const detail: Detail = {
    id: "e1",
    legal_entity_id: "le1",
    legal_entity_name: "WEG Test",
    statement_id: null,
    period_from: "2025-01-01",
    period_to: "2025-12-31",
    purpose: "Jahresabrechnung 2025",
    sampling: "sample",
    status: "open",
    snapshot_hash: null,
    overall_status: "open",
    population: {},
    positions: [],
    cost_items: [{ id: "c1", label: "Versicherung", amount: "12345.67", basis: "MEA" }],
    documents: [],
    notes: [],
    read_receipt_note: "Abruf wird protokolliert.",
  };

  it("translates the overall status, formats the period and wraps the cost table for scrolling", () => {
    renderIntl(<BoardEngagementDetail detail={detail} />);
    expect(screen.getByText("Offen")).toBeInTheDocument();
    expect(screen.getByText(/Zeitraum 01\.01\.2025 bis 31\.12\.2025/)).toBeInTheDocument();
    expect(screen.getByText("Noch keine Positionen ausgewählt.")).toBeInTheDocument();
    expect(screen.getByText("Zu den Positionen sind keine Belege freigegeben.")).toBeInTheDocument();
    expect(screen.getByText("Noch keine Vermerke oder Rückfragen.")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Abrechnungspositionen des Prüfauftrags" });
    expect(table.parentElement).toHaveClass("overflow-x-auto");
    expect(screen.getByText("12.345,67 EUR")).toBeInTheDocument();
  });

  it("shows the API error of a note as alert", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ title: "Fehler", status: 409, detail: "Prüfauftrag abgeschlossen." }, 409));
    renderIntl(<BoardEngagementDetail detail={detail} />);
    await user.type(screen.getByLabelText("Text"), "Rückfrage");
    await user.click(screen.getByRole("button", { name: "Absenden" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Prüfauftrag abgeschlossen.");
  });
});

describe("ResolutionList fallbacks", () => {
  it("renders unknown kind and status values without crashing", () => {
    renderIntl(
      <ResolutionList
        rows={[
          {
            id: "r1",
            number: 1,
            decided_on: "2026-01-15",
            subject: "Test",
            wording: "Text",
            status: "sonstig",
            kind: "sonderform",
            majority_basis: null,
            votes: null,
            legal_entity_name: null,
          },
        ]}
      />,
    );
    expect(screen.getByText("sonstig")).toBeInTheDocument();
    expect(screen.getByText(/15\.01\.2026 · sonderform/)).toBeInTheDocument();
  });
});
