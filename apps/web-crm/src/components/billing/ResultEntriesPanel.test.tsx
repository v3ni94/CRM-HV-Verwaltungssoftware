import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ResultEntriesPanel } from "./ResultEntriesPanel";

describe("ResultEntriesPanel (GAI-615)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is closed outside the status due", () => {
    renderIntl(<ResultEntriesPanel id="s1" status="draft" />);
    expect(screen.getByText("Ergebnisbuchungen sind erst im Status fällig möglich.")).toBeInTheDocument();
    expect(screen.queryByTestId("result-entries")).not.toBeInTheDocument();
  });

  it("needs both dates, then posts drafts only and reports the count", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ entry_ids: ["a", "b"] }, 201));
    const { container } = renderIntl(<ResultEntriesPanel id="s1" status="due" />);
    const create = screen.getByRole("button", { name: "Entwürfe erzeugen" });
    expect(create).toBeDisabled();
    expect(screen.getByText(/Es wird nichts gebucht/)).toBeInTheDocument();
    const dates = container.querySelectorAll('input[type="date"]');
    await userEvent.type(dates[0] as HTMLInputElement, "2026-12-31");
    expect(create).toBeDisabled();
    await userEvent.type(dates[1] as HTMLInputElement, "2027-01-15");
    await userEvent.click(create);
    expect(await screen.findByText("2 Entwürfe erzeugt.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/bff/statements/s1/result-entries");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ booking_date: "2026-12-31", due_date: "2027-01-15" });
  });

  it("shows the refusal of the gate unchanged", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Freigabestufe G3 geschlossen", status: 403 }, 403));
    const { container } = renderIntl(<ResultEntriesPanel id="s1" status="due" />);
    const dates = container.querySelectorAll('input[type="date"]');
    await userEvent.type(dates[0] as HTMLInputElement, "2026-12-31");
    await userEvent.type(dates[1] as HTMLInputElement, "2027-01-15");
    await userEvent.click(screen.getByRole("button", { name: "Entwürfe erzeugen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
