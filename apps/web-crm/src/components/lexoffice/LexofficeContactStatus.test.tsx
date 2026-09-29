import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LexofficeContactBadge, LexofficeContactSection, type ContactLexofficeStatus } from "./LexofficeContactStatus";

const CONTACT = "01920000-0000-7000-8000-0000000000c1";
const row = (patch: Partial<ContactLexofficeStatus> = {}): ContactLexofficeStatus => ({
  config_id: "cfg-1",
  label: "HVM",
  legal_entity_id: "le-1",
  sync_status: "synced",
  last_synced_at: "2026-09-28T10:00:00Z",
  diverged: false,
  deeplink: "https://app.lexware.de/contacts/1",
  last_error: null,
  link_id: "link-1",
  ...patch,
});

function mockApi(rows: ContactLexofficeStatus[]) {
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
    if (url.endsWith(`/contacts/${CONTACT}/lexoffice`)) return jsonResponse(rows);
    if (url.includes("/contacts/links/link-1/")) return jsonResponse({ id: "link-1" });
    return jsonResponse({ title: "unerwartet" }, 500);
  });
  return calls;
}

describe("LexofficeContactBadge", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the link status and the diverged marker", async () => {
    mockApi([row({ diverged: true })]);
    renderIntl(<LexofficeContactBadge contactId={CONTACT} />);
    await waitFor(() => expect(screen.getByTestId("lexoffice-contact-badge")).toHaveTextContent("Lexware: Abgeglichen, abweichend"));
  });

  it("renders nothing without a link", async () => {
    mockApi([row({ sync_status: null, link_id: null })]);
    const { container } = renderIntl(<LexofficeContactBadge contactId={CONTACT} />);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});

describe("LexofficeContactSection", () => {
  afterEach(() => vi.restoreAllMocks());

  it("offers push for a synced link and queues it on click", async () => {
    const calls = mockApi([row()]);
    const user = userEvent.setup();
    renderIntl(<LexofficeContactSection contactId={CONTACT} canUpdate canCreateDraft={false} />);
    await waitFor(() => expect(screen.getByTestId("lexoffice-contact-row")).toHaveTextContent("HVM"));
    expect(screen.getByRole("link", { name: "In Lexware Office öffnen" })).toHaveAttribute("href", "https://app.lexware.de/contacts/1");
    expect(screen.queryByRole("button", { name: "Verknüpfen" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Jetzt abgleichen" }));
    await waitFor(() => expect(screen.getByText("Übertragung eingeplant.")).toBeInTheDocument());
    expect(calls.find((c) => c.method === "POST")?.url).toContain("/configs/cfg-1/contacts/links/link-1/push");
  });

  it("offers link and create for a proposal and both resolutions for a conflict", async () => {
    const calls = mockApi([row({ sync_status: "proposed" }), row({ config_id: "cfg-2", label: "Makler", sync_status: "conflict", link_id: "link-1" })]);
    const user = userEvent.setup();
    renderIntl(<LexofficeContactSection contactId={CONTACT} canUpdate canCreateDraft={false} />);
    await waitFor(() => expect(screen.getAllByTestId("lexoffice-contact-row")).toHaveLength(2));
    expect(screen.getByRole("button", { name: "In Lexware Office anlegen" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Verknüpfen" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/decide"))).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/decide"))?.body).toEqual({ action: "link", contact_id: CONTACT });
    await user.click(screen.getByRole("button", { name: "Lexware Stand übernehmen" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/resolve-conflict"))).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/resolve-conflict"))?.body).toEqual({ resolution: "keep_lexoffice" });
  });

  it("hides actions without contacts:update and opens the draft form with accounting:create", async () => {
    mockApi([row()]);
    const user = userEvent.setup();
    renderIntl(<LexofficeContactSection contactId={CONTACT} contactName="Erika" canUpdate={false} canCreateDraft />);
    await waitFor(() => expect(screen.getByTestId("lexoffice-contact-row")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Jetzt abgleichen" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Rechnungsentwurf erstellen" }));
    expect(screen.getByTestId("lexoffice-draft-form")).toBeInTheDocument();
  });

  it("renders nothing when no organisation exists and no draft may be created", async () => {
    mockApi([]);
    const { container } = renderIntl(<LexofficeContactSection contactId={CONTACT} canUpdate canCreateDraft={false} />);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
