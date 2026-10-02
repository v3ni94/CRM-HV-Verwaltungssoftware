import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BankConnectionsPanel } from "./BankConnectionsPanel";

const TX = "0192abcd-0000-7000-8000-00000000a001";
const conn = {
  id: "c1",
  connector: "file_import",
  bank_name: "Testbank",
  bic: "TESTDE00",
  consent_valid_until: "2026-12-31",
  status: "active",
  error_message: null,
  has_credentials: false,
};

type Calls = { url: string; init?: RequestInit }[];

function stub(over: Record<string, () => Response> = {}) {
  const calls: Calls = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const key = `${init?.method ?? "GET"} ${url}`;
    if (over[key]) return over[key]();
    if (url.endsWith("/connections")) return jsonResponse([conn]);
    if (url.endsWith("/runs")) return jsonResponse([{ id: "r1", source: "csv", status: "done", counts: {}, errors: [] }]);
    if (url.endsWith("/learning")) return jsonResponse({ enabled: false, engine_version: "e1", rule_version: "r1", note: "" });
    return jsonResponse([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("BankConnectionsPanel", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads connections and runs", async () => {
    stub();
    renderIntl(<BankConnectionsPanel canApprove={false} />);
    expect(await screen.findByText("Testbank")).toBeInTheDocument();
    expect(screen.getByText("csv")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Verbindung anlegen" })).toBeNull();
  });

  it("creates a connection", async () => {
    const calls = stub({ "POST /api/bff/banking/connections": () => jsonResponse({}) });
    renderIntl(<BankConnectionsPanel canApprove />);
    await screen.findByText("Testbank");
    await userEvent.type(screen.getByRole("textbox", { name: "Bank" }), " Neue Bank ");
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Verbindung anlegen" }));
    });
    const post = calls.find((c) => c.init?.method === "POST");
    expect(JSON.parse(post?.init?.body as string)).toEqual({ bank_name: "Neue Bank", connector: "file_import", bic: null });
    expect(await screen.findByRole("status")).toHaveTextContent("Verbindung angelegt.");
  });

  it("switches the learning toggle only with a reason", async () => {
    const calls = stub({ "PUT /api/bff/banking/learning": () => jsonResponse({}) });
    renderIntl(<BankConnectionsPanel canApprove />);
    const button = await screen.findByRole("button", { name: "Einschalten" });
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox", { name: "Begründung" }), "Test");
    await act(async () => {
      await userEvent.click(button);
    });
    const put = calls.find((c) => c.init?.method === "PUT");
    expect(JSON.parse(put?.init?.body as string)).toEqual({ enabled: true, reason: "Test" });
  });

  it("looks up decisions for a valid transaction id", async () => {
    const calls = stub();
    renderIntl(<BankConnectionsPanel canApprove={false} />);
    await screen.findByText("Testbank");
    const lookup = screen.getByRole("button", { name: "Anzeigen" });
    expect(lookup).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox", { name: "Umsatz-ID" }), TX);
    await act(async () => {
      await userEvent.click(lookup);
    });
    expect(calls.some((c) => c.url === `/api/bff/banking/transactions/${TX}/decisions`)).toBe(true);
    expect(await screen.findByText(/Keine Protokolleinträge/)).toBeInTheDocument();
  });

  it("shows the API error when loading connections fails", async () => {
    stub({ "GET /api/bff/banking/connections": () => jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403) });
    renderIntl(<BankConnectionsPanel canApprove={false} />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
