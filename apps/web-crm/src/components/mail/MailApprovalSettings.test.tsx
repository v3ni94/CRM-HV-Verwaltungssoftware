import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MailApprovalSettings } from "./MailApprovalSettings";

const MEMBERS = [
  { user_id: "u-1", display_name: "Anna Beispiel" },
  { user_id: "u-2", display_name: "Ben Beispiel" },
];

describe("MailApprovalSettings", () => {
  afterEach(() => vi.restoreAllMocks());

  it("patches the tenant mail approval mode", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/bff/tenant/settings") && init?.method === "PATCH") {
        return jsonResponse({ mail_approval_mode: JSON.parse(String(init.body)).mail_approval_mode });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(
      <MailApprovalSettings initial="external_only" canUpdate deputies={[]} members={MEMBERS} currentUserId="u-1" />,
    );
    expect(screen.getByLabelText("Nur externe Empfänger freigeben")).toBeChecked();
    await userEvent.setup().click(screen.getByLabelText("Alle Antworten freigeben"));
    await waitFor(() => expect(screen.getByText("Gespeichert.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/tenant/settings",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ mail_approval_mode: "all" }) }),
    );
  });

  it("is read only without the update permission", () => {
    renderIntl(<MailApprovalSettings initial="off" canUpdate={false} deputies={[]} members={MEMBERS} currentUserId="u-1" />);
    expect(screen.getByLabelText("Keine Pflichtfreigabe")).toBeDisabled();
    expect(screen.getByText("Die Änderung erfordert das Recht Mandanteneinstellungen ändern.")).toBeInTheDocument();
  });

  it("lists deputies and creates a new one", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/bff/mail-approval/deputies") && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        return jsonResponse({ id: "d-1", ...body }, 201);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(
      <MailApprovalSettings initial="external_only" canUpdate={false} deputies={[]} members={MEMBERS} currentUserId="u-1" />,
    );
    expect(screen.getByText("Derzeit keine Vertretung eingetragen.")).toBeInTheDocument();
    await userEvent.setup().selectOptions(screen.getByLabelText("Vertreter"), "u-2");
    await userEvent.setup().type(screen.getByLabelText("Beginn"), "2026-10-01T08:00");
    await userEvent.setup().type(screen.getByLabelText("Ende"), "2026-10-10T18:00");
    await userEvent.setup().click(screen.getByRole("button", { name: "Vertretung anlegen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/mail-approval/deputies")) ?? [];
    expect(JSON.parse(String((init as RequestInit).body)).absent_user_id).toBe("u-1");
    expect(JSON.parse(String((init as RequestInit).body)).deputy_user_id).toBe("u-2");
  });

  it("revokes a deputy", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/bff/mail-approval/deputies/d-1") && init?.method === "DELETE") {
        return jsonResponse(null, 204);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(
      <MailApprovalSettings
        initial="external_only"
        canUpdate
        deputies={[
          {
            id: "d-1",
            absent_user_id: "u-1",
            deputy_user_id: "u-2",
            starts_at: "2026-10-01T08:00:00Z",
            ends_at: "2026-10-10T18:00:00Z",
            note: null,
          },
        ]}
        members={MEMBERS}
        currentUserId="u-1"
      />,
    );
    await userEvent.setup().click(screen.getByRole("button", { name: "Widerrufen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/bff/mail-approval/deputies/d-1", expect.objectContaining({ method: "DELETE" })));
  });
});
