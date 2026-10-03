import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LevyRefunds, type LevyRefund } from "./LevyRefunds";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));
const LV = "0192abcd-0000-7000-8000-000000000071";
const UNITS = [{ unit_id: "u1", unit_number: "01" }];
const RES = [{ id: "r1", decided_on: "2026-06-01", subject: "Teilerstattung" }];
const REFUND: LevyRefund = {
  id: "f1",
  unit_id: "u1",
  amount: "1000.00",
  reason: "Kosten geringer",
  resolution_id: "r1",
  status: "proposed",
  withdrawn_reason: null,
  payout_locked: true,
  note: "",
};

describe("LevyRefunds (AP21, GAM-110)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("records a proposal with resolution and reason, never a payout", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: "f2" }, 201));
    renderIntl(<LevyRefunds levyId={LV} refunds={[]} units={UNITS} resolutions={RES} enabled />);
    expect(screen.getByText(/bleibt gesperrt/)).toBeInTheDocument();
    expect(screen.getByText("Keine Erstattungsvorschläge.")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Einheit"), "u1");
    await userEvent.type(screen.getByLabelText("Betrag"), "250,50");
    await userEvent.type(screen.getByLabelText("Grund"), "Kosten geringer");
    await userEvent.click(screen.getByText("Vorschlag erfassen"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/hoa/special-levies/${LV}/refunds`);
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ unit_id: "u1", amount: "250.50", reason: "Kosten geringer", resolution_id: "r1" });
  });

  it("shows the API problem when the switch is off on the server", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Erstattungsvorschläge zur Sonderumlage sind nicht freigeschaltet", status: 409 }, 409));
    renderIntl(<LevyRefunds levyId={LV} refunds={[]} units={UNITS} resolutions={RES} enabled={null} />);
    await userEvent.type(screen.getByLabelText("Betrag"), "10");
    await userEvent.type(screen.getByLabelText("Grund"), "Test");
    await userEvent.click(screen.getByText("Vorschlag erfassen"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("hides the form when the switch is off and withdraws a proposal", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...REFUND, status: "withdrawn" }));
    vi.spyOn(window, "prompt").mockReturnValue("Beschluss aufgehoben");
    renderIntl(<LevyRefunds levyId={LV} refunds={[REFUND, { ...REFUND, id: "f0", unit_id: null, status: "withdrawn", withdrawn_reason: "alt" }]} units={UNITS} resolutions={[]} enabled={false} />);
    expect(screen.getByTestId("levy-refunds-off")).toBeInTheDocument();
    expect(screen.queryByText("Vorschlag erfassen")).toBeNull();
    expect(screen.getByText(/Alle Einheiten/)).toBeInTheDocument();
    await userEvent.click(screen.getByText("Zurückziehen"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/hoa/special-levies/${LV}/refunds/f1/withdraw`);
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ reason: "Beschluss aufgehoben" });
  });

  it("ignores a too short withdraw reason", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    vi.spyOn(window, "prompt").mockReturnValue("x");
    renderIntl(<LevyRefunds levyId={LV} refunds={[REFUND]} units={UNITS} resolutions={RES} enabled />);
    await userEvent.click(screen.getByText("Zurückziehen"));
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
