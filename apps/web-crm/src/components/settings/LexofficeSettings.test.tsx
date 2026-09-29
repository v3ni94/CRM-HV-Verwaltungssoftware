import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LexofficeConfigForm, LexofficeKindMappingForm, LexofficeSettings, type LexofficeConfig, type LexofficeKindMapping } from "./LexofficeSettings";

const config: LexofficeConfig = {
  id: "cfg-1",
  legal_entity_id: "le-1",
  legal_entity_name: "Hausverwaltung",
  label: "HVM",
  base_url: "https://api.lexware.io",
  app_base_url: "https://app.lexware.de",
  enabled: false,
  api_key_set: true,
  api_key_last4: "ab12",
  token_invalid: false,
  organization_id: "org-1",
  organization_name: "HVM GmbH",
  profile_tax_type: "net",
  profile_small_business: false,
  profile_business_features: [],
  has_invoicing: false,
  avv_confirmed_on: null,
  avv_confirmed_by: null,
  avv_note: null,
  mailbox_id: null,
  sync_contacts: false,
  sync_names: false,
  invoice_copies: false,
  invoice_drafts: false,
  last_tested_at: "2026-09-28T10:00:00Z",
  last_test_ok: true,
  last_test_message: "Verbindung erfolgreich.",
};
const entities = [
  { id: "le-1", kind: "manager", name: "Hausverwaltung" },
  { id: "le-2", kind: "rental_owner", name: "Einzelunternehmen" },
];
const kinds: LexofficeKindMapping[] = [
  { kind: "broker", label: "Maklerrechnungen", legal_entity_id: null, legal_entity_name: null, config_id: null },
  { kind: "consulting", label: "Beratung", legal_entity_id: null, legal_entity_name: null, config_id: null },
  { kind: "management", label: "Hausverwaltung", legal_entity_id: "le-1", legal_entity_name: "Hausverwaltung", config_id: "cfg-1" },
];

describe("LexofficeConfigForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the write only key placeholder, refuses enabling without AVV and disables invoice switches without INVOICING", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      const body = JSON.parse(String(init?.body));
      if (body.enabled && !body.avv_confirmed_on) {
        return jsonResponse({ title: "Auftragsverarbeitungsvertrag nicht bestätigt", status: 422, code: "MHVP-LEXO-0006" }, 422);
      }
      return jsonResponse({ ...config, enabled: true, avv_confirmed_on: body.avv_confirmed_on, api_key_last4: "wxyz" }, 200);
    });
    renderIntl(<LexofficeConfigForm config={config} legalEntities={entities} mailboxes={[]} canManage onSaved={() => undefined} />);
    const key = screen.getByLabelText("API Schlüssel");
    expect(key).toHaveAttribute("placeholder", "Schlüssel ist hinterlegt (endet auf ab12) und wird nicht angezeigt.");
    expect(screen.getByLabelText("Rechnungskopien abrufen")).toBeDisabled();
    expect(screen.getByLabelText("Rechnungsentwürfe anlegen")).toBeDisabled();
    await userEvent.type(key, "new-key-wxyz");
    await userEvent.click(screen.getByLabelText("Anbindung aktiv"));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Auftragsverarbeitungsvertrag nicht bestätigt"));
    await userEvent.type(screen.getByLabelText("AVV liegt vor seit"), "2026-09-28");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Einstellungen gespeichert."));
    const last = fetchMock.mock.calls.at(-1);
    expect(String(last?.[0])).toBe("/api/bff/integrations/lexoffice/configs/cfg-1");
    expect(JSON.parse(String(last?.[1]?.body))).toMatchObject({ api_key: "new-key-wxyz", avv_confirmed_on: "2026-09-28", enabled: true, clear_mailbox: true });
    expect(key).toHaveValue("");
    expect(key).toHaveAttribute("placeholder", "Schlüssel ist hinterlegt (endet auf wxyz) und wird nicht angezeigt.");
  });

  it("shows the invalid key banner and the test required hint", () => {
    renderIntl(<LexofficeConfigForm config={{ ...config, token_invalid: true, last_test_ok: false }} legalEntities={entities} mailboxes={[]} canManage onSaved={() => undefined} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Der API Schlüssel wurde von Lexware Office abgelehnt.");
    renderIntl(<LexofficeConfigForm config={{ ...config, last_test_ok: null }} legalEntities={entities} mailboxes={[]} canManage onSaved={() => undefined} />);
    expect(screen.getByText("Verbindungstest erforderlich, bevor die Anbindung aktiviert werden kann.")).toBeInTheDocument();
  });

  it("is read only without the permission", () => {
    renderIntl(<LexofficeConfigForm config={config} legalEntities={entities} mailboxes={[]} canManage={false} onSaved={() => undefined} />);
    expect(screen.queryByRole("button", { name: "Speichern" })).not.toBeInTheDocument();
    expect(screen.getByText("Nur Lesezugriff.")).toBeInTheDocument();
    expect(screen.getByLabelText("API Schlüssel")).toBeDisabled();
  });

  it("creates a new organisation for a legal entity", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...config, id: "cfg-2", legal_entity_id: "le-2", legal_entity_name: "Einzelunternehmen", api_key_set: false, message: "Verbindungstest erforderlich" }, 201));
    const onSaved = vi.fn();
    renderIntl(<LexofficeConfigForm config={null} legalEntities={entities} mailboxes={[{ id: "mb-1", address: "rechnung@example.org" }]} canManage onSaved={onSaved} />);
    await userEvent.selectOptions(screen.getByLabelText("Gesellschaft"), "le-2");
    await userEvent.type(screen.getByLabelText("Bezeichnung"), "Makler");
    await userEvent.selectOptions(screen.getByLabelText("Postfach für Rechnungskopien"), "mb-1");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/bff/integrations/lexoffice/configs");
    expect(JSON.parse(String(init?.body))).toMatchObject({ legal_entity_id: "le-2", label: "Makler", mailbox_id: "mb-1" });
    expect(screen.getByRole("status")).toHaveTextContent("Verbindungstest erforderlich");
  });
});

describe("LexofficeKindMappingForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves the invoice kind to legal entity mapping", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      const body = JSON.parse(String(init?.body)) as { kind: string; legal_entity_id: string | null }[];
      return jsonResponse(kinds.map((k) => ({ ...k, legal_entity_id: body.find((b) => b.kind === k.kind)?.legal_entity_id ?? null })), 200);
    });
    renderIntl(<LexofficeKindMappingForm initial={kinds} legalEntities={entities} canManage />);
    await userEvent.selectOptions(screen.getByLabelText("Maklerrechnungen"), "le-2");
    await userEvent.click(screen.getByRole("button", { name: "Zuordnung speichern" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Zuordnung gespeichert."));
    expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual([
      { kind: "broker", legal_entity_id: "le-2" },
      { kind: "consulting", legal_entity_id: null },
      { kind: "management", legal_entity_id: "le-1" },
    ]);
  });
});

describe("LexofficeSettings", () => {
  it("switches tabs and hides the link tab without the permission", async () => {
    renderIntl(<LexofficeSettings configs={[config]} legalEntities={entities} kinds={kinds} mailboxes={[]} canManage canLinkContacts={false} canAccounting={false} />);
    const nav = screen.getByRole("navigation", { name: "Lexware Office" });
    expect(within(nav).queryByRole("button", { name: "Kontakte zuordnen" })).not.toBeInTheDocument();
    await userEvent.click(within(nav).getByRole("button", { name: "Rechnungsarten" }));
    expect(screen.getByRole("heading", { name: "Rechnungsart und Gesellschaft" })).toBeInTheDocument();
  });
});
