import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { RestoreReportView } from "./RestoreReportView";

const file = (content: string) => new File([content], "bericht.json", { type: "application/json" });
const report = {
  apply: false,
  counts: {},
  results: [
    { tenant_id: "t", event_id: "e1", document_id: "doc-1", outcome: "would_delete", reason: null },
    { tenant_id: "t", event_id: "e2", document_id: "doc-2", outcome: "kept_hold", reason: "Löschungssperre gesetzt" },
    { tenant_id: "t", event_id: "e3", document_id: "doc-3", outcome: "absent", reason: null },
    { tenant_id: "t", event_id: "e4", document_id: "doc-4", outcome: "mystery", reason: null },
  ],
};

describe("RestoreReportView", () => {
  it("shows replayed deletions and deliberately kept holds per group", async () => {
    renderIntl(<RestoreReportView />);
    await userEvent.upload(screen.getByLabelText("Berichtsdatei (JSON)"), file(JSON.stringify(report)));
    await waitFor(() => expect(screen.getByTestId("restore-mode")).toHaveTextContent("Nur Prüfung"));
    expect(screen.getByTestId("restore-mode")).toHaveTextContent("Einträge im Bericht: 4");
    expect(within(screen.getByTestId("restore-group-replayed")).getByText("doc-1")).toBeInTheDocument();
    const kept = screen.getByTestId("restore-group-kept");
    expect(within(kept).getByText("erhalten wegen Löschungssperre")).toBeInTheDocument();
    expect(within(kept).getByText("Löschungssperre gesetzt")).toBeInTheDocument();
    const review = screen.getByTestId("restore-group-review");
    expect(within(review).getByText("Unbekannter Ergebnistyp: mystery")).toBeInTheDocument();
    expect(screen.getByText(/brauchen eine Entscheidung durch Datenschutz/)).toBeInTheDocument();
  });

  it("rejects a file that is no replay report and can clear the view", async () => {
    renderIntl(<RestoreReportView />);
    await userEvent.upload(screen.getByLabelText("Berichtsdatei (JSON)"), file("{}"));
    expect(await screen.findByRole("alert")).toHaveTextContent("kein gültiger Bericht");
    await userEvent.upload(screen.getByLabelText("Berichtsdatei (JSON)"), file(JSON.stringify({ ...report, apply: true })));
    expect(await screen.findByTestId("restore-mode")).toHaveTextContent("Angewendet");
    await userEvent.click(screen.getByRole("button", { name: "Anzeige leeren" }));
    expect(screen.queryByTestId("restore-mode")).toBeNull();
  });
});
