import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { ApproverList } from "./ApproverList";

const roles = [{ id: "r1", code: "approver", permissions: ["banking:approve", "accounting:approve"], parent_role_id: null }];
const base = { status: "active", roles: ["approver"], contact_id: null };
const members = [
  { ...base, membership_id: "m1", user_id: "u1", email: "timo@firma.de", display_name: "Timo Müller", contact_id: "c1" },
  { ...base, membership_id: "m2", user_id: "u2", email: "admin.timo@firma.de", display_name: "Müller, Timo" },
  { ...base, membership_id: "m3", user_id: "u3", email: "anna@firma.de", display_name: "Anna Beispiel" },
  { ...base, membership_id: "m4", user_id: "u4", email: "lese@firma.de", display_name: "Lena Lesen", roles: [] },
];

describe("ApproverList", () => {
  it("lists approvers and flags possible duplicate identities by name", () => {
    renderIntl(<ApproverList members={members} roles={roles} />);
    expect(screen.queryByText("Lena Lesen")).toBeNull();
    expect(screen.getByTestId("approver-summary")).toHaveTextContent("2 Konten mit möglicher Doppelidentität.");
    expect(within(screen.getByTestId("approver-m1")).getByTestId("approver-hint")).toHaveTextContent("Müller, Timo");
    expect(within(screen.getByTestId("approver-m3")).getByText("keiner")).toBeInTheDocument();
    expect(screen.getAllByText("Zahlungsaufträge, Lastschriftläufe").length).toBe(3);
  });

  it("changes the flagging with the criteria and states the hint is not proof", async () => {
    renderIntl(<ApproverList members={members} roles={roles} />);
    await userEvent.click(screen.getByLabelText(/^gleicher Name \(/));
    expect(screen.getByTestId("approver-summary")).toHaveTextContent("Keine Konten mit möglicher Doppelidentität.");
    await userEvent.click(screen.getByLabelText(/^gleicher Name \(/));
    expect(screen.getByTestId("approver-summary")).toHaveTextContent("2 Konten");
    expect(screen.getByText(/ein Hinweis, kein Nachweis/)).toBeInTheDocument();
  });

  it("shows the empty state", () => {
    renderIntl(<ApproverList members={[]} roles={roles} />);
    expect(screen.getByText("Kein aktives Konto mit Zahlungsfreigabe.")).toBeInTheDocument();
  });
});
