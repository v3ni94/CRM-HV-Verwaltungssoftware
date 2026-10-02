import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AutoPostingDigests } from "./AutoPostingDigests";

const digest = {
  id: "d1",
  legal_entity_id: "le1",
  week_start: "2026-09-21",
  auto_posted: 7,
  sampled: 2,
  reviews_open: 1,
  findings: 0,
  reconciliation_ok: true,
  confirmed_at: null,
};

describe("AutoPostingDigests", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders the digest rows", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([digest])));
    renderIntl(<AutoPostingDigests canReview={false} />);
    expect(await screen.findByText("21.09.2026")).toBeInTheDocument();
    expect(screen.getByText("unbestätigt")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows the empty state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([])));
    renderIntl(<AutoPostingDigests canReview />);
    expect(await screen.findByText("Kein Wochendigest vorhanden.")).toBeInTheDocument();
  });

  it("confirms a digest and reloads", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse([digest]))
      .mockResolvedValueOnce(jsonResponse({ ...digest, confirmed_at: "2026-09-28T08:00:00Z" }))
      .mockResolvedValueOnce(jsonResponse([{ ...digest, confirmed_at: "2026-09-28T08:00:00Z" }]));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<AutoPostingDigests canReview />);
    const button = await screen.findByRole("button", { name: "Bestätigen" });
    await act(async () => {
      await userEvent.click(button);
    });
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/bff/banking/auto-posting/digests/d1/confirm");
    expect(fetchMock.mock.calls[1]?.[1]?.method).toBe("POST");
    expect(await screen.findByText(/bestätigt am/)).toBeInTheDocument();
  });

  it("shows the API error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<AutoPostingDigests canReview />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
