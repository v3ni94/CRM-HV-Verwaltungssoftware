import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { FinTsConnectDialog, FinTsConnections, FinTsSessionPanel } from "./FinTsConnections";

const CONNECTION_ID = "0192abcd-0000-7000-8000-000000000011";
const SESSION_ID = "0192abcd-0000-7000-8000-000000000012";

const INSTITUTES = [
  { blz: "38250110", name: "Kreissparkasse Euskirchen", city: "Euskirchen", bic: "WELADED1EUS", fints_url: "https://x", connectable: true },
  { blz: "25440047", name: "Commerzbank", city: "Hameln", bic: "COBADEFF254", fints_url: null, connectable: false },
];

function session(status: string, extra: Record<string, unknown> = {}) {
  return {
    id: SESSION_ID,
    fints_connection_id: CONNECTION_ID,
    purpose: "connect",
    status,
    tan_mechanism: "912",
    tan_mechanisms: [{ code: "912", name: "chipTAN optisch", decoupled: false }],
    challenge_text: null,
    challenge_hhduc: null,
    challenge_image_mime: null,
    challenge_image_base64: null,
    challenge_decoupled: false,
    tan_pending: false,
    error_code: null,
    error_message: null,
    result: {},
    sync_run_id: null,
    ...extra,
  };
}

const CONNECTION = {
  id: CONNECTION_ID,
  bank_connection_id: "0192abcd-0000-7000-8000-000000000013",
  bank_name: "Kreissparkasse Euskirchen",
  blz: "38250110",
  bic: "WELADED1EUS",
  status: "active",
  tan_mechanism: "912",
  tan_mechanisms: [{ code: "912", name: "chipTAN optisch", decoupled: false }],
  last_sca_at: "2026-09-27T10:00:00Z",
  sca_due: false,
  sca_due_on: "2026-12-26",
  pin_blocked: false,
  last_error: null,
  last_error_code: null,
  last_sync_at: "2026-09-27T10:05:00Z",
  open_session_id: null,
  accounts: [
    {
      id: "0192abcd-0000-7000-8000-000000000014",
      iban_suffix: "2051",
      bic: "WELADED1EUS",
      account_number: "0000202051",
      property_bank_account_id: null,
      balance_booked: "1234.56",
      balance_currency: "EUR",
      balance_as_of: "2026-09-27",
      balance_fetched_at: "2026-09-27T10:05:00Z",
      last_transactions_fetch_at: null,
      last_synced_booking_date: null,
    },
  ],
};

describe("FinTsConnections", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists a connection with status, balance and the refresh button", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/banking/fints/connections")) return jsonResponse([CONNECTION]);
      if (url.includes("/banking/accounts")) return jsonResponse([]);
      return jsonResponse({});
    });
    renderIntl(<FinTsConnections />);
    expect(await screen.findByText("Kreissparkasse Euskirchen")).toBeInTheDocument();
    expect(screen.getByText("Verbunden")).toBeInTheDocument();
    expect(screen.getByText(/1\.234,56/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aktualisieren" })).toBeEnabled();
    expect(screen.getByText(/Freigabe gültig bis 26\.12\.2026/)).toBeInTheDocument();
  });

  it("shows the PIN re-entry hint when the bank rejected the PIN", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/banking/fints/connections")) {
        return jsonResponse([{ ...CONNECTION, status: "error", pin_blocked: true, last_error_code: "MHVP-BANK-0009" }]);
      }
      if (url.includes("/banking/accounts")) return jsonResponse([]);
      return jsonResponse({});
    });
    renderIntl(<FinTsConnections />);
    expect(await screen.findByText(/Die Bank hat Anmeldename oder PIN abgelehnt/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Aktualisieren" })).toBeDisabled();
    expect(screen.getByLabelText("PIN erneut eingeben")).toBeInTheDocument();
  });
});

describe("FinTsConnectDialog", () => {
  afterEach(() => vi.restoreAllMocks());

  it("walks institute search, credentials and the TAN step", async () => {
    const posted: { url: string; body: unknown }[] = [];
    let sessionStatus = "awaiting_tan";
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.includes("/banking/fints/institutes?q=")) return jsonResponse(INSTITUTES);
      if (method === "POST" && url.endsWith("/banking/fints/connections")) {
        posted.push({ url, body: JSON.parse(String(init?.body)) });
        return jsonResponse(session("queued"), 201);
      }
      if (method === "POST" && url.endsWith(`/sessions/${SESSION_ID}/tan`)) {
        posted.push({ url, body: JSON.parse(String(init?.body)) });
        sessionStatus = "done";
        return jsonResponse(session("awaiting_tan", { tan_pending: true }));
      }
      if (url.endsWith(`/sessions/${SESSION_ID}`)) {
        return jsonResponse(
          session(sessionStatus, sessionStatus === "awaiting_tan" ? { challenge_text: "Bitte TAN eingeben", challenge_hhduc: "0248A0123" } : { result: { accounts: 1 } })
        );
      }
      if (url.endsWith("/banking/fints/connections")) return jsonResponse([CONNECTION]);
      if (url.includes("/banking/accounts")) return jsonResponse([]);
      return jsonResponse({});
    });
    const onChanged = vi.fn();
    renderIntl(<FinTsConnectDialog onClose={() => undefined} onChanged={onChanged} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Bank"), "Euskirchen");
    const hit = await screen.findByRole("option", { name: /Kreissparkasse Euskirchen/ });
    expect(screen.getByRole("option", { name: /Commerzbank/ })).toBeDisabled();
    await user.click(hit);
    await user.type(screen.getByLabelText("Anmeldename"), "kunde-1");
    await user.type(screen.getByLabelText("PIN"), "geheim");
    await user.click(screen.getByRole("button", { name: "Verbindung starten" }));
    expect(posted[0]?.body).toEqual({ institute: "38250110", login: "kunde-1", pin: "geheim" });
    expect(await screen.findByText("Bitte TAN eingeben")).toBeInTheDocument();
    expect(screen.getByText("0248A0123")).toBeInTheDocument();
    await user.type(screen.getByLabelText("TAN"), "123456");
    await user.click(screen.getByRole("button", { name: "TAN senden" }));
    expect(posted[1]?.body).toEqual({ tan: "123456" });
    await waitFor(() => expect(screen.getByText(/1 Konten geladen/)).toBeInTheDocument(), { timeout: 6000 });
    expect(onChanged).toHaveBeenCalled();
  }, 10000);
});

describe("FinTsSessionPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders the failed state with the bank's error and the PIN lock hint", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse(session("failed", { error_code: "MHVP-BANK-0009", error_message: "Bank hat Anmeldename oder PIN abgelehnt" }))
    );
    const onFailed = vi.fn();
    renderIntl(<FinTsSessionPanel sessionId={SESSION_ID} onFailed={onFailed} />);
    expect(await screen.findByText(/Bank hat Anmeldename oder PIN abgelehnt/)).toBeInTheDocument();
    expect(screen.getByText(/Nach einem Fehlversuch/)).toBeInTheDocument();
    await waitFor(() => expect(onFailed).toHaveBeenCalled());
  });

  it("shows the decoupled waiting state with the poll button", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse(session("awaiting_decoupled", { challenge_decoupled: true, challenge_text: "In der App freigeben" }))
    );
    renderIntl(<FinTsSessionPanel sessionId={SESSION_ID} />);
    expect(await screen.findByText("In der App freigeben")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Freigabe jetzt prüfen" })).toBeInTheDocument();
  });
});
