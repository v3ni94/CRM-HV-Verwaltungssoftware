import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AuditReportsPanel, type AuditReport } from "./AuditReportsPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));
const AUDIT = "0192abcd-0000-7000-8000-000000000301";
const REPORT = "0192abcd-0000-7000-8000-000000000302";

const report: AuditReport = {
  id: REPORT,
  version: 1,
  created_at: "2026-09-26T10:00:00Z",
  board_statement: null,
  content: {
    overall_status: "Stichprobe geprüft",
    scope_note: "Stichprobe: geprüft sind nur die ausgewählten Positionen.",
    selected: 2,
    checked_count: 2,
    checked_value: "200.00",
    unchecked_count: 0,
    unchecked_value: "0.00",
    findings: "Keine Beanstandung",
    recommendation: null,
  },
};

describe("AuditReportsPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the report figures and records the board statement", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ ...report, board_statement: { text: "x", recorded_at: "2026-09-26T11:00:00Z" } }));
    const user = userEvent.setup();
    renderIntl(<AuditReportsPanel auditId={AUDIT} reports={[report]} />);
    expect(screen.getByText("Prüfbericht Version 1")).toBeInTheDocument();
    expect(screen.getByText("2 Positionen ausgewählt, 2 geprüft (200,00 EUR), 0 nicht geprüft (0,00 EUR).")).toBeInTheDocument();
    expect(screen.getByText("Keine Beanstandung", { exact: false })).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Stellungnahme erfassen" });
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText("Stellungnahme des Beirats"), "Der Beirat nimmt den Bericht zur Kenntnis.");
    await user.click(button);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/hoa/audit-reports/${REPORT}/board-statement`);
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ statement: "Der Beirat nimmt den Bericht zur Kenntnis." });
    expect(refresh).toHaveBeenCalled();
  });

  it("shows an existing statement and creates a new report after confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ id: "r2", version: 2 }, 201));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    renderIntl(
      <AuditReportsPanel auditId={AUDIT} reports={[{ ...report, board_statement: { text: "Zur Kenntnis genommen.", recorded_at: "2026-09-26T11:00:00Z" } }]} />,
    );
    expect(screen.getByText("Zur Kenntnis genommen.", { exact: false })).toBeInTheDocument();
    expect(screen.getByLabelText("Stellungnahme des Beirats ersetzen (bisheriger Text bleibt im Verlauf)")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Feststellungen"), "Zweite Runde");
    await user.click(screen.getByRole("button", { name: "Prüfbericht erstellen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/hoa/audits/${AUDIT}/reports`);
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ findings: "Zweite Runde", recommendation: null });
  });
});
