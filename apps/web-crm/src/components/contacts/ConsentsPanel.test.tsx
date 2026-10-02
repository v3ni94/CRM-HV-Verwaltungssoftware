import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ConsentsPanel } from "./ConsentsPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), back: vi.fn() }) }));

describe("ConsentsPanel (AE34)", () => {
  it("marks an objection as such and offers to withdraw it, a consent keeps Widerrufen", () => {
    renderIntl(
      <ConsentsPanel
        contactId="c1"
        consents={[
          { id: "k1", kind: "email_delivery", granted_at: "2026-10-01T10:00:00Z", revoked_at: null, source: "Formular", record_type: "consent", client_evidence_recorded: false },
          {
            id: "k2",
            kind: "marketing",
            granted_at: "2026-10-01T11:00:00Z",
            revoked_at: null,
            source: "Schreiben des Kontakts",
            record_type: "objection",
            client_evidence_recorded: false,
          },
        ]}
      />,
    );
    expect(screen.getByText("(Widerspruch)")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Zurücknehmen" })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Widerrufen" })).toHaveLength(1);
  });

  it("records an objection through the BFF and validates the source (AF19)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}, 201));
    renderIntl(<ConsentsPanel contactId="c1" consents={[]} />);
    const form = screen.getByRole("form", { name: "Widerspruch erfassen" });
    await userEvent.click(within(form).getByRole("button", { name: "Widerspruch speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent("mindestens 2 Zeichen");
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.selectOptions(within(form).getByLabelText("Verarbeitung"), "email_delivery");
    await userEvent.type(within(form).getByLabelText("Quelle des Widerspruchs"), "Schreiben vom 01.10.2026");
    await userEvent.click(within(form).getByRole("button", { name: "Widerspruch speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]![0])).toBe("/api/bff/contacts/c1/objections");
    const body = JSON.parse(String(fetchMock.mock.calls[0]![1]?.body));
    expect(body.kind).toBe("email_delivery");
    expect(body.source).toBe("Schreiben vom 01.10.2026");
    vi.restoreAllMocks();
  });
});
