import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { type MeteringConnection } from "@/lib/metering";
import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { ConnectionsAdmin } from "./ConnectionsAdmin";

const CONN_ID = "cccccccc-1111-4111-8111-111111111111";
const m = messages.Metering;

function connection(over: Partial<MeteringConnection> = {}): MeteringConnection {
  return {
    id: CONN_ID,
    display_name: "ista Hauptkonto",
    provider_code: "ista",
    contracting_company: null,
    environment: "test",
    status: "active",
    customer_references: ["0004711"],
    config: {},
    secret_names: ["client_id"],
    capabilities: [],
    last_test_status: null,
    last_test_at: null,
    last_test_detail: null,
    test_stale: false,
    scheduled_sync_enabled: false,
    write_sync_enabled: false,
    last_sync: {},
    version: 3,
    ...over,
  };
}

describe("ConnectionsAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists connections with secret names only and pauses a connection with the version", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(connection({ status: "paused", version: 4 })));
    const onChange = vi.fn();
    renderIntl(<ConnectionsAdmin initial={[connection()]} providers={[]} canManage onChange={onChange} />);
    const card = screen.getByTestId(`metering-connection-${CONN_ID}`);
    expect(card).toHaveTextContent("ista Hauptkonto");
    expect(card).toHaveTextContent("client_id");
    expect(card).toHaveTextContent("0004711");
    await userEvent.click(screen.getByRole("button", { name: m.connection.pause }));
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe(`/api/bff/metering/connections/${CONN_ID}`);
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ version: 3, status: "paused" });
    expect(await screen.findByRole("button", { name: m.connection.activate })).toBeInTheDocument();
  });

  it("shows the API refusal and keeps the state when the write release fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Konflikt", status: 409, detail: "Version veraltet" }, 409));
    renderIntl(<ConnectionsAdmin initial={[connection()]} providers={[]} canManage />);
    await userEvent.click(screen.getByRole("button", { name: m.connection.writeRelease }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Version veraltet");
    expect(screen.getByRole("button", { name: m.connection.writeRelease })).toBeInTheDocument();
  });

  it("sends secrets via PUT and clears the form afterwards", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(connection({ secret_names: ["client_id", "token"] })));
    renderIntl(<ConnectionsAdmin initial={[connection()]} providers={[]} canManage />);
    await userEvent.click(screen.getByRole("button", { name: m.connection.replaceSecrets }));
    await userEvent.type(screen.getByLabelText(m.connection.secretName), "token");
    const value = screen.getByLabelText(m.connection.secretValue);
    expect(value).toHaveAttribute("type", "password");
    await userEvent.type(value, "geheim");
    await userEvent.click(screen.getByRole("button", { name: m.save }));
    await waitFor(() => expect(screen.queryByLabelText(m.connection.secretValue)).not.toBeInTheDocument());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe(`/api/bff/metering/connections/${CONN_ID}/secrets`);
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ secrets: { token: "geheim" } });
    expect(screen.getByTestId(`metering-connection-${CONN_ID}`)).toHaveTextContent("token");
    expect(screen.getByTestId(`metering-connection-${CONN_ID}`)).not.toHaveTextContent("geheim");
  });

  it("hides all actions without manage right and shows the read-only hint", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<ConnectionsAdmin initial={[connection()]} providers={[]} canManage={false} loadFailed />);
    expect(screen.getByText(m.readOnlyHint)).toBeInTheDocument();
    expect(screen.getByText(m.loadError)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
