import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { membersHref, UserMappingTable, type UserMappingRow } from "./UserMappingTable";

const rows: UserMappingRow[] = [
  {
    source_id: "501",
    email: "alt-admin@example.org",
    display_name: "Alt Admin",
    objektakte_role: "admin",
    objektakte_status: "active",
    proposed_role: "tenant_admin",
    crm_user_id: null,
    crm_member_roles: null,
    action: "invite",
  },
  {
    source_id: "502",
    email: "clerk@example.org",
    display_name: "Sach Bearbeiter",
    objektakte_role: "sachbearbeiter",
    objektakte_status: "active",
    proposed_role: "standard",
    crm_user_id: "u-2",
    crm_member_roles: ["standard"],
    action: "already_member",
  },
  {
    source_id: "504",
    email: "gast@example.org",
    display_name: "Gast Nutzer",
    objektakte_role: "gast",
    objektakte_status: "invited",
    proposed_role: null,
    crm_user_id: null,
    crm_member_roles: null,
    action: "manual",
  },
  {
    source_id: "503",
    email: "weg@example.org",
    display_name: "Geloescht",
    objektakte_role: "sachbearbeiter",
    objektakte_status: "deleted",
    proposed_role: "standard",
    crm_user_id: null,
    crm_member_roles: null,
    action: "skip",
  },
];

describe("UserMappingTable", () => {
  it("lists every source user with role proposal, action and a prefilled member link", () => {
    renderIntl(<UserMappingTable rows={rows} />);
    const table = screen.getByTestId("user-mapping");
    expect(table.querySelectorAll("tbody tr")).toHaveLength(4);
    expect(screen.getByText("Einladen")).toBeInTheDocument();
    expect(screen.getByText("Bereits Mitglied")).toBeInTheDocument();
    expect(screen.getByText("Manuell entscheiden")).toBeInTheDocument();
    expect(screen.getByText("Überspringen")).toBeInTheDocument();
    expect(screen.getByText("Kein Vorschlag")).toBeInTheDocument();
    expect(screen.getByText("(deleted)")).toBeInTheDocument();

    const invite = screen.getAllByRole("link", { name: "Einladen mit Vorbelegung" });
    expect(invite).toHaveLength(1);
    expect(invite[0]).toHaveAttribute("href", "/einstellungen/benutzer?email=alt-admin%40example.org&role=tenant_admin");
    // Skipped accounts get no link, manual ones only the plain link without a role.
    expect(screen.getAllByRole("link")).toHaveLength(3);
    expect(membersHref(rows[2]!)).toBe("/einstellungen/benutzer?email=gast%40example.org");
  });

  it("shows an empty state", () => {
    renderIntl(<UserMappingTable rows={[]} />);
    expect(screen.getByText("Der Export enthielt keine Benutzer.")).toBeInTheDocument();
  });
});
