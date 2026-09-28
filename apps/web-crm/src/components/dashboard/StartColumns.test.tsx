import { screen, within } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { ApprovalsColumn } from "./ApprovalsColumn";
import { KpiStrip } from "./KpiStrip";
import { MyTicketsColumn } from "./MyTicketsColumn";
import { TodayColumn } from "./TodayColumn";

describe("TodayColumn", () => {
  it("shows the German empty state", () => {
    renderIntl(<TodayColumn items={[]} today="2026-09-27" />);
    expect(screen.getByText("Für heute und die nächsten sieben Tage liegt nichts an.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zum Kalender" })).toHaveAttribute("href", "/kalender");
  });

  it("groups today and the next seven days, sorted by date, with source links", () => {
    renderIntl(
      <TodayColumn
        today="2026-09-27"
        items={[
          { id: "d1", date: "2026-10-02", title: "Zähler 4711", kind: "meter_calibration", source: "deadline", href: "/fristen" },
          { id: "c1", date: "2026-09-27", title: "Begehung Musterstraße", kind: "appointment", source: "calendar", href: "/kalender" },
          { id: "c2", date: "2026-09-29", title: "Übergabe", kind: "appointment", source: "calendar", href: null },
        ]}
      />,
    );
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(["Heute", "Nächste sieben Tage"]);
    expect(screen.getByRole("link", { name: /Begehung Musterstraße/ })).toHaveAttribute("href", "/kalender");
    expect(screen.getByRole("link", { name: /Zähler 4711/ })).toHaveAttribute("href", "/fristen");
    expect(screen.getByText("Eichfrist Zähler")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Übergabe/ })).toBeNull();
    const dates = screen.getAllByText(/^\d{2}\.\d{2}\.\d{4}$/).map((e) => e.textContent);
    expect(dates).toEqual(["27.09.2026", "29.09.2026", "02.10.2026"]);
  });
});

describe("MyTicketsColumn", () => {
  it("shows the German empty state and the link to the full list", () => {
    renderIntl(<MyTicketsColumn tickets={[]} listHref="/tickets?assignee_user_id=u1&sort=urgency" />);
    expect(screen.getByText("Ihnen ist kein offenes Ticket zugewiesen.")).toBeInTheDocument();
    expect(screen.getByTestId("my-tickets-all")).toHaveAttribute("href", "/tickets?assignee_user_id=u1&sort=urgency");
  });

  it("keeps the urgency order of the server, colours by attention and counts the rest", () => {
    renderIntl(
      <MyTicketsColumn
        listHref="/tickets"
        total={12}
        tickets={[
          { id: "a", number: 7, title: "Heizung kalt", status: "in_progress", priority: "high", sla_due_at: "2026-09-28T10:00:00Z", attention: "stale_96h", last_activity_at: null },
          { id: "b", number: 9, title: null, status: "new", priority: "normal", sla_due_at: null, attention: "new", last_activity_at: null },
        ]}
      />,
    );
    const rows = screen.getAllByTestId("my-ticket");
    expect(rows).toHaveLength(2);
    const [first, second] = rows as [HTMLElement, HTMLElement];
    expect(first).toHaveAttribute("data-attention", "stale_96h");
    expect(within(first).getByRole("link")).toHaveAttribute("href", "/tickets/a");
    expect(within(first).getByRole("link").className).toContain("border-l-signal-critical");
    expect(within(first).getByText("fällig 28.09.2026")).toBeInTheDocument();
    expect(within(second).getByText("ohne Titel")).toBeInTheDocument();
    expect(screen.getByText("und 10 weitere")).toBeInTheDocument();
  });

  it("shows at most four tickets and the remaining count via the server limit", () => {
    const tickets = Array.from({ length: 4 }, (_, i) => ({
      id: `t${i}`,
      number: i + 1,
      title: `Ticket ${i + 1}`,
      status: "new",
      priority: "normal",
      sla_due_at: null,
    }));
    renderIntl(<MyTicketsColumn tickets={tickets} listHref="/tickets" total={7} />);
    expect(screen.getAllByTestId("my-ticket")).toHaveLength(4);
    expect(screen.getByText("und 3 weitere")).toBeInTheDocument();
  });

  it("shows the fallback notice when the tenant's most urgent tickets replace an empty assignment", () => {
    renderIntl(
      <MyTicketsColumn
        listHref="/tickets"
        fallback
        tickets={[{ id: "a", number: 3, title: "Wasserschaden", status: "new", priority: "high", sla_due_at: null }]}
      />,
    );
    expect(screen.getByTestId("my-tickets-fallback")).toHaveTextContent(
      "Ihnen ist kein Ticket zugewiesen, hier die dringendsten offenen Tickets des Mandanten.",
    );
  });

  it("does not show the fallback notice for an empty tenant-wide result either", () => {
    renderIntl(<MyTicketsColumn tickets={[]} listHref="/tickets" fallback />);
    expect(screen.queryByTestId("my-tickets-fallback")).toBeNull();
    expect(screen.getByText("Ihnen ist kein offenes Ticket zugewiesen.")).toBeInTheDocument();
  });
});

describe("ApprovalsColumn", () => {
  it("tells a role without approval rights that it decides nothing", () => {
    renderIntl(<ApprovalsColumn counts={{}} />);
    expect(screen.getByText("Ihre Rolle entscheidet keine Freigaben.")).toBeInTheDocument();
  });

  it("shows the empty state when every count is zero", () => {
    renderIntl(<ApprovalsColumn counts={{ mail: 0, dunning_runs: 0 }} />);
    expect(screen.getByText("Nichts wartet auf Ihre Freigabe.")).toBeInTheDocument();
    expect(screen.queryByTestId("approval-mail")).toBeNull();
  });

  it("renders one action tile per pending kind with count and link", () => {
    renderIntl(<ApprovalsColumn counts={{ mail: 3, bank_accounts: 0, direct_debits: 1, metering_transmissions: 2 }} />);
    expect(screen.queryByTestId("approval-bank_accounts")).toBeNull();
    const mail = within(screen.getByTestId("approval-mail"));
    expect(mail.getByRole("link", { name: /Mail-Antworten/ })).toHaveAttribute("href", "/mail");
    expect(mail.getByText("3")).toBeInTheDocument();
    expect(within(screen.getByTestId("approval-direct_debits")).getByRole("link")).toHaveAttribute("href", "/bank/lastschriften");
    expect(screen.getByText("Übermittlungen Messdienstleister")).toBeInTheDocument();
  });
});

describe("KpiStrip", () => {
  it("renders linked chips and the analytics link", () => {
    renderIntl(<KpiStrip tiles={{ properties: 67, documents: 3 }} analyticsHref="/auswertung/tickets" />);
    expect(screen.getByRole("link", { name: /67/ })).toHaveAttribute("href", "/objekte");
    expect(screen.getByTestId("tile-documents").querySelector("a")).toBeNull();
    expect(screen.getByRole("link", { name: "Auswertung Tickets" })).toHaveAttribute("href", "/auswertung/tickets");
  });
});
