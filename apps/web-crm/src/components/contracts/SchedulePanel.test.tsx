import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import type { ScheduleOut } from "./ContractForm";
import { SchedulePanel } from "./SchedulePanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

const CONTRACT = "01920000-0000-7000-8000-0000000000s1";
const plan: ScheduleOut = { id: "p1", interval: "monthly", due_day_rule: "day", due_day: 3, valid_from: "2026-01-01", valid_to: null, payment_mode: "advance", amount_basis: "per_month" };

describe("SchedulePanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the plans and sends only a PATCH with the corrected due day", async () => {
    const user = userEvent.setup();
    const calls: { url: string; method: string; body: Record<string, unknown> }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push({ url: String(input), method: init?.method ?? "GET", body: JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown> });
      return jsonResponse({ ...plan, due_day: 5 });
    });
    renderIntl(<SchedulePanel contractId={CONTRACT} schedules={[plan]} canUpdate />);
    expect(screen.getAllByTestId("schedule-row")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Korrigieren" }));
    const day = screen.getByLabelText("Fälligkeitstag");
    await user.clear(day);
    await user.type(day, "5");
    await user.click(screen.getByRole("button", { name: "Korrektur speichern" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]!.url).toBe(`/api/bff/contracts/${CONTRACT}/schedules/p1`);
    expect(calls[0]!.method).toBe("PATCH");
    expect(calls[0]!.body).toMatchObject({ due_day: 5, interval: "monthly", valid_to: null });
    await waitFor(() => expect(screen.queryByTestId("schedule-correction-form")).toBeNull());
    expect(refresh).toHaveBeenCalled();
  });

  it("shows the API message when the plan is locked by posted receivables (409)", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "Der Zahlungsplan ist bereits Grundlage gebuchter Sollstellungen." }, 409));
    renderIntl(<SchedulePanel contractId={CONTRACT} schedules={[plan]} canUpdate />);
    await user.click(screen.getByRole("button", { name: "Korrigieren" }));
    await user.click(screen.getByRole("button", { name: "Korrektur speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("gebuchter Sollstellungen");
  });

  it("blocks an invalid due day and hides the button without update right", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const { unmount } = renderIntl(<SchedulePanel contractId={CONTRACT} schedules={[plan]} canUpdate />);
    await user.click(screen.getByRole("button", { name: "Korrigieren" }));
    const day = screen.getByLabelText("Fälligkeitstag");
    await user.clear(day);
    await user.type(day, "32");
    expect(screen.getByRole("button", { name: "Korrektur speichern" })).toBeDisabled();
    expect(fetchSpy).not.toHaveBeenCalled();
    unmount();
    renderIntl(<SchedulePanel contractId={CONTRACT} schedules={[plan]} canUpdate={false} />);
    expect(screen.queryByRole("button", { name: "Korrigieren" })).toBeNull();
  });
});
