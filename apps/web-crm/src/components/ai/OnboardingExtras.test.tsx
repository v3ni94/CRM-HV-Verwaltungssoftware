import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import type { PropertyParty } from "@/lib/ai";
import { jsonResponse, renderIntl } from "@/test/intl";

import { EMPTY_EXTRAS, EntityDecisions, entityDecisions, extrasPayload, extrasProblems, OnboardingExtras, parseKeyValues, resolvePayload, type ExtrasState } from "./OnboardingExtras";
import { PersonMatchTable } from "./PersonMatchTable";

function Harness({ onState }: { onState: (s: ExtrasState) => void }) {
  const [state, setState] = useState<ExtrasState>(EMPTY_EXTRAS);
  onState(state);
  return <OnboardingExtras state={state} onChange={setState} />;
}

describe("parseKeyValues", () => {
  it("reads comma and point decimals and returns unreadable lines", () => {
    expect(parseKeyValues("01=70,5\n02: 55\n\nkaputt")).toEqual({ values: { "01": "70.5", "02": "55" }, invalid: ["kaputt"] });
  });
});

describe("extras state", () => {
  it("builds the payload and flags problems", () => {
    const state: ExtrasState = {
      bankAccounts: [{ kind: "hoa", iban: "de02 1203 0000 0000 2020 51", holder: "WEG Test", bank_name: "", is_default: true }],
      keys: [{ code: "FEST", name: "", unit_of_measure: "", kind: "", values: "01=12,5" }],
      debtorAccounts: true,
      linkDocuments: false,
    };
    expect(extrasProblems(state)).toEqual([]);
    expect(extrasPayload(state)).toEqual({
      bank_accounts: [{ kind: "hoa", iban: "DE02120300000000202051", holder: "WEG Test", bank_name: null, is_default: true }],
      allocation_keys: [{ code: "FEST", name: null, unit_of_measure: null, kind: null, values: { "01": "12.5" } }],
      create_debtor_accounts: true,
      link_source_documents: false,
    });
    expect(extrasProblems({ ...state, bankAccounts: [{ ...state.bankAccounts[0]!, iban: "123" }] })).toContain("bank");
    expect(extrasProblems({ ...state, bankAccounts: [{ ...state.bankAccounts[0]!, kind: "deposit" }] })).toContain("deposit");
    expect(extrasProblems({ ...state, keys: [{ ...state.keys[0]!, kind: "consumption" }] })).toContain("keyConsumption");
    expect(extrasProblems({ ...state, keys: [{ ...state.keys[0]!, code: "klein" }] })).toContain("keyCode");
  });
});

describe("OnboardingExtras", () => {
  it("adds a bank account and an allocation key row", async () => {
    let latest: ExtrasState = EMPTY_EXTRAS;
    renderIntl(<Harness onState={(s) => (latest = s)} />);
    await userEvent.click(screen.getByTestId("bank-add"));
    fireEvent.change(screen.getByLabelText("IBAN"), { target: { value: "DE02120300000000202051" } });
    await userEvent.click(screen.getByTestId("key-add"));
    fireEvent.change(screen.getByLabelText("Kürzel"), { target: { value: "sond_a" } });
    expect(latest.bankAccounts[0]?.iban).toBe("DE02120300000000202051");
    expect(latest.keys[0]?.code).toBe("SOND_A");
    expect(screen.getByLabelText(/Quelldokumente mit dem Objekt verknüpfen/)).toBeChecked();
  });
});

const PARTIES: PropertyParty[] = [
  { role: "owner", unit_number: "01", kind: "person", salutation: null, first_name: "Anna", last_name: "Beispiel", company_name: null, start_date: null, payments: [], source: null, confidence: 0.9 },
  { role: "tenant", unit_number: "02", kind: "person", salutation: null, first_name: null, last_name: "Neu", company_name: null, start_date: null, payments: [], source: null, confidence: 0.9 },
];

describe("PersonMatchTable", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the decision per person as table", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        results: [
          { decision: "link", candidates: [{ contact_id: "c1", name: "Anna Beispiel", score: 0.93, reasons: ["Name", "Anschrift"] }] },
          { decision: "none", candidates: [] },
        ],
        link_threshold: "0.85",
        suggest_threshold: "0.55",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<PersonMatchTable parties={PARTIES} />);
    await userEvent.click(screen.getByTestId("person-match-load"));
    await waitFor(() => expect(screen.getByTestId("person-match-table")).toBeInTheDocument());
    expect(screen.getByTestId("person-match-row-0")).toHaveTextContent("Wird verknüpft");
    expect(screen.getByTestId("person-match-row-0")).toHaveTextContent("Anna Beispiel (93 %)");
    expect(screen.getByTestId("person-match-row-1")).toHaveTextContent("Neuer Kontakt");
    expect(screen.getByTestId("person-match-row-1")).toHaveTextContent("kein Treffer");
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/bff/onboarding/person-match-batch");
    expect(JSON.parse(init.body as string)).toEqual({ persons: [{ first_name: "Anna", last_name: "Beispiel" }, { last_name: "Neu" }] });
  });

  it("shows an error and renders nothing without parties", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Fehler", detail: "Nicht erlaubt" }, 403)));
    const { container, unmount } = renderIntl(<PersonMatchTable parties={[]} />);
    expect(container).toBeEmptyDOMElement();
    unmount();
    renderIntl(<PersonMatchTable parties={PARTIES} />);
    await userEvent.click(screen.getByTestId("person-match-load"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

describe("entity decisions (R03-02)", () => {
  afterEach(() => vi.unstubAllGlobals());
  const decisions = entityDecisions({
    entity_decisions: [{ kind: "bank_account", index: 0, holder: "Eigner", account_kind: "rent", candidates: [{ id: "e1", name: "Anna", kind: "rental_owner" }, { id: "e2", name: "Bernd", kind: "rental_owner" }] }],
  });
  const accounts = [{ kind: "rent", iban: "de02 1203 0000 0000 2020 51", holder: "Eigner", bank_name: "", is_default: false }];

  it("builds the request with the chosen entity per account", () => {
    expect(entityDecisions(undefined)).toEqual([]);
    expect(resolvePayload(decisions, accounts, { "0": "e2" }, [], "2020-01-01")).toEqual({
      bank_accounts: [{ kind: "rent", iban: "DE02120300000000202051", holder: "Eigner", bank_name: null, is_default: false, legal_entity_id: "e2" }],
      resolved_indexes: [0],
      debtor_legal_entity_ids: [],
      as_of: "2020-01-01",
    });
  });

  it("enables the button only after a choice and posts the follow-up call", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ created_bank_accounts: 1, debtor_entities: 0 }));
    vi.stubGlobal("fetch", fetchMock);
    const done = vi.fn();
    renderIntl(<EntityDecisions runId="r1" decisions={decisions} accounts={accounts} asOf="2020-01-01" onResolved={done} />);
    const button = screen.getByTestId("entity-apply");
    expect(button).toBeDisabled();
    await userEvent.selectOptions(screen.getByRole("combobox"), "e1");
    expect(button).toBeEnabled();
    await userEvent.click(button);
    await waitFor(() => expect(done).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/bff/ai/import-runs/r1/resolve-entities");
  });
});
