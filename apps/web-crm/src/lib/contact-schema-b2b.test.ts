import { describe, expect, it } from "vitest";

import { buildContactSchema, emptyContact } from "./contact-schema";

// GAA-05 (AF07): B2B mandates are refused in the form like the API (MHVP-CONT-0033).
function bank(scheme: "core" | "b2b") {
  return {
    label: "",
    kind: "" as const,
    is_default: false,
    iban: "DE89370400440532013000",
    bic: "",
    bank_name: "",
    holder: "",
    valid_from: "2026-01-01",
    valid_to: "",
    sepa_enabled: false,
    mandate_reference: "",
    mandate_signed_on: "",
    mandate_granted_via: "" as const,
    mandate_note: "",
    mandate_document_id: "",
    mandate_scheme: scheme,
  };
}

function messages(scheme: "core" | "b2b"): string[] {
  const schema = buildContactSchema((k) => k);
  const result = schema.safeParse({ ...emptyContact(), bank_accounts: [bank(scheme)] });
  return result.success ? [] : result.error.issues.map((i) => i.message);
}

describe("B2B mandate", () => {
  it("is refused", () => {
    expect(messages("b2b")).toContain("mandateB2bUnsupported");
  });
  it("core is not refused for the scheme", () => {
    expect(messages("core")).not.toContain("mandateB2bUnsupported");
  });
});
