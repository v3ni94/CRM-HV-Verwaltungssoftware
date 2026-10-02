import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LexofficeRuns } from "./LexofficeRuns";

const RUN = { id: "r1", kind: "receipts", status: "failed", counts: { read: 3 }, errors: [{}], created_at: "2026-09-30T10:00:00Z", finished_at: null };

describe("LexofficeRuns (GAI-615)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists runs with counts and error badge, no import button without the right", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([RUN]));
    renderIntl(<LexofficeRuns canImport={false} />);
    expect(await screen.findByText("failed")).toBeInTheDocument();
    expect(screen.getByText("read: 3")).toBeInTheDocument();
    expect(screen.getByText("30.09.2026")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("imports receipts with POST, locks while running and reloads", async () => {
    let release: (r: Response) => void = () => undefined;
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([]))
      .mockReturnValueOnce(new Promise((resolve) => (release = resolve)))
      .mockResolvedValueOnce(jsonResponse([RUN]));
    renderIntl(<LexofficeRuns canImport />);
    const button = await screen.findByRole("button");
    await userEvent.click(button);
    expect(button).toBeDisabled();
    release(jsonResponse({}, 201));
    expect(await screen.findByText("failed")).toBeInTheDocument();
    expect(fetchMock.mock.calls[1]![0]).toBe("/api/bff/integrations/lexoffice/import/receipts");
    expect((fetchMock.mock.calls[1]![1] as RequestInit).method).toBe("POST");
  });

  it("shows the refusal of the import", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse([])).mockResolvedValueOnce(jsonResponse({ title: "Nicht verbunden", status: 409 }, 409));
    renderIntl(<LexofficeRuns canImport />);
    await userEvent.click(await screen.findByRole("button"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
