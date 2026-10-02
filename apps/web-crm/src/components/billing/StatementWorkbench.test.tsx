import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ResultTable, StatementWorkbench } from "./StatementWorkbench";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
const ID = "0192abcd-0000-7000-8000-000000000011";
const KEYS = [{ id: "0192abcd-0000-7000-8000-000000000012", code: "WFL", name: "Wohnfläche" }];

describe("StatementWorkbench", () => {
  afterEach(() => vi.restoreAllMocks());

  it("adds a cost item only with a basis and a valid amount", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}, 201));
    renderIntl(<StatementWorkbench id={ID} status="draft" keys={KEYS} />);
    const add = screen.getByText("Position hinzufügen");
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Hausmeister");
    await userEvent.type(screen.getByLabelText("Betrag"), "2000,00");
    expect(add).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Grundlage"), "Mietvertrag Anlage");
    await userEvent.click(add);
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({
      label: "Hausmeister",
      amount: "2000.00",
      allocation_key_id: KEYS[0]?.id,
      basis: "Mietvertrag Anlage",
    });
  });

  it("issues only with a delivery date and shows the G3 refusal", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ title: "Freigabestufe", status: 403, detail: "Freigabestufe G3 ist nicht erteilt." }, 403),
    );
    renderIntl(<StatementWorkbench id={ID} status="internally_approved" keys={KEYS} />);
    expect(screen.getByText("Ausgeben")).toBeDisabled();
    expect(screen.getByTestId("gate-g3-hint")).toHaveTextContent("Freigabestufe G3");
    await userEvent.type(screen.getByLabelText("Zugang beim Mieter"), "2026-09-30");
    await userEvent.click(screen.getByText("Ausgeben"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("StatementWorkbench hints", () => {
  it("explains that a second person approves internally", () => {
    renderIntl(<StatementWorkbench id={ID} status="calculated" keys={KEYS} />);
    expect(screen.getByText("Intern freigeben")).toBeInTheDocument();
    expect(screen.getByText(/zweite Person/)).toBeInTheDocument();
  });
});

describe("ResultTable", () => {
  it("renders results in euro", () => {
    renderIntl(<ResultTable rows={[{ unit_number: "01", costs: "700.00", advances_due: "100.00", advances_paid: "100.00", balance: "600.00" }]} />);
    expect(screen.getByText("01")).toBeInTheDocument();
    expect(screen.getAllByText(/100,00/).length).toBe(2);
  });
});

describe("StatementWorkbench period locks", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the active period locks of the property read only", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse([{ id: "l1", period_from: "2025-01-01", period_to: "2025-12-31", source: "manual", reason: "Abschluss 2025", active: true }]),
    );
    renderIntl(<StatementWorkbench id={ID} status="draft" keys={KEYS} propertyId="0192abcd-0000-7000-8000-000000000099" />);
    await waitFor(() => expect(screen.getByTestId("period-locks")).toHaveTextContent("Abschluss 2025"));
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/bff/accounting/period-locks?property_id=0192abcd-0000-7000-8000-000000000099&active=true");
  });
});

describe("StatementWorkbench period lock of the statement (GAG-11)", () => {
  afterEach(() => vi.restoreAllMocks());
  const PROP = "0192abcd-0000-7000-8000-000000000099";
  const LEDGER = "0192abcd-0000-7000-8000-000000000098";

  it("shows the statement lock and creates a lock for the statement period", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes(`/statements/${ID}/period-lock`)) return jsonResponse({ locks: [], auto_lock_on_close: false, lock_mode: "hard" });
      if (init?.method === "POST") return jsonResponse({ id: "l2" }, 201);
      return jsonResponse([]);
    });
    renderIntl(
      <StatementWorkbench id={ID} status="issued" keys={KEYS} propertyId={PROP} ledgerId={LEDGER} periodFrom="2025-01-01" periodTo="2025-12-31" />,
    );
    await waitFor(() => expect(screen.getByTestId("statement-period-lock")).toHaveTextContent("noch keine Periodensperre"));
    const create = screen.getByText("Zeitraum 01.01.2025 bis 31.12.2025 sperren");
    expect(create).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Grund der Sperre"), "Abrechnung 2025");
    await userEvent.click(create);
    await waitFor(() => expect(screen.getByText("Periodensperre angelegt.")).toBeInTheDocument());
    const post = fetchMock.mock.calls.find((c) => c[1]?.method === "POST");
    expect(String(post?.[0])).toContain("/api/bff/accounting/period-locks");
    expect(JSON.parse(post?.[1]?.body as string)).toEqual({
      ledger_id: LEDGER,
      property_id: PROP,
      period_from: "2025-01-01",
      period_to: "2025-12-31",
      reason: "Abrechnung 2025",
    });
  });
});
