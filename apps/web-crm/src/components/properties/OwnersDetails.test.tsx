import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { OwnersDetails } from "./OwnersDetails";
import type { CurrentOwner } from "./PropertyOwnerPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const PID = "0192abcd-0000-7000-8000-000000000341";
const OWNER: CurrentOwner = {
  id: "0192abcd-0000-7000-8000-000000000342",
  party_id: "pa1",
  party_name: "Muster, Max",
  contact_id: "0192abcd-0000-7000-8000-000000000343",
  contact_name: "Muster, Max",
  share_percent: null,
  valid_from: "2026-01-01",
  valid_to: null,
  clearing_account_id: "0192abcd-0000-7000-8000-000000000344",
  power_of_attorney_document_id: null,
  tax_advisor_contact_id: null,
};
const ACCOUNT_OTHER = { id: "0192abcd-0000-7000-8000-000000000345", label: "1600 Sonstiges" };
const ACCOUNTS = [{ id: "0192abcd-0000-7000-8000-000000000344", label: "1590 Verrechnung Eigentümer" }, ACCOUNT_OTHER];
const DOCUMENT = { id: "0192abcd-0000-7000-8000-000000000346", label: "Vollmacht Muster.pdf" };
const DOCUMENTS = [DOCUMENT];

type Call = { url: string; method: string; body: unknown };

function mockFetch(calls: Call[]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (url.startsWith("/api/bff/contacts?q=")) return jsonResponse({ items: [{ id: "0192abcd-0000-7000-8000-000000000347", display_name: "Steuerkanzlei Nord" }] });
    return jsonResponse({ id: OWNER.id });
  });
}

describe("OwnersDetails", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("renders nothing without write permission or owners", () => {
    const { container } = renderIntl(<OwnersDetails propertyId={PID} owners={[OWNER]} accounts={ACCOUNTS} documents={DOCUMENTS} canEdit={false} />);
    expect(container).toBeEmptyDOMElement();
    const empty = renderIntl(<OwnersDetails propertyId={PID} owners={[]} accounts={ACCOUNTS} documents={DOCUMENTS} canEdit />);
    expect(empty.container).toBeEmptyDOMElement();
  });

  it("saves clearing account, power of attorney and tax advisor via PUT", async () => {
    const calls: Call[] = [];
    mockFetch(calls);
    const user = userEvent.setup();
    renderIntl(<OwnersDetails propertyId={PID} owners={[OWNER]} accounts={ACCOUNTS} documents={DOCUMENTS} canEdit />);
    await user.click(screen.getByRole("button", { name: "Details für Muster, Max bearbeiten" }));
    expect(screen.getByLabelText("Verrechnungskonto")).toHaveValue(OWNER.clearing_account_id);
    await user.selectOptions(screen.getByLabelText("Verrechnungskonto"), ACCOUNT_OTHER.id);
    await user.selectOptions(screen.getByLabelText("Verwaltervollmacht"), DOCUMENT.id);
    await user.type(screen.getByTestId("owner-tax-advisor"), "Steuer");
    await user.click(await screen.findByRole("button", { name: "Steuerkanzlei Nord" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const put = calls.find((c) => c.method === "PUT");
    expect(put?.url).toBe(`/api/bff/properties/${PID}/owners/${OWNER.id}/details`);
    expect(put?.body).toEqual({
      clearing_account_id: ACCOUNT_OTHER.id,
      power_of_attorney_document_id: DOCUMENT.id,
      tax_advisor_contact_id: "0192abcd-0000-7000-8000-000000000347",
    });
  });

  it("clears references with null and shows API errors", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Eingaben ungültig", detail: "Das Verrechnungskonto gehört nicht zum Objekt.", status: 422 }, 422));
    const user = userEvent.setup();
    renderIntl(<OwnersDetails propertyId={PID} owners={[OWNER]} accounts={ACCOUNTS} documents={DOCUMENTS} canEdit />);
    await user.click(screen.getByRole("button", { name: "Details für Muster, Max bearbeiten" }));
    await user.selectOptions(screen.getByLabelText("Verrechnungskonto"), "");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("gehört nicht zum Objekt");
    expect(refresh).not.toHaveBeenCalled();
  });
});
