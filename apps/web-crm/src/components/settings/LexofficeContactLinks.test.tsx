import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LexofficeContactLinks, type LexofficeLink } from "./LexofficeContactLinks";

const base: LexofficeLink = {
  id: "link-1",
  config_id: "cfg-1",
  contact_id: "c-1",
  contact_display_name: "Muster, Erika",
  lexoffice_contact_id: "r-1",
  customer_number: 10001,
  vendor_number: null,
  sync_status: "proposed",
  diverged: false,
  remote_display: { name: "Erika Muster", city: "Berlin" },
  match_reason: "email_exact",
  match_score: "0.9",
  candidates: [],
  conflict: null,
  last_synced_at: null,
  last_error: null,
  deeplink: "https://app.lexware.de/permalink/contacts/view/r-1",
};

describe("LexofficeContactLinks", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists proposed rows with reason, decides a link and reloads with the filter", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "POST") return jsonResponse({ ...base, sync_status: "pending" }, 200);
      if (url.includes("status=ambiguous")) return jsonResponse({ items: [{ ...base, id: "link-2", sync_status: "ambiguous", contact_id: null, contact_display_name: null, match_reason: null, candidates: [{ contact_id: "a", reason: "name_zip", score: 0.7 }, { contact_id: "b", reason: "name_zip", score: 0.7 }] }], total: 1 }, 200);
      return jsonResponse({ items: [base], total: 1 }, 200);
    });
    renderIntl(<LexofficeContactLinks configId="cfg-1" canDecide />);
    await waitFor(() => expect(screen.getByText("Muster, Erika")).toBeInTheDocument());
    expect(screen.getByText("Grund: E-Mail identisch")).toBeInTheDocument();
    expect(screen.getByText("Kd.Nr. 10001")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Verknüpfen" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u, i]) => String(u).endsWith("/contacts/links/link-1/decide") && i?.method === "POST")).toBe(true));
    expect(JSON.parse(String(fetchMock.mock.calls.find(([u]) => String(u).endsWith("/decide"))![1]?.body))).toEqual({ action: "link" });
    await userEvent.selectOptions(screen.getByLabelText("Filter"), "ambiguous");
    await waitFor(() => expect(screen.getByText("2 Kandidaten")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Verknüpfen" })).not.toBeInTheDocument();
  });

  it("shows the three conflict columns and resolves", async () => {
    const conflict = { ...base, sync_status: "conflict", conflict: { address: { crm: { street: "Neu 1", zip: "1", city: "Hilden", countryCode: "DE" }, lexoffice: { street: "Alt 1", zip: "1", city: "Anderswo", countryCode: "DE" }, baseline: { street: "Alt 1", zip: "1", city: "Berlin", countryCode: "DE" } } } };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => (init?.method === "POST" ? jsonResponse({ ...base, sync_status: "synced" }, 200) : jsonResponse({ items: [conflict], total: 1 }, 200)));
    renderIntl(<LexofficeContactLinks configId="cfg-1" canDecide />);
    await waitFor(() => expect(screen.getByText("Neu 1, 1, Hilden, DE")).toBeInTheDocument());
    expect(screen.getByText("Alt 1, 1, Anderswo, DE")).toBeInTheDocument();
    expect(screen.getByText("Alt 1, 1, Berlin, DE")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Lexware Stand behalten" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/resolve-conflict"))).toBe(true));
    expect(JSON.parse(String(fetchMock.mock.calls.find(([u]) => String(u).endsWith("/resolve-conflict"))![1]?.body))).toEqual({ resolution: "keep_lexoffice" });
  });

  it("asks before the batch push of diverged rows and hides actions without the permission", async () => {
    const diverged = { ...base, sync_status: "synced", diverged: true };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => (init?.method === "POST" ? jsonResponse({ queued: 1 }, 200) : jsonResponse({ items: [diverged], total: 1 }, 200)));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<LexofficeContactLinks configId="cfg-1" canDecide />);
    await userEvent.selectOptions(screen.getByLabelText("Filter"), "diverged");
    await waitFor(() => expect(screen.getByRole("button", { name: "Abweichende abgleichen (1)" })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Abweichende abgleichen (1)" }));
    expect(confirm).toHaveBeenCalledWith("1 Kontakte in die Warteschlange stellen?");
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/push-batch"))).toBe(true));
  });

  it("hides every action without the permission", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ items: [base], total: 1 }, 200));
    renderIntl(<LexofficeContactLinks configId="cfg-1" canDecide={false} />);
    await waitFor(() => expect(screen.getByText("Muster, Erika")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Abgleich starten" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Verknüpfen" })).not.toBeInTheDocument();
  });
});
