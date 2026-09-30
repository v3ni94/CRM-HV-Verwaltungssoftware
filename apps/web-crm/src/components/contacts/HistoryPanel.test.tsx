import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { HistoryPanel } from "./HistoryPanel";

describe("HistoryPanel", () => {
  it("lists mail, dispatch and ticket entries with their kind and status", () => {
    renderIntl(
      <HistoryPanel
        events={[
          { kind: "dispatch_registered", at: "2026-09-29T10:00:00Z", title: "Mahnung", id: "d1", status: "delivered" },
          { kind: "email_in", at: "2026-09-28T08:00:00Z", title: "Frage zur Abrechnung", id: "m1", status: "received" },
          { kind: "ticket", at: "2026-09-27T08:00:00Z", title: "Heizung", id: "t1", status: "open" },
        ]}
      />,
    );
    expect(screen.getByText("Zustellung Einschreiben")).toBeInTheDocument();
    expect(screen.getByText("E-Mail eingehend")).toBeInTheDocument();
    expect(screen.getByText("Status delivered")).toBeInTheDocument();
    expect(screen.getByText("Heizung")).toBeInTheDocument();
  });

  it("shows a neutral text without entries", () => {
    renderIntl(<HistoryPanel events={[]} />);
    expect(screen.getByText("Keine Kommunikation erfasst.")).toBeInTheDocument();
  });
});
