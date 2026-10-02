import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { StatementInspectionsPanel } from "./StatementInspectionsPanel";

const CONTRACTS = [{ contract_id: "c1", unit_number: "01" }];
const OPEN_ROW = {
  id: "r1",
  contract_id: "c1",
  requested_at: "2026-09-01",
  channel: "email",
  status: "open",
  provision: null,
  provided_at: null,
  objection_received_at: null,
  objection_text: null,
};

describe("StatementInspectionsPanel (GAI-615)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads on demand and shows the empty state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]));
    renderIntl(<StatementInspectionsPanel id="s1" contracts={CONTRACTS} />);
    expect(screen.queryByText("Keine Anfragen erfasst.")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Anfragen laden" }));
    expect(await screen.findByText("Keine Anfragen erfasst.")).toBeInTheDocument();
    expect(screen.getByText(/keine Fristberechnung und keine Rechtsfolge/)).toBeInTheDocument();
  });

  it("records a request only with a date and reloads the list", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(OPEN_ROW, 201))
      .mockResolvedValueOnce(jsonResponse([OPEN_ROW]));
    const { container } = renderIntl(<StatementInspectionsPanel id="s1" contracts={CONTRACTS} />);
    await userEvent.click(screen.getByRole("button", { name: "Anfragen laden" }));
    const add = await screen.findByRole("button", { name: "Anfrage erfassen" });
    expect(add).toBeDisabled();
    await userEvent.type(container.querySelector('input[type="date"]') as HTMLInputElement, "2026-09-01");
    await userEvent.click(add);
    expect(await screen.findByRole("cell", { name: "E-Mail" })).toBeInTheDocument();
    const [, init] = fetchMock.mock.calls[1]!;
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ contract_id: "c1", requested_at: "2026-09-01", channel: "letter" });
    expect(screen.getByText("offen")).toBeInTheDocument();
  });

  it("closes a request with PATCH and shows the refusal of the API", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([OPEN_ROW]))
      .mockResolvedValueOnce(jsonResponse({ title: "Nicht erlaubt", status: 403 }, 403));
    renderIntl(<StatementInspectionsPanel id="s1" contracts={CONTRACTS} />);
    await userEvent.click(screen.getByRole("button", { name: "Anfragen laden" }));
    await userEvent.click(await screen.findByRole("button", { name: "Abschließen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[1]!;
    expect(url).toBe("/api/bff/statements/s1/inspections/r1");
    expect((init as RequestInit).method).toBe("PATCH");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ close: true });
  });
});
