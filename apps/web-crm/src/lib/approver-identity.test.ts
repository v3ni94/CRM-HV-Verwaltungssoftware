import { approvers, effectivePermissions, emailKey, identityHints, nameKey, type ApproverMember, type ApproverRole } from "./approver-identity";

const member = (id: string, over: Partial<ApproverMember>): ApproverMember => ({
  membership_id: `m-${id}`,
  user_id: `u-${id}`,
  email: `${id}@example.test`,
  display_name: `Person ${id}`,
  status: "active",
  roles: ["approver"],
  contact_id: null,
  ...over,
});
const roles: ApproverRole[] = [
  { id: "r1", code: "approver", permissions: ["banking:approve"], parent_role_id: null },
  { id: "r2", code: "child", permissions: ["banking:read"], parent_role_id: "r3" },
  { id: "r3", code: "parent", permissions: ["accounting:approve"], parent_role_id: null },
  { id: "r4", code: "reader", permissions: ["banking:read"], parent_role_id: null },
];

describe("approver identity", () => {
  it("inherits permissions from parent roles", () => {
    expect([...effectivePermissions(["child"], roles)].sort()).toEqual(["accounting:approve", "banking:read"]);
  });

  it("lists only active members with an approval permission", () => {
    const rows = approvers(
      [member("a", {}), member("b", { roles: ["reader"] }), member("c", { status: "blocked" }), member("d", { roles: ["child"] })],
      roles,
    );
    expect(rows.map((r) => r.member.membership_id)).toEqual(["m-a", "m-d"]);
    expect(rows[1]).toMatchObject({ payments: false, directDebits: true });
  });

  it("normalises names and email variants", () => {
    expect(nameKey("Müller, Timo")).toBe(nameKey("Timo Mueller"));
    expect(emailKey("timo.mueller2+x@firma.de")).toBe(emailKey("timomueller@FIRMA.de"));
    expect(emailKey("timo@firma.de")).not.toBe(emailKey("timo@andere.de"));
    expect(emailKey("kaputt")).toBeNull();
  });

  it("flags same contact, same name and email variants, honouring the enabled criteria", () => {
    const list = [
      member("a", { display_name: "Timo Müller", contact_id: "c1", email: "timo@firma.de" }),
      member("b", { display_name: "Müller, Timo", contact_id: null, email: "x@firma.de" }),
      member("c", { display_name: "Anna Beispiel", contact_id: "c1", email: "timo2@firma.de" }),
      member("d", { display_name: "Dritter", email: "dritter@firma.de" }),
    ];
    const all = identityHints(list, ["contact", "name", "emailVariant"]);
    expect(all.get("m-a")?.map((h) => [h.with.membership_id, h.reasons])).toEqual([
      ["m-b", ["name"]],
      ["m-c", ["contact", "emailVariant"]],
    ]);
    expect(all.get("m-d")).toEqual([]);
    expect(identityHints(list, ["name"]).get("m-c")).toEqual([]);
  });

  it("never flags the same user twice", () => {
    const a = member("a", {});
    expect(identityHints([a, { ...a, membership_id: "m-x" }], ["name"]).get("m-a")).toEqual([]);
  });
});
