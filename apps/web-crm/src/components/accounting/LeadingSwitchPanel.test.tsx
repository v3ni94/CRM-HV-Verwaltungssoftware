import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LeadingSwitchPanel } from "./LeadingSwitchPanel";

const URL = "/api/bff/accounting/ledgers/L1/leading-switches";
const state = {
  ledger_leading_system: "immoware24",
  effective: [
    { kind: "receivable_posting", leading_system: "immoware24", source: "ledger" },
    { kind: "dunning", leading_system: "mhvp", source: "switch" },
    { kind: "direct_debit", leading_system: "immoware24", source: "ledger" },
    { kind: "payment_order", leading_system: "immoware24", source: "ledger" },
  ],
  items: [{ id: "S1", kind: "payment_order", leading_system: "mhvp", valid_from: "2026-11-01", property_id: null, status: "requested", comment: null }],
};

describe("LeadingSwitchPanel", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the effective system per kind and requests a switch", async () => {
    const fetchMock = vi.fn<(u: string, i?: RequestInit) => Promise<Response>>(() => Promise.resolve(jsonResponse(state)));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<LeadingSwitchPanel ledgerId="L1" canApprove properties={[{ id: "P1", label: "001 Haus" }]} today="2026-10-02" />);
    expect(await screen.findByText("Mahnung")).toBeInTheDocument();
    expect(screen.getAllByText("Umschaltung").length).toBeGreaterThan(0);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(URL);
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Umschaltung beantragen" }));
    });
    const post = fetchMock.mock.calls.find((c) => c[0] === URL && c[1]?.method === "POST");
    expect(JSON.parse(post?.[1]?.body as string)).toEqual({ kind: "dunning", leading_system: "mhvp", valid_from: "2026-10-02", property_id: null, comment: null });
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Freigeben" }));
    });
    expect(fetchMock.mock.calls.some((c) => c[0] === `${URL}/S1/decide`)).toBe(true);
  });

  it("is read only without approval right", async () => {
    const fetchMock = vi.fn<(u: string, i?: RequestInit) => Promise<Response>>(() => Promise.resolve(jsonResponse(state)));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<LeadingSwitchPanel ledgerId="L1" canApprove={false} properties={[]} today="2026-10-02" />);
    expect(await screen.findByText("Mahnung")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows the error of a refused decision", async () => {
    const fetchMock = vi.fn((_u: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "POST" ? jsonResponse({ title: "Forbidden", status: 403, detail: "Die Freigabe muss eine andere Person vornehmen." }, 403) : jsonResponse(state)),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<LeadingSwitchPanel ledgerId="L1" canApprove properties={[]} today="2026-10-02" />);
    const button = await screen.findByRole("button", { name: "Freigeben" });
    await act(async () => {
      await userEvent.click(button);
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
