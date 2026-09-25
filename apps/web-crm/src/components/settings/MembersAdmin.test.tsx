import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MembersAdmin } from "./MembersAdmin";

const ROLE_ID = "01920000-0000-7000-8000-00000000f001";
const MEMBER_ID = "01920000-0000-7000-8000-00000000f002";

const roles = [{ id: ROLE_ID, code: "tenant_admin", name: "Mandantenadministrator", is_system: true, parent_role_id: null, permissions: ["members:read"] }];

const member = {
  membership_id: MEMBER_ID,
  user_id: "01920000-0000-7000-8000-00000000f003",
  email: "bestand@muellerhv.de",
  display_name: "Bestandsbenutzer",
  roles: ["tenant_admin"],
  status: "active",
  last_login_at: null,
  contact_id: null,
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

    renderIntl(<MembersAdmin initialMembers={[member]} roles={roles} canCreate canUpdate />);

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
});
