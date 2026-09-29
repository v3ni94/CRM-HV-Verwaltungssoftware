import { STEPS, stepCount, stepOfHint, stepState } from "./steps";
import type { Full } from "./types";

const base = {
  address: "",
  handover_date: null,
  deposit_amount: null,
  deposit_iban: null,
  deposit_account_holder: null,
  deposit_bank_name: null,
  deposit_note: null,
  internal_note: null,
  internal_contact: null,
  management_number: null,
  participants: [],
  meters: [],
  rooms: [],
  defects: [],
  keys: [],
  items: [],
  notes: [],
  signatures: [],
  documents: [],
  hints: [],
  hint_codes: [],
} as unknown as Full;

describe("steps", () => {
  it("has 13 steps with defects between rooms and keys", () => {
    expect(STEPS).toHaveLength(13);
    expect(STEPS.indexOf("defects")).toBe(STEPS.indexOf("rooms") + 1);
  });

  it.each([
    ["no_address", "object"],
    ["no_date", "object"],
    ["no_participants", "participants"],
    ["no_meters", "meters"],
    ["no_rooms", "rooms"],
    ["no_keys", "keys"],
    ["no_signature", "signatures"],
    ["signatures_invalidated", "signatures"],
    ["iban_invalid", "deposit"],
  ])("marks the step of hint code %s as attention", (code, step) => {
    const p = { ...base, hint_codes: [code] } as Full;
    expect(stepOfHint(code)).toBe(step);
    expect(stepState(step as never, p)).toBe("attention");
    for (const other of STEPS) if (other !== step) expect(stepState(other, p)).not.toBe("attention");
  });

  it("reports filled for content and empty otherwise, with counters per list step", () => {
    const p = {
      ...base,
      address: "Musterweg 12",
      rooms: [{ id: "r1" }],
      signatures: [
        { id: "s1", invalidated_at: null },
        { id: "s2", invalidated_at: "2026-09-25T10:00:00Z" },
      ],
      documents: [
        { id: "d1", kind: "photo", item_id: "r1" },
        { id: "d2", kind: "attachment", item_id: null },
      ],
    } as unknown as Full;
    expect(stepState("object", p)).toBe("filled");
    expect(stepState("rooms", p)).toBe("filled");
    expect(stepCount("rooms", p)).toBe(1);
    expect(stepCount("signatures", p)).toBe(1);
    expect(stepCount("attachments", p)).toBe(1);
    expect(stepCount("object", p)).toBeNull();
    expect(stepState("keys", p)).toBe("empty");
    expect(stepState("deposit", p)).toBe("empty");
    expect(stepState("summary", p)).toBe("empty");
  });

  it("ignores unknown codes", () => {
    expect(stepOfHint("something_new")).toBeNull();
    expect(stepState("object", { ...base, hint_codes: ["something_new"] } as Full)).toBe("empty");
  });
});
