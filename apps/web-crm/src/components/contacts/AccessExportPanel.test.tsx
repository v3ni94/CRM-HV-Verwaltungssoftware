import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AccessExportPanel } from "./AccessExportPanel";

const base = {
  id: "e1",
  prepared_at: "2026-10-01T08:00:00Z",
  prepared_by: "u1",
  reviewed_by: null,
  released_by: null,
  downloads: 0,
  rejected_reason: null,
};

describe("AccessExportPanel (AC07, GA08-06)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("offers no download before release, only review", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([{ ...base, status: "prepared" }]));
    renderIntl(<AccessExportPanel contactId="c1" />);
    expect(await screen.findByRole("button", { name: "Als geprüft markieren" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Herunterladen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Zur Herausgabe freigeben" })).not.toBeInTheDocument();
  });

  it("posts the review and shows download once released", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([{ ...base, status: "reviewed" }]))
      .mockResolvedValueOnce(jsonResponse({ ...base, status: "released" }))
      .mockResolvedValueOnce(jsonResponse([{ ...base, status: "released" }]));
    renderIntl(<AccessExportPanel contactId="c1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Zur Herausgabe freigeben" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("/api/bff/contacts/c1/access-exports/e1/approve");
    expect(init.method).toBe("POST");
    expect(await screen.findByRole("button", { name: "Herunterladen" })).toBeInTheDocument();
  });
});
