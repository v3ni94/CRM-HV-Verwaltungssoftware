import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CatalogAdmin, type CatalogEntry } from "./CatalogAdmin";

const SUMMARIES = [
  { catalog: "deposit_kind", entries: 2, active: 2, system: 2 },
  { catalog: "trade", entries: 1, active: 1, system: 1 },
];
const ENTRIES: CatalogEntry[] = [
  {
    id: "11111111-1111-4111-8111-111111111111",
    catalog: "deposit_kind",
    code: "sparbuch",
    label: "Sparbuch",
    sort_order: 0,
    active: true,
    is_system: true,
  },
  {
    id: "22222222-2222-4222-8222-222222222222",
    catalog: "deposit_kind",
    code: "eigene",
    label: "Eigene Art",
    sort_order: 1,
    active: true,
    is_system: false,
  },
];

function mockFetch() {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.includes("/api/bff/catalogs/deposit_kind?") && method === "GET")
        return jsonResponse(ENTRIES);
      if (url.endsWith("/api/bff/catalogs") && method === "GET")
        return jsonResponse(SUMMARIES);
      if (url.endsWith("/api/bff/catalogs/deposit_kind") && method === "POST") {
        return jsonResponse(
          {
            ...JSON.parse(String(init?.body)),
            id: "3",
            catalog: "deposit_kind",
            active: true,
            is_system: false,
          },
          201,
        );
      }
      if (method === "PATCH")
        return jsonResponse({
          ...ENTRIES[0],
          ...JSON.parse(String(init?.body)),
        });
      if (method === "DELETE") return new Response(null, { status: 204 });
      return jsonResponse({ title: "unerwartet" }, 500);
    });
}

describe("CatalogAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists entries, marks system entries and deactivates one via PATCH", async () => {
    const fetchMock = mockFetch();
    renderIntl(<CatalogAdmin catalogs={SUMMARIES} canManage />);
    const table = await screen.findByTestId("catalog-entries");
    expect(within(table).getByText("Sparbuch")).toBeInTheDocument();
    expect(within(table).getAllByText("System")).toHaveLength(1);
    expect(within(table).getByText("Eigen")).toBeInTheDocument();
    // System entry has no delete button, own entry has one.
    expect(within(table).getAllByText("Löschen")).toHaveLength(1);
    await userEvent.setup().click(screen.getByLabelText("Sparbuch aktiv"));
    await waitFor(() =>
      expect(screen.getByText("Gespeichert.")).toBeInTheDocument(),
    );
    const patch = fetchMock.mock.calls.find(
      ([, init]) => init?.method === "PATCH",
    )!;
    expect(String(patch[0])).toContain(
      "/api/bff/catalogs/deposit_kind/11111111-1111-4111-8111-111111111111",
    );
    expect(JSON.parse(String(patch[1]?.body))).toEqual({ active: false });
  });

  it("validates the code and adds an own entry via POST", async () => {
    const fetchMock = mockFetch();
    renderIntl(<CatalogAdmin catalogs={SUMMARIES} canManage />);
    await screen.findByTestId("catalog-entries");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Code"), "Bürgschaft");
    await user.type(screen.getByLabelText("Bezeichnung"), "Bürgschaft Bank");
    await user.click(screen.getByText("Hinzufügen"));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Der Code darf nur Kleinbuchstaben",
    );
    await user.clear(screen.getByLabelText("Code"));
    await user.type(screen.getByLabelText("Code"), "buergschaft_bank");
    await user.click(screen.getByText("Hinzufügen"));
    await waitFor(() =>
      expect(screen.getByText("Gespeichert.")).toBeInTheDocument(),
    );
    const post = fetchMock.mock.calls.find(
      ([, init]) => init?.method === "POST",
    )!;
    expect(JSON.parse(String(post[1]?.body))).toEqual({
      code: "buergschaft_bank",
      label: "Bürgschaft Bank",
      sort_order: 2,
    });
  });

  it("is read only without the settings permission", async () => {
    mockFetch();
    renderIntl(<CatalogAdmin catalogs={SUMMARIES} canManage={false} />);
    const table = await screen.findByTestId("catalog-entries");
    expect(screen.getByLabelText("Sparbuch aktiv")).toBeDisabled();
    expect(within(table).queryByText("Löschen")).not.toBeInTheDocument();
    expect(screen.queryByText("Hinzufügen")).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Die Pflege erfordert das Recht Mandanteneinstellungen ändern.",
      ),
    ).toBeInTheDocument();
  });
});
