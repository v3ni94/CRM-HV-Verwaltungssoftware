import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { FlowImport } from "./FlowImport";

const RUN_ID = "01920000-0000-7000-8000-0000000000cc";
const UNIT_ID = "01920000-0000-7000-8000-0000000000dd";
const PROPERTY_ID = "01920000-0000-7000-8000-0000000000ee";

const previewRun = {
  id: RUN_ID,
  filename: "flow_export.sql",
  status: "previewed",
  row_count: 1,
  created_count: 0,
  skipped_count: 0,
  applied_at: null,
  rows: [
    {
      index: 0,
      external_uuid: "aaaaaaaa-0000-0000-0000-000000000001",
      external_ref: "MF-2026-0001",
      title: "Helle Wohnung",
      kind: "rental",
      object_type: "wohnung",
      status: "active",
      listing_fields: { price: "700.00" },
      match: {
        unit_id: UNIT_ID,
        property_id: PROPERTY_ID,
        unit_number: "01",
        property_number: "042",
        basis: "object_number",
      },
      problems: [],
    },
  ],
};

const applyResult = {
  ...previewRun,
  status: "applied",
  created_count: 1,
  skipped_count: 0,
  rows: [{ ...previewRun.rows[0], applied: true, outcome: "created", listing_id: "listing-1" }],
};

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("confirm", vi.fn(() => true));
});
afterEach(() => vi.unstubAllGlobals());

function file(name = "flow_export.sql") {
  return new File(["dump"], name, { type: "application/sql" });
}

describe("FlowImport", () => {
  it("uploads a dump and renders the preview table", async () => {
    fetchMock.mockImplementation(async (path: string) => {
      if (path === "/api/bff/letting/flow-import/preview") return jsonResponse(previewRun, 201);
      if (path === "/api/bff/properties") return jsonResponse([{ id: PROPERTY_ID, number: "042", name: "Maklerhaus" }]);
      if (path.startsWith("/api/bff/properties/")) return jsonResponse([{ id: UNIT_ID, number: "01", label: null }]);
      throw new Error(`unexpected fetch: ${path}`);
    });
    renderIntl(<FlowImport />);

    const input = screen.getByLabelText("SQL-Dump");
    await userEvent.upload(input, file());
    await userEvent.click(screen.getByRole("button", { name: "Prüfen" }));

    await waitFor(() => expect(screen.getByTestId("flow-import-preview")).toBeInTheDocument());
    expect(screen.getByText("MF-2026-0001")).toBeInTheDocument();
    expect(screen.getByText("Helle Wohnung")).toBeInTheDocument();
    expect(screen.getByText("700.00")).toBeInTheDocument();

    const [call] = fetchMock.mock.calls.filter(([p]) => p === "/api/bff/letting/flow-import/preview");
    expect(call?.[1].body).toBeInstanceOf(FormData);
  });

  it("sends the chosen action and unit override on apply", async () => {
    fetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
      if (path === "/api/bff/letting/flow-import/preview") return jsonResponse(previewRun, 201);
      if (path === "/api/bff/properties") return jsonResponse([{ id: PROPERTY_ID, number: "042", name: "Maklerhaus" }]);
      if (path.startsWith("/api/bff/properties/")) return jsonResponse([{ id: UNIT_ID, number: "01", label: null }]);
      if (path === `/api/bff/letting/flow-import/${RUN_ID}/apply`) {
        const body = JSON.parse(String(init?.body));
        expect(body).toEqual({ items: [{ index: 0, action: "create", unit_id: UNIT_ID }] });
        return jsonResponse(applyResult);
      }
      throw new Error(`unexpected fetch: ${path}`);
    });
    renderIntl(<FlowImport />);

    await userEvent.upload(screen.getByLabelText("SQL-Dump"), file());
    await userEvent.click(screen.getByRole("button", { name: "Prüfen" }));
    await waitFor(() => expect(screen.getByTestId("flow-import-preview")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Ausgewählte übernehmen" }));

    await waitFor(() => expect(screen.getByTestId("flow-import-result")).toBeInTheDocument());
    expect(screen.getByTestId("flow-import-result")).toHaveTextContent("1 Anzeigen angelegt, 0 übersprungen.");
  });
});
