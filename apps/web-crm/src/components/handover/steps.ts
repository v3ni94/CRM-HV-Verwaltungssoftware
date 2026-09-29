import type { Full } from "./types";

/** The 13 client steps of the editor in their fixed order (operator question: the order is
 *  not changed by M31). `defects` is a step of its own and a valid `current_step`. */
export const STEPS = [
  "object",
  "participants",
  "deposit",
  "internal",
  "meters",
  "rooms",
  "defects",
  "keys",
  "items",
  "notes",
  "attachments",
  "signatures",
  "summary",
] as const;
export type Step = (typeof STEPS)[number];

export type StepState = "attention" | "filled" | "empty";

/** Hint code of the API (`hint_codes`) -> the step that resolves it. Codes, never texts. */
const HINT_STEP: Record<string, Step> = {
  no_address: "object",
  no_date: "object",
  no_participants: "participants",
  no_meters: "meters",
  no_rooms: "rooms",
  no_keys: "keys",
  no_signature: "signatures",
  signatures_invalidated: "signatures",
  iban_invalid: "deposit",
};

export function stepOfHint(code: string): Step | null {
  return HINT_STEP[code] ?? null;
}

/** Counter shown on the step chip: number of records of the step, null for steps without a
 *  list. Attachments count files that are not photos of a sub record (same condition as the
 *  attachments tab). */
export function stepCount(step: Step, p: Full): number | null {
  switch (step) {
    case "participants":
    case "meters":
    case "rooms":
    case "defects":
    case "keys":
    case "items":
    case "notes":
      return p[step].length;
    case "attachments":
      return p.documents.filter((d) => d.kind === "attachment" || (d.kind === "photo" && !d.item_id)).length;
    case "signatures":
      return p.signatures.filter((s) => !s.invalidated_at).length;
    default:
      return null;
  }
}

/** Whether a step without a counter holds content (object: address or date, deposit: any
 *  deposit field, internal: any internal field, summary: never). */
function hasContent(step: Step, p: Full): boolean {
  switch (step) {
    case "object":
      return Boolean(p.address || p.handover_date);
    case "deposit":
      return Boolean(p.deposit_amount || p.deposit_iban || p.deposit_account_holder || p.deposit_bank_name || p.deposit_note);
    case "internal":
      return Boolean(p.internal_note || p.internal_contact || p.management_number);
    default:
      return false;
  }
}

/** Status dot of a step: `attention` when a hint code points at it, `filled` when it holds
 *  content, `empty` otherwise. */
export function stepState(step: Step, p: Full): StepState {
  const codes = p.hint_codes ?? [];
  if (codes.some((c) => stepOfHint(c) === step)) return "attention";
  const count = stepCount(step, p);
  if (count !== null ? count > 0 : hasContent(step, p)) return "filled";
  return "empty";
}
