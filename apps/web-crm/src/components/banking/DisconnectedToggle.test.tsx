import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { isDisconnected, SHOW_DISCONNECTED_KEY } from "./DisconnectedToggle";
import { FinApiConnections } from "./FinApiConnections";

const base = {
  bank_connection_id: "bc",
  web_form_url: null,
  web_form_status: "FINISHED",
  last_error: null,
  auto_update_enabled: false,
  accounts: [],
};

function mockLoad() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/config")) return jsonResponse({ configured: true, auto_fetch_enabled: false });
    if (url.endsWith("/connections"))
      return jsonResponse([
        { ...base, id: "a", bank_name: "Sparkasse Aktiv", status: "active" },
        { ...base, id: "b", bank_name: "Volksbank Alt", status: "disabled" },
        { ...base, id: "c", bank_name: "Commerzbank Alt", status: "disabled" },
      ]);
    return jsonResponse({});
  });
}

describe("OP-02 disconnected bank connections", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("classifies separated statuses only", () => {
    expect(isDisconnected("disabled")).toBe(true);
    expect(isDisconnected("revoked")).toBe(true);
    expect(isDisconnected("disconnected")).toBe(true);
    expect(isDisconnected("active")).toBe(false);
    expect(isDisconnected("error")).toBe(false);
  });

  it("hides separated connections by default and shows them with the switch, remembered", async () => {
    mockLoad();
    renderIntl(<FinApiConnections />);
    expect(await screen.findByText("Sparkasse Aktiv")).toBeInTheDocument();
    expect(screen.queryByText("Volksbank Alt")).not.toBeInTheDocument();
    const toggle = screen.getByLabelText("Getrennte anzeigen (2)");
    await userEvent.click(toggle);
    expect(screen.getByText("Volksbank Alt")).toBeInTheDocument();
    expect(screen.getByText("Commerzbank Alt")).toBeInTheDocument();
    expect(localStorage.getItem(SHOW_DISCONNECTED_KEY)).toBe("1");
  });

  it("restores the remembered switch state", async () => {
    localStorage.setItem(SHOW_DISCONNECTED_KEY, "1");
    mockLoad();
    renderIntl(<FinApiConnections />);
    expect(await screen.findByText("Volksbank Alt")).toBeInTheDocument();
  });
});
