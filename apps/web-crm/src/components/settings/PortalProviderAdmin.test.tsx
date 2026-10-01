import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalProviderAdmin } from "./PortalProviderAdmin";

const CONTACT = "01920000-0000-7000-8000-0000000000c1";
const ACCOUNT = "01920000-0000-7000-8000-0000000000a1";
const ENTITY = "01920000-0000-7000-8000-0000000000e1";
const WINDOW = {
  id: "01920000-0000-7000-8000-0000000000b1",
  provider_contact_id: CONTACT,
  starts_at: "2099-01-05T06:00:00Z",
  ends_at: "2099-01-05T14:00:00Z",
  kind: "unavailable",
  note: "Urlaub",
};

function mockApi(calls: { url: string; init?: RequestInit }[]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push({ url, ...(init ? { init } : {}) });
    const method = init?.method ?? "GET";
    if (url.startsWith("/api/bff/contacts?")) return jsonResponse({ items: [{ id: CONTACT, display_name: "Elektro Meier" }] });
    if (url.includes("/provider-availability?")) return jsonResponse([WINDOW]);
    if (url.includes("/portal-admin/accounts?")) return jsonResponse([{ id: ACCOUNT, email: "meier@example.test", status: "active" }]);
    if (url.endsWith("/document-class-grants") && method === "GET") return jsonResponse([]);
    if (url.endsWith("/document-class-grants") && method === "POST") {
      return jsonResponse({ id: "g1", valid_from: "2026-10-01", valid_to: null, ...JSON.parse(String(init?.body)) }, 201);
    }
    if (url.endsWith("/provider-availability") && method === "POST") {
      return jsonResponse({ id: "w2", ...JSON.parse(String(init?.body)) }, 201);
    }
    if (method === "DELETE") return new Response(null, { status: 204 });
    return jsonResponse({}, 404);
  });
}

async function pickProvider(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Dienstleister suchen"), "Meier");
  await user.click(screen.getByRole("button", { name: "Suchen" }));
  await user.click(await screen.findByRole("button", { name: "Elektro Meier" }));
  await screen.findByTestId("provider-windows");
}

describe("PortalProviderAdmin (GA11-04)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists windows of the provider and removes one", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    mockApi(calls);
    const user = userEvent.setup();
    renderIntl(<PortalProviderAdmin canManage legalEntities={[{ id: ENTITY, name: "WEG Musterweg" }]} documentClasses={["abrechnungsbeleg"]} />);
    await pickProvider(user);
    expect(screen.getByTestId("provider-windows")).toHaveTextContent("Urlaub");
    expect(screen.getByTestId("provider-windows")).toHaveTextContent("nicht verfügbar");
    await user.click(screen.getByRole("button", { name: "Entfernen" }));
    await waitFor(() => expect(screen.queryByText(/Urlaub/)).not.toBeInTheDocument());
    expect(calls.at(-1)?.url).toBe(`/api/bff/portal-admin/provider-availability/${WINDOW.id}`);
  });

  it("creates a window with timezone aware times and validates the order", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    mockApi(calls);
    const user = userEvent.setup();
    renderIntl(<PortalProviderAdmin canManage legalEntities={[]} documentClasses={[]} />);
    await pickProvider(user);
    await user.click(screen.getByRole("button", { name: "Zeitfenster erfassen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte Beginn und Ende angeben.");
    await user.type(screen.getByLabelText("Beginn"), "2099-02-01T08:00");
    await user.type(screen.getByLabelText("Ende"), "2099-02-01T07:00");
    await user.click(screen.getByRole("button", { name: "Zeitfenster erfassen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Das Ende muss nach dem Beginn liegen.");
    await user.clear(screen.getByLabelText("Ende"));
    await user.type(screen.getByLabelText("Ende"), "2099-02-01T16:00");
    await user.click(screen.getByRole("button", { name: "Zeitfenster erfassen" }));
    await waitFor(() => expect(calls.some((c) => c.init?.method === "POST")).toBe(true));
    const sent = JSON.parse(String(calls.find((c) => c.init?.method === "POST")?.init?.body)) as Record<string, string>;
    expect(sent.provider_contact_id).toBe(CONTACT);
    expect(sent.starts_at).toMatch(/Z$/);
    expect(sent.kind).toBe("available");
  });

  it("releases a document class for the portal account", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    mockApi(calls);
    const user = userEvent.setup();
    renderIntl(<PortalProviderAdmin canManage legalEntities={[{ id: ENTITY, name: "WEG Musterweg" }]} documentClasses={["abrechnungsbeleg"]} />);
    await pickProvider(user);
    await user.click(screen.getByRole("button", { name: "Klasse freigeben" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte Rechtsträger und Unterlagenklasse wählen.");
    await user.selectOptions(screen.getByLabelText("Rechtsträger"), ENTITY);
    await user.selectOptions(screen.getByLabelText("Unterlagenklasse"), "abrechnungsbeleg");
    await user.click(screen.getByRole("button", { name: "Klasse freigeben" }));
    const grants = await screen.findByTestId("class-grants");
    expect(grants).toHaveTextContent("abrechnungsbeleg, WEG Musterweg, Dienstleister");
    const post = calls.find((c) => c.url.endsWith("/document-class-grants") && c.init?.method === "POST");
    expect(post?.url).toBe(`/api/bff/portal-admin/accounts/${ACCOUNT}/document-class-grants`);
    expect(JSON.parse(String(post?.init?.body))).toEqual({ legal_entity_id: ENTITY, document_class: "abrechnungsbeleg", role: "provider" });
  });

  it("hides the forms without management permission", async () => {
    mockApi([]);
    const user = userEvent.setup();
    renderIntl(<PortalProviderAdmin canManage={false} legalEntities={[]} documentClasses={[]} />);
    await pickProvider(user);
    expect(screen.queryByRole("button", { name: "Zeitfenster erfassen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Klasse freigeben" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Entfernen" })).not.toBeInTheDocument();
  });
});
