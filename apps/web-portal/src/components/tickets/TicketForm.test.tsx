import { fireEvent, screen, waitFor } from "@testing-library/react";

import type { PortalContract } from "@/lib/portal";
import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketForm } from "./TicketForm";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh, back: vi.fn() }) }));

const contract: PortalContract = {
  id: "6c9f7a2e-0000-4000-8000-000000000001",
  kind: "rental",
  number: "MV-2024-001",
  unit_id: "6c9f7a2e-0000-4000-8000-000000000002",
  start_date: "2024-01-01",
  end_date: null,
};

describe("TicketForm", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    refresh.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("validates subject and description before calling the API", async () => {
    renderIntl(<TicketForm contracts={[contract]} />);
    fireEvent.click(screen.getByRole("button", { name: "Meldung absenden" }));
    expect(await screen.findByText("Bitte einen Betreff mit mindestens 3 Zeichen angeben.")).toBeInTheDocument();
    expect(screen.getByText("Bitte den Schaden mit mindestens 3 Zeichen beschreiben.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts the report with the chosen unit and shows the case number", async () => {
    fetchMock.mockImplementation(async () =>
      jsonResponse({ id: "x", number: "T-2026-0042", status: "new" }, 201),
    );
    renderIntl(<TicketForm contracts={[contract]} />);
    fireEvent.change(screen.getByLabelText("Betreff"), { target: { value: "Wasserschaden im Bad" } });
    fireEvent.change(screen.getByLabelText("Beschreibung"), { target: { value: "Wasser tritt unter der Wanne aus." } });
    fireEvent.change(screen.getByLabelText("Einheit (optional)"), { target: { value: contract.unit_id } });
    fireEvent.click(screen.getByRole("button", { name: "Meldung absenden" }));
    expect(await screen.findByRole("status")).toHaveTextContent("T-2026-0042");
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/bff/portal/tickets");
    expect(JSON.parse(String(init?.body))).toEqual({
      title: "Wasserschaden im Bad",
      description: "Wasser tritt unter der Wanne aus.",
      unit_id: contract.unit_id,
    });
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });
});
