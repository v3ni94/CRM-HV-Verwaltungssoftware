import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

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
});
