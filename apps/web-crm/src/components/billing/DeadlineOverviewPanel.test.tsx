import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DeadlineOverviewPanel } from "./DeadlineOverviewPanel";

const ID = "0192abcd-0000-7000-8000-000000000041";
const CID = "0192abcd-0000-7000-8000-000000000042";
const OVERVIEW = {
  policy: "block_claims",
  notice: "Fristende nur zur Orientierung, im Einzelfall zu verifizieren.",
  contracts: [
    {
      contract_id: CID,
      unit_number: "WE 1",
      deadline_orientation: "2026-12-31",
      delivered_at: null,
      access_suggestion: {
        dispatch_id: "d1",
        date: "2026-03-05",
        channel: "post",
        confirmed_delivery: false,
      },
      days_left: 90,
      state: "open",
    },
  ],
};
const SETTINGS = {
  policy: "block_claims",
  watch_enabled: false,
  warn_days_first: 60,
  warn_days_second: 30,
};

describe("DeadlineOverviewPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the orientation and adopts the access only on click", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(OVERVIEW))
      .mockResolvedValueOnce(jsonResponse(SETTINGS))
      .mockResolvedValueOnce(jsonResponse({}))
      .mockResolvedValueOnce(
        jsonResponse({
          ...OVERVIEW,
          contracts: [
            {
              ...OVERVIEW.contracts[0],
              delivered_at: "2026-03-05",
              access_suggestion: null,
              state: "delivered_in_time",
            },
          ],
        }),
      )
      .mockResolvedValueOnce(jsonResponse(SETTINGS));
    renderIntl(<DeadlineOverviewPanel id={ID} canEdit />);
    expect(await screen.findByText("31.12.2026")).toBeInTheDocument();
    expect(screen.getByText(/zu verifizieren/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await userEvent.click(
      screen.getByRole("button", { name: "Zugang übernehmen" }),
    );
    await waitFor(() =>
      expect(fetchMock.mock.calls[2]?.[0]).toContain(`/results/${CID}/delivery`),
    );
    expect(await screen.findByText("Zugang vor Fristende")).toBeInTheDocument();
  });
});
