import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { EbicsSubscribers } from "./EbicsSubscribers";

const ID = "0192abcd-0000-7000-8000-000000000031";

const STATUS = {
  enabled: true,
  signature_key_mode: "external",
  transport_available: false,
  transport: "unavailable",
  min_key_bits: 2048,
  default_key_bits: 4096,
  key_bits_strict_from: "2027-11-01",
  c53_btf: "EOP/DE//camt.053/ZIP",
  open_questions: ["AE23-01"],
};

function subscriber(extra: Record<string, unknown> = {}) {
  return {
    id: ID,
    label: "Hausbank",
    host_id: "HOST1",
    partner_id: "PARTNER1",
    ebics_user_id: "USER1",
    url: "https://ebics.example",
    ebics_version: "3.0",
    signature_version: "A006",
    key_bits: 2048,
    signature_key_mode: "external",
    status: "created",
    next_step: "generate_keys",
    ini_sent_at: null,
    hia_sent_at: null,
    activated_on: null,
    bank_keys_verified_at: null,
    last_download_at: null,
    keys: [],
    ...extra,
  };
}

function mockApi(sub: Record<string, unknown>, calls: { url: string; method: string; body: unknown }[]) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (method !== "GET") {
      calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      return jsonResponse(sub);
    }
    if (url.endsWith("/banking/ebics/status")) return jsonResponse(STATUS);
    if (url.endsWith("/banking/ebics/subscribers")) return jsonResponse([sub]);
    return jsonResponse({});
  });
}

describe("EbicsSubscribers", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the missing transport, the key policy and generates keys", async () => {
    const calls: { url: string; method: string; body: unknown }[] = [];
    mockApi(subscriber(), calls);
    renderIntl(<EbicsSubscribers />);
    expect(await screen.findByText("Hausbank")).toBeInTheDocument();
    expect(screen.getByText(/keine geprüfte EBICS-Implementierung installiert/)).toBeInTheDocument();
    expect(screen.getByText(/ab 01\.11\.2027 sind mindestens 4096 Bit nötig/)).toBeInTheDocument();
    expect(screen.getByText("Angelegt")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Schlüssel erzeugen" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]).toEqual({ url: `/api/bff/banking/ebics/subscribers/${ID}/keys`, method: "POST", body: {} });
  });

  it("asks for the bank letter hashes in the verification step", async () => {
    const calls: { url: string; method: string; body: unknown }[] = [];
    mockApi(
      subscriber({
        status: "bank_keys_received",
        next_step: "verify_bank_keys",
        keys: [{ id: "k", owner: "subscriber", usage: "authentication", version: "X002", key_bits: 2048, source: "generated", public_key_sha256: "A", letter_hash: "B", has_private_key: true, runs_out: "2027-11-01" }],
      }),
      calls,
    );
    renderIntl(<EbicsSubscribers />);
    expect(await screen.findByText("Bankschlüssel erhalten, Prüfung offen")).toBeInTheDocument();
    expect(screen.getByText(/läuft am 01\.11\.2027 aus/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Hash-Wert Authentifikationsschlüssel (Bankbrief)"), "AB12");
    await userEvent.type(screen.getByLabelText("Hash-Wert Verschlüsselungsschlüssel (Bankbrief)"), "CD34");
    await userEvent.click(screen.getByRole("button", { name: "Bankschlüssel prüfen" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]).toEqual({
      url: `/api/bff/banking/ebics/subscribers/${ID}/bank-keys/verify`,
      method: "POST",
      body: { authentication_hash: "AB12", encryption_hash: "CD34" },
    });
  });

  it("shows the API error, e.g. the missing transport on INI", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if ((init?.method ?? "GET") === "POST") {
        return jsonResponse({ code: "MHVP-BANK-0050", title: "EBICS-Übertragung nicht verfügbar", status: 503, detail: "EBICS-Übertragung nicht verfügbar" }, 503);
      }
      if (url.endsWith("/banking/ebics/status")) return jsonResponse(STATUS);
      return jsonResponse([subscriber({ status: "keys_ready", next_step: "send_ini" })]);
    });
    renderIntl(<EbicsSubscribers />);
    await userEvent.click(await screen.findByRole("button", { name: "INI senden" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
