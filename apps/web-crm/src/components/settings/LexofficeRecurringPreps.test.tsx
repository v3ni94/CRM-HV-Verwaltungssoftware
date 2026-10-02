import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LexofficeRecurringPreps } from "./LexofficeRecurringPreps";

const row = {
  id: "p1",
  property_id: "x",
  status: "open",
  prepared: {
    property: { number: "1001", name: "Am Park" },
    contact: { display_name: "WEG Am Park", deeplink: null },
    amounts_per_unit_type: { wohnung: "12.50" },
    interval_label: "monatlich",
    start_date: "2026-11-01",
    text: "Verwalterhonorar",
    api_limitation: "Nur lesend.",
  },
  checklist: [{ step: 1, text: "Vorlage anlegen", done: false }],
  lexoffice_template_id: null,
  deeplink: null,
};

describe("LexofficeRecurringPreps (GAH-407)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the empty state", async () => {
    fetchMock.mockImplementation(async () => jsonResponse([]));
    renderIntl(<LexofficeRecurringPreps canManage />);
    expect(await screen.findByText("Keine offenen Vorbereitungen.")).toBeInTheDocument();
  });

  it("renders a preparation with German amount and date format", async () => {
    fetchMock.mockImplementation(async () => jsonResponse([row]));
    renderIntl(<LexofficeRecurringPreps canManage />);
    expect(await screen.findByText(/wohnung: 12,50 EUR/)).toBeInTheDocument();
    expect(screen.getByText(/01\.11\.2026/)).toBeInTheDocument();
    expect(screen.getByText("Vorlage anlegen")).toBeInTheDocument();
  });

  it("hides the actions without the manage right", async () => {
    fetchMock.mockImplementation(async () => jsonResponse([row]));
    renderIntl(<LexofficeRecurringPreps canManage={false} />);
    await screen.findByText("Vorlage anlegen");
    expect(screen.queryByRole("button", { name: "Verwerfen" })).not.toBeInTheDocument();
  });

  it("needs a template id before recording as done and posts it", async () => {
    fetchMock.mockImplementation(async () => jsonResponse([row]));
    renderIntl(<LexofficeRecurringPreps canManage />);
    const done = await screen.findByRole("button", { name: "Als angelegt erfassen" });
    expect(done).toBeDisabled();
    await userEvent.type(screen.getByLabelText("ID der angelegten Vorlage"), "tpl-1");
    expect(done).toBeEnabled();
    await userEvent.click(done);
    await waitFor(() => expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith("/p1/done"))).toBe(true));
    const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/p1/done"));
    expect(call?.[1]?.method).toBe("POST");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ lexoffice_template_id: "tpl-1" });
  });

  it("shows the load error", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ code: "X", title: "Fehler", status: 500 }, 500));
    renderIntl(<LexofficeRecurringPreps canManage />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
