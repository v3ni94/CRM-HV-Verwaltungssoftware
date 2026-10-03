/** GAM-205: Hinweise auf mögliche Doppelidentitäten unter den Konten mit Zahlungsfreigabe.
 *  Reine Anzeigehilfe: Die Vier-Augen-Prüfung der API vergleicht Benutzer-IDs und bleibt unverändert.
 *  Was als unabhängiger Freigeber gilt, ist eine offene Entscheidung (OPEN_QUESTIONS AP19-01). */

export type ApproverMember = {
  membership_id: string;
  user_id: string;
  email: string;
  display_name: string;
  status: string;
  roles: string[];
  contact_id?: string | null;
};
export type ApproverRole = { id: string; code: string; permissions: string[]; parent_role_id?: string | null };
export type IdentityCriterion = "contact" | "name" | "emailVariant";
export const IDENTITY_CRITERIA: IdentityCriterion[] = ["contact", "name", "emailVariant"];
export const PAYMENT_PERMISSION = "banking:approve";
export const DIRECT_DEBIT_PERMISSION = "accounting:approve";

/** Permissions of a role code including the inherited parent roles. */
export function effectivePermissions(codes: string[], roles: ApproverRole[]): Set<string> {
  const byId = new Map(roles.map((r) => [r.id, r]));
  const byCode = new Map(roles.map((r) => [r.code, r]));
  const out = new Set<string>();
  const seen = new Set<string>();
  const stack = codes.map((c) => byCode.get(c)).filter((r): r is ApproverRole => !!r);
  while (stack.length > 0) {
    const role = stack.pop() as ApproverRole;
    if (seen.has(role.id)) continue;
    seen.add(role.id);
    for (const p of role.permissions) out.add(p);
    const parent = role.parent_role_id ? byId.get(role.parent_role_id) : undefined;
    if (parent) stack.push(parent);
  }
  return out;
}

const fold = (value: string) =>
  value
    .toLowerCase()
    .replace(/ä/g, "ae")
    .replace(/ö/g, "oe")
    .replace(/ü/g, "ue")
    .replace(/ß/g, "ss")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");

/** Name key: words lower-cased and sorted, so "Müller, Timo" equals "Timo Müller". */
export function nameKey(name: string): string {
  return fold(name)
    .split(/[\s,;]+/)
    .filter(Boolean)
    .sort()
    .join(" ");
}

/** E-Mail key: domain plus local part without digits, dots and a plus suffix. */
export function emailKey(email: string): string | null {
  const at = email.lastIndexOf("@");
  if (at < 1) return null;
  const local = fold(email.slice(0, at)).replace(/\+.*$/, "").replace(/[\d._-]/g, "");
  return local ? `${local}@${fold(email.slice(at + 1))}` : null;
}

export type IdentityHint = { with: ApproverMember; reasons: IdentityCriterion[] };

/** For each member the other members that match one of the enabled criteria. */
export function identityHints(members: ApproverMember[], enabled: IdentityCriterion[]): Map<string, IdentityHint[]> {
  const result = new Map<string, IdentityHint[]>();
  for (const a of members) {
    const hints: IdentityHint[] = [];
    for (const b of members) {
      if (a.membership_id === b.membership_id || a.user_id === b.user_id) continue;
      const reasons: IdentityCriterion[] = [];
      if (enabled.includes("contact") && a.contact_id && a.contact_id === b.contact_id) reasons.push("contact");
      if (enabled.includes("name") && nameKey(a.display_name) !== "" && nameKey(a.display_name) === nameKey(b.display_name)) reasons.push("name");
      const ka = emailKey(a.email);
      if (enabled.includes("emailVariant") && ka !== null && ka === emailKey(b.email)) reasons.push("emailVariant");
      if (reasons.length > 0) hints.push({ with: b, reasons });
    }
    result.set(a.membership_id, hints);
  }
  return result;
}

/** Active members holding payment order or direct debit approval. */
export function approvers(members: ApproverMember[], roles: ApproverRole[]) {
  return members
    .filter((m) => m.status === "active")
    .map((m) => {
      const perms = effectivePermissions(m.roles, roles);
      return { member: m, payments: perms.has(PAYMENT_PERMISSION), directDebits: perms.has(DIRECT_DEBIT_PERMISSION) };
    })
    .filter((row) => row.payments || row.directDebits);
}
