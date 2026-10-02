import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DunningInterestRates } from "./DunningInterestRates";

const info = (stale: boolean) => ({
  day_count: "act_365_fixed",
  day_counts: { act_365_fixed: "Tage durch 365 (fest, auch im Schaltjahr)", act_act: "Tage durch tatsächliche Jahrestage" },
  base_rate_stale: stale,
  base_rate_hint: stale ? "Kein Basiszinssatz gepflegt" : null,
  next_change_dates: ["2027-01-01", "2027-07-01"],
});

function route(stale: boolean) {
  return vi.fn((url: string) => {
    if (url.endsWith("/dunning-interest")) return Promise.resolve(jsonResponse(info(stale)));
    if (url.endsWith("/base-rate-checkpoints")) return Promise.resolve(jsonResponse([{ id: "1" }, { id: "2" }]));
    return Promise.resolve(jsonResponse([]));
  });
}

describe("DunningInterestRates (AI03)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the day count and the stale hint and seeds the check points", async () => {
    const fetchMock = route(true);
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<DunningInterestRates />);
    expect(await screen.findByTestId("dunning-day-count")).toHaveTextContent("Tage durch 365");
    const hint = await screen.findByTestId("dunning-rate-stale");
    expect(hint).toHaveTextContent("Kein Basiszinssatz gepflegt");
    expect(hint).toHaveTextContent("01.01.2027");
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: /Prüfpunkte/ }));
    });
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/base-rate-checkpoints"))).toBe(true);
    expect(await screen.findByText(/2 Prüfpunkte/)).toBeInTheDocument();
  });

  it("shows no hint when the rate of the current half year is maintained", async () => {
    vi.stubGlobal("fetch", route(false));
    renderIntl(<DunningInterestRates />);
    await screen.findByTestId("dunning-day-count");
    expect(screen.queryByTestId("dunning-rate-stale")).toBeNull();
  });
});
