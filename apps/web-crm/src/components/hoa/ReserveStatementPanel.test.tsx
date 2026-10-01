import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ReserveStatementPanel } from "./ReserveStatementPanel";

const LEDGER = "0192abcd-0000-7000-8000-000000000031";
const HOA = "0192abcd-0000-7000-8000-000000000032";
const ID = "0192abcd-0000-7000-8000-000000000033";
const ROW = {
  id: ID,
  ledger_id: LEDGER,
  hoa_statement_id: HOA,
  year: 2025,
  status: "calculated",
  snapshot: { reserve: { opening: "1000.00", closing: "1000.00" }, positions: [] },
  source_snapshot_hash: "h",
  status_log: [],
};

describe("ReserveStatementPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates a reserve statement and shows the figures and actions", async () => {
    let created = false;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "POST") {
        created = true;
        return jsonResponse(ROW, 201);
      }
      return jsonResponse(created ? [ROW] : []);
    });
    renderIntl(<ReserveStatementPanel ledgerId={LEDGER} hoaStatementId={HOA} />);
    expect(await screen.findByText("Noch keine Rücklagenabrechnung.")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Aus der jüngsten Hausgeldabrechnung anlegen"));
    expect(await screen.findByText("Rücklagenabrechnung 2025")).toBeInTheDocument();
    expect(screen.getByText("Endbestand")).toBeInTheDocument();
    expect(screen.getAllByText(/1\.000,00/).length).toBeGreaterThan(0);
    expect(screen.getByText("Intern freigeben (zweite Person)")).toBeInTheDocument();
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([, i]) => JSON.parse(String(i?.body ?? "{}")).hoa_statement_id === HOA)).toBe(true),
    );
  });
});
