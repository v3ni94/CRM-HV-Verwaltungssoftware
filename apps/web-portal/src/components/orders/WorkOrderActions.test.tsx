import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { WorkOrderActions } from "./WorkOrderActions";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh, back: vi.fn() }) }));

const ORDER_ID = "6c9f7a2e-0000-4000-8000-00000000000a";

describe("WorkOrderActions", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    refresh.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("submits a quote with the German amount converted to a decimal string", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ id: ORDER_ID, status: "quoted" }));
    renderIntl(<WorkOrderActions orderId={ORDER_ID} status="requested" />);
    fireEvent.click(screen.getByRole("button", { name: "Angebot abgeben" }));
    fireEvent.change(screen.getByLabelText("Betrag in EUR"), { target: { value: "1.250,50" } });
    fireEvent.click(screen.getByRole("button", { name: "Angebot senden" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe(`/api/bff/portal/work-orders/${ORDER_ID}/quote`);
    expect(JSON.parse(String(init?.body))).toEqual({ amount: "1250.50" });
    expect(await screen.findByRole("status")).toHaveTextContent("Die Änderung wurde übermittelt.");
  });

  it("rejects an invalid amount without calling the API", async () => {
    renderIntl(<WorkOrderActions orderId={ORDER_ID} status="requested" />);
    fireEvent.click(screen.getByRole("button", { name: "Angebot abgeben" }));
    fireEvent.change(screen.getByLabelText("Betrag in EUR"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Angebot senden" }));
    expect(await screen.findByText(/Bitte einen Betrag größer 0/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("declines after an explicit confirmation", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ id: ORDER_ID, status: "rejected" }));
    renderIntl(<WorkOrderActions orderId={ORDER_ID} status="requested" />);
    fireEvent.click(screen.getByRole("button", { name: "Auftrag ablehnen" }));
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Ablehnung bestätigen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url] = fetchMock.mock.calls[0]!;
    expect(url).toBe(`/api/bff/portal/work-orders/${ORDER_ID}/decline`);
  });

  it("offers only the appointment action after approval", () => {
    renderIntl(<WorkOrderActions orderId={ORDER_ID} status="approved" />);
    expect(screen.getByRole("button", { name: "Termin nennen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Angebot abgeben" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Auftrag ablehnen" })).not.toBeInTheDocument();
  });
});
