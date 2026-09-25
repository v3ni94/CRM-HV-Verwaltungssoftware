import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalRolePermissions } from "./PortalRolePermissions";

const catalogue = ["documents:read", "tickets:read"];
const initialRoles = { standard: ["documents:read"], tenant_admin: ["documents:read", "tickets:read"] };

describe("PortalRolePermissions (Portalrechte je Rolle, docs/rules/M2-07.md)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("hides edit controls without tenant_settings:update", () => {
    renderIntl(<PortalRolePermissions catalogue={catalogue} initialRoles={initialRoles} canUpdate={false} />);
    expect(screen.getByLabelText("standard: documents:read")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Speichern" })).not.toBeInTheDocument();
  });

  it("toggles a permission and saves the matrix", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/bff/tenant/portal-role-permissions") && method === "PUT") {
        return jsonResponse({ roles: { ...initialRoles, standard: ["documents:read", "tickets:read"] } });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(<PortalRolePermissions catalogue={catalogue} initialRoles={initialRoles} canUpdate />);
    await userEvent.click(screen.getByLabelText("standard: tickets:read"));
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(screen.getByText("Gespeichert.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/tenant/portal-role-permissions",
      expect.objectContaining({ method: "PUT" }),
    );
  });

  it("resyncs existing staff grants", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/bff/tenant/portal-role-permissions/resync") && method === "POST") {
        return jsonResponse({ members: 3 });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(<PortalRolePermissions catalogue={catalogue} initialRoles={initialRoles} canUpdate />);
    await userEvent.click(screen.getByRole("button", { name: "Auf bestehende Zugänge anwenden" }));
    await waitFor(() =>
      expect(screen.getByText("Auf 3 bestehende Zugänge angewendet.")).toBeInTheDocument(),
    );
  });
});
