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
    await userEvent.type(screen.getByLabelText("Zugang beim Mieter"), "2026-09-30");
    await userEvent.click(screen.getByText("Ausgeben"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("ResultTable", () => {
  it("renders results in euro", () => {
    renderIntl(<ResultTable rows={[{ unit_number: "01", costs: "700.00", advances_due: "100.00", advances_paid: "100.00", balance: "600.00" }]} />);
    expect(screen.getByText("01")).toBeInTheDocument();
    expect(screen.getAllByText(/100,00/).length).toBe(2);
  });
});
