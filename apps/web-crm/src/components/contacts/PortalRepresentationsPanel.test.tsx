import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalRepresentationsPanel, type Representation } from "./PortalRepresentationsPanel";

const ME = "11111111-1111-7111-8111-111111111111";
const OWNER = "22222222-2222-7222-8222-222222222222";
const ACCOUNT = "33333333-3333-7333-8333-333333333333";
const DOC = "44444444-4444-7444-8444-444444444444";

const account = { id: ACCOUNT, email: "vertreter@example.org", status: "active" };
const rep: Representation = {
  id: "55555555-5555-7555-8555-555555555555",
  account_id: ACCOUNT,
  principal_contact_id: OWNER,
  document_id: DOC,
  valid_from: "2026-01-01",
  valid_to: null,
  status: "active",
  note: "Vollmacht liegt vor",
  revoked_at: null,
  representative_contact_id: ME,
  representative_email: "vertreter@example.org",
};

function route(map: Record<string, unknown>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    for (const [key, value] of Object.entries(map)) if (url.includes(key)) return jsonResponse(value);
    return jsonResponse([]);
  });
}

describe("PortalRepresentationsPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the powers of attorney of this contact with the represented person", async () => {
    route({
      "portal-admin/accounts": [account],
      "portal-admin/representations": [rep, { ...rep, id: "other", account_id: "99999999-9999-7999-8999-999999999999", principal_contact_id: "88888888-8888-7888-8888-888888888888" }],
      [`contacts/${OWNER}/name`]: { id: OWNER, display_name: "Eva Eigentümer" },
    });
    renderIntl(<PortalRepresentationsPanel contactId={ME} canManage={false} />);
    const rows = await screen.findAllByTestId("representation-row");
    expect(rows).toHaveLength(1);
    await screen.findByRole("link", { name: "Eva Eigentümer" });
    expect(rows[0]).toHaveTextContent("Vertritt");
    expect(rows[0]).toHaveTextContent("01.01.2026");
    expect(rows[0]).toHaveTextContent("unbefristet");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows who represents this contact when it is the principal", async () => {
    route({
      "portal-admin/accounts": [],
      "portal-admin/representations": [{ ...rep, principal_contact_id: ME, representative_contact_id: OWNER, representative_email: "v@example.org" }],
      [`contacts/${OWNER}/name`]: { id: OWNER, display_name: "Victor Vertreter" },
    });
    renderIntl(<PortalRepresentationsPanel contactId={ME} canManage />);
    const row = await screen.findByTestId("representation-row");
    expect(row).toHaveTextContent("Vertreten durch");
    expect(await screen.findByRole("link", { name: "Victor Vertreter" })).toHaveAttribute("href", `/kontakte/${OWNER}`);
  });

  it("revokes an active power of attorney after confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = route({
      "portal-admin/accounts": [account],
      "portal-admin/representations": [rep],
      [`contacts/${OWNER}/name`]: { id: OWNER, display_name: "Eva Eigentümer" },
    });
    renderIntl(<PortalRepresentationsPanel contactId={ME} canManage />);
    await screen.findByTestId("representation-row");
    fireEvent.click(screen.getByRole("button", { name: "Widerrufen" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith(`/representations/${rep.id}/revoke`) && (c[1] as RequestInit).method === "POST")).toBe(true),
    );
  });

  it("requires principal, document and start date before anything is sent", async () => {
    const fetchMock = route({ "portal-admin/accounts": [account], "portal-admin/representations": [] });
    renderIntl(<PortalRepresentationsPanel contactId={ME} canManage />);
    await screen.findByText("Keine Vollmachten hinterlegt.");
    const calls = fetchMock.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Vollmacht anlegen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte Vertretenen, Vollmachtsdokument und Beginn angeben.");
    expect(fetchMock.mock.calls.length).toBe(calls);
  });

  it("uploads the document and then creates the power of attorney", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/bff/documents")) return jsonResponse({ id: DOC }, 201);
      if (url.endsWith("/portal-admin/representations") && (init as RequestInit | undefined)?.method === "POST") return jsonResponse(rep, 201);
      if (url.includes("/api/bff/contacts?")) return jsonResponse({ items: [{ id: OWNER, display_name: "Eva Eigentümer" }] });
      if (url.includes("portal-admin/accounts")) return jsonResponse([account]);
      return jsonResponse([]);
    });
    renderIntl(<PortalRepresentationsPanel contactId={ME} canManage />);
    await screen.findByText("Keine Vollmachten hinterlegt.");
    fireEvent.change(screen.getByLabelText("Vertretener Kontakt"), { target: { value: "Eva" } });
    fireEvent.click(screen.getByRole("button", { name: "Suchen" }));
    fireEvent.click(await screen.findByRole("button", { name: "Eva Eigentümer" }));
    await userEvent.upload(screen.getByTestId("representation-document"), new File(["%PDF-1.4"], "vollmacht.pdf", { type: "application/pdf" }));
    fireEvent.change(screen.getByLabelText("Gültig ab"), { target: { value: "2026-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Vollmacht anlegen" }));
    await waitFor(() => expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith("/portal-admin/representations") && (c[1] as RequestInit | undefined)?.method === "POST")).toBe(true));
    const upload = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/api/bff/documents")) as [string, RequestInit];
    expect(JSON.parse(String((upload[1].body as FormData).get("links")))).toEqual([{ entity_type: "contact", entity_id: OWNER, role: "evidence" }]);
    const create = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/portal-admin/representations") && (c[1] as RequestInit | undefined)?.method === "POST") as [string, RequestInit];
    expect(JSON.parse(String(create[1].body))).toEqual({
      account_id: ACCOUNT,
      principal_contact_id: OWNER,
      document_id: DOC,
      valid_from: "2026-01-01",
      valid_to: null,
      note: null,
    });
  });
});
