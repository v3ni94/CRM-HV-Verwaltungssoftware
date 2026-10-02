import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { RolesAdmin } from "./RolesAdmin";

const roles = [
  { id: "r1", code: "system_role", name: "Systemrolle A", is_system: true, permissions: ["contacts:read"] },
  { id: "r2", code: "custom", name: "Eigene Rolle", is_system: false, permissions: ["tickets:read"] },
] as never;

describe("RolesAdmin (GAH-407)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders roles read only without the update right", () => {
    renderIntl(<RolesAdmin initialRoles={roles} canUpdate={false} />);
    expect(screen.getByText("Systemrolle")).toBeInTheDocument();
    expect(screen.getByText("contacts:read")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Speichern" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Rolle anlegen" })).not.toBeInTheDocument();
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  });

  it("makes system roles not editable even with the update right", () => {
    renderIntl(<RolesAdmin initialRoles={[(roles as never[])[0]] as never} canUpdate />);
    expect(screen.queryByRole("button", { name: "Speichern" })).not.toBeInTheDocument();
  });

  it("saves the permissions of a custom role with PUT", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({}));
    renderIntl(<RolesAdmin initialRoles={roles} canUpdate />);
    const save = screen.getAllByRole("button", { name: "Speichern" });
    expect(save).toHaveLength(1);
    await userEvent.click(save[0]!);
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(String(url)).toBe("/api/bff/tenant/roles/r2/permissions");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ permissions: ["tickets:read"] });
  });

  it("creates a role and shows a refusal", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ code: "X", title: "Code vergeben", status: 409 }, 409));
    renderIntl(<RolesAdmin initialRoles={roles} canUpdate />);
    await userEvent.type(screen.getByLabelText("Code"), "neu");
    await userEvent.type(screen.getByLabelText("Name"), "Neue Rolle");
    await userEvent.click(screen.getByRole("button", { name: "Rolle anlegen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({ code: "neu", name: "Neue Rolle", permissions: [] });
  });
});
