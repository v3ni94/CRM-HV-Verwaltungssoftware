import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CircularVotePanel, type CircularListing } from "./CircularVotePanel";

const CID = "00000000-0000-7000-8000-000000000007";
const U1 = "00000000-0000-7000-8000-0000000000a1";

function listing(over: Partial<CircularListing> = {}): CircularListing {
  return {
    enabled: true,
    note: "Hinweis",
    circulars: [
      {
        id: CID,
        deadline: "2026-12-10T17:00:00Z",
        description: null,
        own_contract_ids: [U1],
        items: [
          { id: "i1", position: 1, title: "Fassadenanstrich", proposal: "Anstrich 2027", wording_sha256: "ab12", open: true, own_votes: [] },
          {
            id: "i2",
            position: 2,
            title: "Hausordnung",
            proposal: null,
            wording_sha256: "cd34",
            open: true,
            own_votes: [{ agenda_item_id: "i2", contract_id: U1, choice: "yes", cast_at: "2026-11-05T10:00:00Z", wording_sha256: "cd34" }],
          },
        ],
      },
    ],
    ...over,
  };
}

describe("CircularVotePanel", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn()));

  it("shows the disabled note when the tenant switch is off", async () => {
    vi.mocked(fetch).mockImplementation(() => Promise.resolve(jsonResponse(listing({ enabled: false, circulars: [] }))));
    renderIntl(<CircularVotePanel />);
    expect(await screen.findByText(/nicht freigeschaltet/)).toBeInTheDocument();
  });

  it("shows evidence of a cast vote and votes once per unit", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockImplementation(() => Promise.resolve(jsonResponse(listing())));
    renderIntl(<CircularVotePanel />);
    expect(await screen.findByText(/Prüfsumme des Beschlusstexts cd34/)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Ja" })).toHaveLength(1);
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ id: "v1" }, 201)).mockImplementation(() => Promise.resolve(jsonResponse(listing())));
    await user.click(screen.getByRole("button", { name: "Nein" }));
    await waitFor(() =>
      expect(
        vi.mocked(fetch).mock.calls.some(
          ([url, init]) =>
            url === `/api/bff/portal/circular-resolutions/${CID}/vote` &&
            (init as RequestInit).body === JSON.stringify({ agenda_item_id: "i1", contract_id: U1, choice: "no" }),
        ),
      ).toBe(true),
    );
  });

  it("shows the owners only note on 403", async () => {
    vi.mocked(fetch).mockImplementation(() => Promise.resolve(jsonResponse({ code: "MHVP-AUTH" }, 403)));
    renderIntl(<CircularVotePanel />);
    expect(await screen.findByText("Nur für Eigentümer verfügbar.")).toBeInTheDocument();
  });
});
