import type { components } from "@mhvp/api-client";

import { emptyContact, fromContact, toContactIn } from "./contact-schema";

type ContactOut = components["schemas"]["ContactOut"];

function contact(external_ids: Record<string, string>): ContactOut {
  return {
    id: "c1",
    kind: "person",
    display_name: "Erika Mustermann",
    first_name: "Erika",
    last_name: "Mustermann",
    language: "de",
    blocked: false,
    external_ids,
    completeness: "complete",
    addresses: [],
    phones: [],
    emails: [],
    identifiers: [],
    bank_accounts: [],
    types: [],
    roles: [],
    tags: [],
    version: 1,
    created_at: "2026-09-01T10:00:00Z",
    updated_at: "2026-09-01T10:00:00Z",
    deleted_at: null,
  } as unknown as ContactOut;
}

describe("external ids in the contact form (M3-06)", () => {
  it("shows the known keys and keeps unknown ones", () => {
    const existing = contact({ immoware24: "4711", lexoffice_customer_number: "10005", other: "x" });
    const values = fromContact(existing);
    expect(values.ext_immoware24).toBe("4711");
    expect(values.ext_lexoffice).toBe("10005");
    expect(toContactIn(values, existing).external_ids).toEqual({
      immoware24: "4711",
      lexoffice_customer_number: "10005",
      other: "x",
    });
  });

  it("sets and removes the editable keys", () => {
    const existing = contact({ immoware24: "4711", other: "x" });
    const values = { ...fromContact(existing), ext_immoware24: " ", ext_lexoffice: " 10006 " };
    expect(toContactIn(values, existing).external_ids).toEqual({
      lexoffice_customer_number: "10006",
      other: "x",
    });
    expect(toContactIn(emptyContact()).external_ids).toEqual({});
  });
});
