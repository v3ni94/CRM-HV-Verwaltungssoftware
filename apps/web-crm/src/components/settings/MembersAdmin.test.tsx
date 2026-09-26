import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MembersAdmin } from "./MembersAdmin";

const ROLE_ID = "01920000-0000-7000-8000-00000000f001";
const MEMBER_ID = "01920000-0000-7000-8000-00000000f002";

const roles = [{ id: ROLE_ID, code: "tenant_admin", name: "Mandantenadministrator", is_system: true, parent_role_id: null, permissions: ["members:read"] }];
const competenceCatalogue = [{ code: "buchhaltung", label: "Buchhaltung" }];

const member = {
  membership_id: MEMBER_ID,
  user_id: "01920000-0000-7000-8000-00000000f003",
  email: "bestand@muellerhv.de",
  display_name: "Bestandsbenutzer",
  roles: ["tenant_admin"],
  status: "active",
  last_login_at: null,
  contact_id: null,
  reply_approval_required: false,
  reply_approval_reason: null,
  reply_approval_until: null,
};

describe("MembersAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("adds a member and resets a password", async () => {
    const created = { ...member, membership_id: "01920000-0000-7000-8000-00000000f004", email: "neu@muellerhv.de", display_name: "Neue Person" };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/bff/tenant/members") && method === "POST") return jsonResponse(created, 201);
      if (url.endsWith(`/api/bff/tenant/members/${MEMBER_ID}/reset-password`) && method === "POST") return jsonResponse(null, 200);
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(
      <MembersAdmin initialMembers={[member]} roles={roles} competenceCatalogue={competenceCatalogue} canCreate canUpdate />,
    );

    // Reset password flow (scoped to the desktop table; the same actions also render in the
    // mobile card list).
    const table = within(screen.getByRole("table"));
    await userEvent.click(table.getByRole("button", { name: "Passwort zurücksetzen" }));
    await userEvent.type(table.getByPlaceholderText("Startpasswort"), "sicheresstartpw1");
    await userEvent.click(table.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByText("Passwort wurde zurückgesetzt.")).toBeInTheDocument());

    // Add member flow.
    await userEvent.type(screen.getByLabelText("E-Mail"), "neu@muellerhv.de");
    await userEvent.type(screen.getByLabelText("Anzeigename"), "Neue Person");
    await userEvent.type(screen.getByLabelText("Startpasswort", { exact: false }), "sicheresstartpw2");
    await userEvent.click(screen.getByRole("button", { name: "Benutzer anlegen" }));

    await waitFor(() => expect(screen.getAllByText("Neue Person").length).toBeGreaterThan(0));
    expect(within(screen.getByRole("table")).getByText("neu@muellerhv.de")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalled();
  });

  it("edits a member's competences", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith(`/api/bff/tenant/members/${MEMBER_ID}/competences`) && method === "PUT") {
        return jsonResponse(null, 204);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(
      <MembersAdmin initialMembers={[member]} roles={roles} competenceCatalogue={competenceCatalogue} canCreate={false} canUpdate />,
    );

    const table = within(screen.getByRole("table"));
    await userEvent.click(table.getByRole("button", { name: "Kompetenzen bearbeiten" }));
    await userEvent.click(screen.getByLabelText("Buchhaltung"));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const call = fetchMock.mock.calls.find(([input, init]) =>
      String(input).endsWith(`/api/bff/tenant/members/${MEMBER_ID}/competences`) && init?.method === "PUT",
    );
    expect(call).toBeDefined();
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ competence_codes: ["buchhaltung"] });
  });

  it("selects legal entities for a tax advisor only (A37)", async () => {
    const HOA1 = "01920000-0000-7000-8000-00000000a001";
    const HOA2 = "01920000-0000-7000-8000-00000000a002";
    const TAX_ID = "01920000-0000-7000-8000-00000000f005";
    const taxAdvisor = { ...member, membership_id: TAX_ID, email: "stb@example.org", display_name: "Steuerberatung", roles: ["tax_advisor"], legal_entity_ids: [] };
    const options = [
      { id: HOA1, name: "WEG Musterstraße 1", kind: "hoa" },
      { id: HOA2, name: "WEG Musterstraße 2", kind: "hoa" },
    ];
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith(`/api/bff/tenant/members/${TAX_ID}/legal-entities`) && method === "PUT") {
        return new Response(null, { status: 204 });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(
      <MembersAdmin
        initialMembers={[member, taxAdvisor]}
        roles={roles}
        competenceCatalogue={competenceCatalogue}
        legalEntityOptions={options}
        canCreate={false}
        canUpdate
        canUpdateScope
      />,
    );

    const table = within(screen.getByRole("table"));
    // Only the tax advisor row offers the scope editor; the administrator row does not.
    expect(table.getAllByRole("button", { name: "Rechtsträger (0)" })).toHaveLength(1);
    await userEvent.click(table.getByRole("button", { name: "Rechtsträger (0)" }));
    expect(screen.getByText("Ohne Auswahl hat der Steuerberater keinen Zugriff auf Buchhaltungsdaten.")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("WEG Musterstraße 1"));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const call = fetchMock.mock.calls.find(([input, init]) =>
      String(input).endsWith(`/api/bff/tenant/members/${TAX_ID}/legal-entities`) && init?.method === "PUT",
    );
    expect(call).toBeDefined();
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ legal_entity_ids: [HOA1] });
    await waitFor(() => expect(table.getByRole("button", { name: "Rechtsträger (1)" })).toBeInTheDocument());
  });

  it("sets the reply approval flag of a member (M20-03) through the settings permission", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith(`/api/bff/tenant/members/${MEMBER_ID}/reply-approval`) && init?.method === "PUT") {
        return jsonResponse({ ...member, reply_approval_required: true, reply_approval_reason: "azubi", reply_approval_until: "2027-03-31" });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(
      <MembersAdmin initialMembers={[member]} roles={roles} competenceCatalogue={competenceCatalogue} canCreate canUpdate canUpdateScope />,
    );
    const table = within(screen.getByRole("table"));
    await userEvent.click(table.getByRole("button", { name: "Freigabepflicht für Ticketantworten" }));
    const editor = within(table.getByTestId("reply-approval-editor"));
    await userEvent.click(editor.getByRole("checkbox"));
    await userEvent.selectOptions(editor.getByRole("combobox"), "azubi");
    await userEvent.type(editor.getByLabelText("Befristet bis"), "2027-03-31");
    await userEvent.click(editor.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(table.getByText(/Freigabepflicht: Azubi/)).toBeInTheDocument());
    expect(table.getByText(/bis 31.03.2027/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/bff/tenant/members/${MEMBER_ID}/reply-approval`,
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ required: true, reason: "azubi", until: "2027-03-31" }) }),
    );
  });

  it("hides the reply approval editor without the settings permission", () => {
    renderIntl(<MembersAdmin initialMembers={[member]} roles={roles} competenceCatalogue={competenceCatalogue} canCreate canUpdate />);
    expect(screen.queryByTestId("reply-approval-toggle")).not.toBeInTheDocument();
  });
});
