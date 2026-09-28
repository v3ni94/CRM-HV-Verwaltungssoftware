import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { SchadenstoolSettings, type SchadenstoolConfig } from "./SchadenstoolSettings";
import { SchadenstoolTakeover } from "./SchadenstoolTakeover";

const initial: SchadenstoolConfig = {
  base_url: null,
  enabled: false,
  token_set: false,
  token_last4: null,
  token_invalid: false,
  hmac_secret_set: false,
  webhook_secret_set: false,
  webhook_path: "/api/v1/integrations/schadenstool/webhook/t/p",
  avv_confirmed_on: null,
  avv_confirmed_by: null,
  avv_note: null,
  last_tested_at: null,
  last_test_ok: null,
  last_test_message: null,
  last_pull_at: null,
  last_pull_message: null,
};

describe("SchadenstoolSettings", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends secrets once, never shows them and shows the problem when AVV is missing", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      const body = JSON.parse(String(init?.body));
      if (!body.avv_confirmed_on) {
        return jsonResponse({ title: "Auftragsverarbeitungsvertrag nicht bestätigt", status: 422, code: "MHVP-SDT-0005" }, 422);
      }
      return jsonResponse({ ...initial, base_url: body.base_url, enabled: true, token_set: true, token_last4: "wxyz", webhook_secret_set: true, avv_confirmed_on: "2026-09-28" }, 200);
    });
    renderIntl(<SchadenstoolSettings initial={initial} canManage />);
    expect(screen.getByText(initial.webhook_path)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Basisadresse"), "https://schaden.example");
    const token = screen.getByLabelText("Integrationstoken");
    await userEvent.type(token, "token-abcdwxyz");
    await userEvent.type(screen.getByLabelText("Webhook-Geheimnis"), "webhook-secret-0123456789");
    await userEvent.click(screen.getByLabelText("Anbindung aktiv"));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Auftragsverarbeitungsvertrag nicht bestätigt"));
    await userEvent.type(screen.getByLabelText("AVV liegt vor seit"), "2026-09-28");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByText("Einstellungen gespeichert.")).toBeInTheDocument());
    const last = fetchMock.mock.calls.at(-1);
    expect(String(last?.[0])).toBe("/api/bff/integrations/schadenstool/config");
    expect(JSON.parse(String(last?.[1]?.body))).toMatchObject({ token: "token-abcdwxyz", webhook_secret: "webhook-secret-0123456789", avv_confirmed_on: "2026-09-28", enabled: true });
    expect(token).toHaveValue("");
    expect(token).toHaveAttribute("placeholder", "Token ist hinterlegt (endet auf wxyz) und wird nicht angezeigt.");
  });

  it("reports an invalid token from the connection test", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ ...initial, token_set: true, token_invalid: true, last_test_ok: false, last_test_message: "Token ungültig.", last_tested_at: "2026-09-28T10:00:00Z" }, 200),
    );
    renderIntl(<SchadenstoolSettings initial={{ ...initial, token_set: true }} canManage />);
    await userEvent.click(screen.getByRole("button", { name: "Verbindung testen" }));
    await waitFor(() => expect(screen.getByText("Verbindung fehlgeschlagen: Token ungültig.")).toBeInTheDocument());
    expect(screen.getByRole("alert")).toHaveTextContent("Token ungültig.");
  });

  it("is read only without the permission", () => {
    renderIntl(<SchadenstoolSettings initial={initial} canManage={false} />);
    expect(screen.queryByRole("button", { name: "Speichern" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Integrationstoken")).toBeDisabled();
  });
});

describe("SchadenstoolTakeover", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists proposals and links only after the member confirms", async () => {
    const row = {
      id: "01920000-0000-7000-8000-000000000001",
      remote_id: "r1",
      remote_external_id: "01920000-0000-7000-8000-0000000000aa",
      remote_title: "Sturmschaden Dach",
      remote_status: "gutachten",
      remote_status_label: "gutachten",
      object_external_id: "702",
      remote_updated_at: "2026-09-28T09:00:00Z",
      proposed_property_id: "01920000-0000-7000-8000-0000000000bb",
      proposed_property_label: "702 Schadenhaus",
      proposed_ticket_id: "01920000-0000-7000-8000-0000000000aa",
      proposed_ticket_number: 17,
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (init?.method === "POST") return jsonResponse({ id: row.id, sync_status: "linked", ticket_id: row.proposed_ticket_id }, 200);
      return jsonResponse([row], 200);
    });
    renderIntl(<SchadenstoolTakeover canDecide />);
    await waitFor(() => expect(screen.getByText("Sturmschaden Dach")).toBeInTheDocument());
    expect(screen.getByText(/Vorschlag Objekt: 702 Schadenhaus/)).toBeInTheDocument();
    expect(screen.getByText(/Vorschlag Ticket Nr. 17/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.every(([, init]) => init?.method !== "POST")).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Mit vorgeschlagenem Ticket verknüpfen" }));
    await waitFor(() => expect(screen.getByText("Übernommen, zum Ticket")).toBeInTheDocument());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(String(post?.[0])).toBe(`/api/bff/integrations/schadenstool/takeover/${row.id}`);
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ action: "link", ticket_id: row.proposed_ticket_id });
  });
});
