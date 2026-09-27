import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { type Assignment } from "@/lib/metering";
import { jsonResponse, renderIntl } from "@/test/intl";

import { AssignmentsTable } from "./AssignmentsTable";

const A1 = "aaaaaaaa-1111-4111-8111-111111111111";
const A2 = "aaaaaaaa-2222-4222-8222-222222222222";

function assignment(id: string, over: Partial<Assignment> = {}): Assignment {
  return {
    id,
    connection_id: "cccccccc-1111-4111-8111-111111111111",
    connection_name: "Techem Hauptkonto",
    provider_code: "techem",
    environment: "test",
    property_id: "pppppppp-1111-4111-8111-111111111111",
    property_number: "007",
    property_name: "Musterstraße 1",
    property_address: "Musterstraße 1, 40721 Hilden",
    external_billing_unit_id: "eeeeeeee-1111-4111-8111-111111111111",
    external_number: "0004711",
    external_name: null,
    expected_unit_count: 12,
    service_scope: "heating",
    valid_from: "2026-01-01",
    valid_to: null,
    status: "proposed",
    origin: "manual",
    is_primary: true,
    confirmed_at: null,
    verification_basis: null,
    remote_confirmed: false,
    remote_confirmed_at: null,
    group_id: null,
    unit_scope: [],
    assigned_unit_count: 10,
    conflict_reason: null,
    error_hint: null,
    last_success_at: null,
    note: null,
    version: 3,
    ...over,
  };
}

describe("AssignmentsTable", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists assignments with identifiers as text, paginates by X-Total-Count and previews the bulk release", async () => {
    const rows = [assignment(A1), assignment(A2, { property_number: "008", status: "conflict", conflict_reason: "Überschneidung Heizung 2026" })];
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/metering/assignments?")) return jsonResponse(rows, 200, { "x-total-count": "60" });
      if (url.endsWith(`/metering/assignments/${A1}`) && init?.method === "PATCH") return jsonResponse({ ...rows[0], status: "confirmed" });
      return jsonResponse({ detail: "unexpected" }, 500);
    });
    renderIntl(<AssignmentsTable connections={[]} canUpdate pageSize={25} />);
    const row1 = await screen.findByTestId(`assignment-${A1}`);
    expect(within(row1).getByText("007")).toBeInTheDocument();
    expect(within(row1).getByText("0004711")).toBeInTheDocument();
    expect(within(row1).getByText("10/12")).toBeInTheDocument();
    expect(within(row1).getByText("vorgeschlagen")).toBeInTheDocument();
    expect(screen.getByText("Überschneidung Heizung 2026")).toBeInTheDocument();
    expect(screen.getByText("60 Zuordnungen")).toBeInTheDocument();
    expect(screen.getByText("Seite 1 von 3")).toBeInTheDocument();
    const listUrl = String(fetchMock.mock.calls[0]?.[0]);
    expect(listUrl).toContain("page=1");
    expect(listUrl).toContain("page_size=25");

    const user = userEvent.setup();
    const boxes = screen.getAllByRole("checkbox", { name: "Auswählen" });
    await user.click(boxes[0] as HTMLElement);
    await user.click(boxes[1] as HTMLElement);
    await user.click(screen.getByTestId("release-preview-button"));
    const preview = screen.getByTestId("release-preview");
    expect(within(preview).getByText("wird bestätigt")).toBeInTheDocument();
    expect(within(preview).getByText("übersprungen (Konflikt)")).toBeInTheDocument();
    await user.click(screen.getByTestId("release-apply"));
    await waitFor(() => expect(screen.getByTestId("release-report")).toHaveTextContent("Objekt 007: bestätigt."));
    const patch = fetchMock.mock.calls.find((c) => c[1]?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body))).toMatchObject({ version: 3, status: "confirmed" });
    expect(fetchMock.mock.calls.filter((c) => c[1]?.method === "PATCH")).toHaveLength(1);
  });

  it("passes search and filters to the server", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([], 200, { "x-total-count": "0" }));
    renderIntl(<AssignmentsTable connections={[]} canUpdate={false} />);
    await screen.findByText("Keine Zuordnungen gefunden.");
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Prüfstatus"), "conflict");
    await user.type(screen.getByLabelText("Suche (Objekt, externe Nummer)"), "0047");
    await user.click(screen.getByRole("button", { name: "Suchen" }));
    await waitFor(() => {
      const last = String(fetchMock.mock.calls.at(-1)?.[0]);
      expect(last).toContain("status=conflict");
      expect(last).toContain("search=0047");
    });
    expect(screen.queryByTestId("release-preview-button")).not.toBeInTheDocument();
  });
});
