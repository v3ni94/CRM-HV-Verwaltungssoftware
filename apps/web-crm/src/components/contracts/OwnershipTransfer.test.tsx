import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { OwnershipTransfer, type TransferContract, type TransferPreview } from "./OwnershipTransfer";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

const CID = "0192abcd-0000-7000-8000-000000000701";
const NEW_ID = "0192abcd-0000-7000-8000-000000000702";
const CONTRACT: TransferContract = {
  id: CID,
  kind: "ownership",
  number: "V-2026-000012",
  party_id: "p1",
  party_name: "Verkäufer Test",
  unit_id: "0192abcd-0000-7000-8000-000000000007",
  start_date: "2020-01-01",
  end_date: null,
  sev_enabled: true,
};
const PREVIEW: TransferPreview = {
  contract_id: CID,
  party_id: "p1",
  party_name: "Verkäufer Test",
  title_transfer_date: "2026-04-01",
  old_end_date: "2026-03-31",
  new_start_date: "2026-04-01",
  payments: [
    { id: "pay1", payment_type_code: "hoa_fee", gross: "300.00", valid_from: "2025-01-01", valid_to: null },
    { id: "pay2", payment_type_code: "reserve", gross: "50.00", valid_from: "2025-01-01", valid_to: null },
  ],
  schedules: [{ id: "s1", interval: "monthly", due_day_rule: "day", due_day: 3, valid_from: "2020-01-01", valid_to: null }],
  allocation_values: [{ id: "v1", allocation_key_code: "PERSONS", allocation_key_name: "Personen", unit_of_measure: "Pers.", value: "2.00000000", valid_from: "2020-01-01" }],
  statement_split: "not_implemented",
};

function mockFetch(overrides: Partial<Record<string, (init?: RequestInit) => Response>> = {}) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url === `/api/bff/contracts/${CID}` && method === "GET") return (overrides.contract ?? (() => jsonResponse(CONTRACT)))(init);
    if (url.startsWith("/api/bff/contacts?")) return jsonResponse({ items: [{ id: "c9", display_name: "Käufer Neu" }] });
    if (url === "/api/bff/contacts" && method === "POST") return jsonResponse({ id: "c10", display_name: "Erika Erwerb" }, 201);
    if (url.startsWith(`/api/bff/contracts/${CID}/ownership-transfer/preview`)) return jsonResponse(PREVIEW);
    if (url === `/api/bff/contracts/${CID}/ownership-transfer` && method === "POST") return (overrides.transfer ?? (() => jsonResponse({ id: NEW_ID }, 201)))(init);
    return jsonResponse({ title: "unexpected" }, 500);
  });
}

describe("OwnershipTransfer", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    push.mockReset();
    refresh.mockReset();
  });

  it("renders nothing without contracts:update", () => {
    renderIntl(<OwnershipTransfer contractId={CID} sevAllowed canUpdate={false} />);
    expect(screen.queryByText("Eigentümerwechsel")).toBeNull();
  });

  it("searches the acquirer, validates the date, shows the preview with the W07 hint and posts the transfer", async () => {
    const fetchMock = mockFetch();
    const user = userEvent.setup({ delay: null });
    renderIntl(<OwnershipTransfer contractId={CID} sevAllowed canUpdate />);
    await user.click(screen.getByRole("button", { name: "Eigentümerwechsel erfassen" }));
    const dialog = await screen.findByTestId("ownership-transfer-dialog");
    expect(within(dialog).getByText("Eigentümerwechsel für Vertrag V-2026-000012 (Verkäufer Test)")).toBeInTheDocument();
    const next = within(dialog).getByRole("button", { name: "Vorschau" });
    expect(next).toBeDisabled();

    await user.type(within(dialog).getByLabelText("Erwerber"), "Käu");
    await user.click(within(dialog).getByRole("button", { name: "Suchen" }));
    await user.click(await within(dialog).findByRole("button", { name: "Käufer Neu" }));
    expect(within(dialog).getByTestId("acquirer-picked")).toHaveTextContent("Käufer Neu");

    await user.type(within(dialog).getByLabelText("Eigentumsübergang (Grundbuch)"), "2019-06-01");
    expect(within(dialog).getByText("Der Eigentumsübergang muss nach dem Beginn des bisherigen Eigentums (01.01.2020) liegen.")).toBeInTheDocument();
    expect(next).toBeDisabled();
    await user.clear(within(dialog).getByLabelText("Eigentumsübergang (Grundbuch)"));
    await user.type(within(dialog).getByLabelText("Eigentumsübergang (Grundbuch)"), "2026-04-01");
    await user.type(within(dialog).getByLabelText("Nutzen und Lasten (optional)"), "2026-03-15");
    await user.selectOptions(within(dialog).getByLabelText("Erwerbsart"), "purchase");
    // SEV is preselected from the current ownership in a WEG mit SEV.
    expect(within(dialog).getByLabelText("Sondereigentumsverwaltung (SEV) für den Erwerber aktiv")).toBeChecked();
    await user.type(within(dialog).getByLabelText("Notiz zum neuen Vertrag"), "Kaufvertrag UR 12/2026");
    expect(next).toBeEnabled();
    await user.click(next);

    const preview = await within(dialog).findByTestId("transfer-preview");
    expect(preview).toHaveTextContent("Das Eigentum von Verkäufer Test endet am 31.03.2026.");
    expect(preview).toHaveTextContent("Das Eigentum von Käufer Neu beginnt am 01.04.2026.");
    const amounts = within(dialog).getByTestId("transfer-amounts");
    expect(amounts).toHaveTextContent("Hausgeld: 300,00 EUR");
    expect(amounts).toHaveTextContent("Erhaltungsrücklage: 50,00 EUR");
    expect(amounts).toHaveTextContent("Zahlungsplan: monatlich");
    expect(amounts).toHaveTextContent("Personen: 2,00 Pers.");
    expect(within(dialog).getByTestId("transfer-w07")).toHaveTextContent("Regel W07 ist fachlich nicht freigegeben, Freigabepunkt P01 ist offen");

    await user.click(within(dialog).getByRole("button", { name: "Eigentümerwechsel erfassen" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(String(push.mock.calls[0]?.[0])).toContain(`/vertraege/${NEW_ID}?hinweis=`);
    const call = fetchMock.mock.calls.find(([input, init]) => String(input).endsWith("/ownership-transfer") && init?.method === "POST");
    expect(call).toBeDefined();
    expect(JSON.parse(String((call![1] as RequestInit).body))).toEqual({
      new_contact_id: "c9",
      title_transfer_date: "2026-04-01",
      benefit_burden_date: "2026-03-15",
      acquisition_kind: "purchase",
      special_succession_liability: false,
      sev_enabled: true,
      carry_over_amounts: true,
      notes: "Kaufvertrag UR 12/2026",
    });
  });

  it("creates the acquirer as a new contact and can switch the carry over off", async () => {
    const fetchMock = mockFetch();
    const user = userEvent.setup({ delay: null });
    renderIntl(<OwnershipTransfer contractId={CID} sevAllowed={false} canUpdate />);
    await user.click(screen.getByRole("button", { name: "Eigentümerwechsel erfassen" }));
    const dialog = await screen.findByTestId("ownership-transfer-dialog");
    expect(within(dialog).queryByLabelText("Sondereigentumsverwaltung (SEV) für den Erwerber aktiv")).toBeNull();
    await user.click(within(dialog).getByRole("button", { name: "Neuen Kontakt anlegen" }));
    const create = within(dialog).getByTestId("acquirer-create");
    expect(within(create).getByRole("button", { name: "Kontakt anlegen" })).toBeDisabled();
    await user.type(within(create).getByLabelText("Vorname"), "Erika");
    await user.type(within(create).getByLabelText("Nachname"), "Erwerb");
    await user.click(within(create).getByRole("button", { name: "Kontakt anlegen" }));
    expect(await within(dialog).findByTestId("acquirer-picked")).toHaveTextContent("Erika Erwerb");
    const created = fetchMock.mock.calls.find(([input, init]) => String(input) === "/api/bff/contacts" && init?.method === "POST");
    expect(JSON.parse(String((created![1] as RequestInit).body))).toEqual({ kind: "person", first_name: "Erika", last_name: "Erwerb" });

    await user.type(within(dialog).getByLabelText("Eigentumsübergang (Grundbuch)"), "2026-04-01");
    await user.click(within(dialog).getByLabelText("Sollbeträge, Zahlungsplan und Umlagewerte ab dem Eigentumsübergang übernehmen"));
    await user.click(within(dialog).getByRole("button", { name: "Vorschau" }));
    expect(await within(dialog).findByText("Nicht übernommen (am neuen Vertrag zu erfassen):")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Eigentümerwechsel erfassen" }));
    await waitFor(() => expect(push).toHaveBeenCalled());
    const call = fetchMock.mock.calls.find(([input, init]) => String(input).endsWith("/ownership-transfer") && init?.method === "POST");
    const body = JSON.parse(String((call![1] as RequestInit).body));
    expect(body.new_contact_id).toBe("c10");
    expect(body.carry_over_amounts).toBe(false);
    expect(body.sev_enabled).toBe(false);
  });

  it("shows the API error and returns to the form", async () => {
    mockFetch({ transfer: () => jsonResponse({ title: "Eigentümerwechsel nicht möglich", detail: "Das Eigentumsverhältnis ist bereits beendet.", code: "MHVP-CONTR-0001" }, 422) });
    const user = userEvent.setup({ delay: null });
    renderIntl(<OwnershipTransfer contractId={CID} sevAllowed canUpdate />);
    await user.click(screen.getByRole("button", { name: "Eigentümerwechsel erfassen" }));
    const dialog = await screen.findByTestId("ownership-transfer-dialog");
    await user.type(within(dialog).getByLabelText("Erwerber"), "Käu");
    await user.click(within(dialog).getByRole("button", { name: "Suchen" }));
    await user.click(await within(dialog).findByRole("button", { name: "Käufer Neu" }));
    await user.type(within(dialog).getByLabelText("Eigentumsübergang (Grundbuch)"), "2026-04-01");
    await user.click(within(dialog).getByRole("button", { name: "Vorschau" }));
    await user.click(await within(dialog).findByRole("button", { name: "Eigentümerwechsel erfassen" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Das Eigentumsverhältnis ist bereits beendet.");
    expect(within(dialog).getByRole("button", { name: "Vorschau" })).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("explains an ended ownership instead of a form", async () => {
    mockFetch({ contract: () => jsonResponse({ ...CONTRACT, end_date: "2026-03-31" }) });
    const user = userEvent.setup({ delay: null });
    renderIntl(<OwnershipTransfer contractId={CID} sevAllowed canUpdate />);
    await user.click(screen.getByRole("button", { name: "Eigentümerwechsel erfassen" }));
    expect(await screen.findByText("Das Eigentum ist bereits zum 31.03.2026 beendet.")).toBeInTheDocument();
    expect(screen.queryByTestId("ownership-transfer-dialog")).toBeNull();
  });
});
