import { screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CircularPortalVotes } from "./CircularPortalVotes";

const OWNERS = [{ id: "c1", label: "WE 01" }];
const VOTE = { id: "v1", meeting_id: "m1", item_title: "Fassadenanstrich", contract_id: "c1", choice: "no", cast_at: "2026-11-05T10:00:00Z", wording_sha256: null };

describe("CircularPortalVotes", () => {
  afterEach(() => vi.restoreAllMocks());

  it("requests the votes of the legal entity and renders nothing for an empty list", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
    renderIntl(<CircularPortalVotes legalEntityId="le 1" owners={OWNERS} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/bff/hoa/portal-circular-votes?legal_entity_id=le%201");
    expect(screen.queryByTestId("circular-portal-votes")).not.toBeInTheDocument();
  });

  it("renders nothing when the API answers with an error", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Forbidden", status: 403 }, 403));
    renderIntl(<CircularPortalVotes legalEntityId="e" owners={OWNERS} />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByTestId("circular-portal-votes")).not.toBeInTheDocument();
  });

  it("shows the vote read only and falls back to the short id for unknown owners", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([VOTE, { ...VOTE, id: "v2", contract_id: "abcdef1234567", choice: "abstain" }]));
    renderIntl(<CircularPortalVotes legalEntityId="e" owners={OWNERS} />);
    expect(await screen.findByTestId("circular-portal-votes")).toBeInTheDocument();
    expect(screen.getByText(/WE 01: Fassadenanstrich, Nein/)).toBeInTheDocument();
    expect(screen.getByText(/abcdef12: Fassadenanstrich, Enthaltung/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
