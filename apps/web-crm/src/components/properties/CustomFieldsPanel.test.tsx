import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CustomFieldsPanel, type CustomFieldDefinition } from "./CustomFieldsPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const PID = "0192abcd-0000-7000-8000-000000000331";
const def = (over: Partial<CustomFieldDefinition>): CustomFieldDefinition => ({
  id: over.key ?? "x",
  entity_type: "property",
  key: "k",
  label: "K",
  field_type: "string",
  required: false,
  group: null,
  valid_for_management_types: [],
  options: [],
  description: null,
  sort_order: 0,
  ...over,
});
const DEFINITIONS = [
  def({ key: "akte", label: "Objektakte Nr.", field_type: "string" }),
  def({ key: "stellplaetze", label: "Stellplätze", field_type: "integer" }),
  def({ key: "aufzug", label: "Aufzug", field_type: "bool" }),
  def({ key: "heizung", label: "Heizungsart", field_type: "choice", options: ["Gas", "Fernwärme"] }),
  def({ key: "weg_only", label: "Nur WEG", field_type: "string", valid_for_management_types: ["hoa"] }),
  def({ key: "vertrag", label: "Vertrag", field_type: "document_ref" }),
];

type Call = { url: string; method: string; body: unknown; headers: Headers };

function mockFetch(calls: Call[], patchStatus = 200) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null, headers: new Headers(init?.headers) });
    if (url.startsWith("/api/bff/custom-fields?")) return jsonResponse(DEFINITIONS);
    if (method === "POST") return jsonResponse(def({ key: "neu", label: "Neu" }), 201);
    if (patchStatus === 412) return jsonResponse({ title: "Versionskonflikt", status: 412 }, 412);
    return jsonResponse({ id: PID, version: 4 });
  });
}

describe("CustomFieldsPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("shows the defined fields of the management type with formatted values", async () => {
    mockFetch([]);
    renderIntl(
      <CustomFieldsPanel propertyId={PID} version={3} values={{ akte: "OA-1", stellplaetze: 4, aufzug: true, heizung: "Gas" }} managementType="rental" canEdit={false} canDefine={false} />,
    );
    expect(await screen.findByText("Objektakte Nr.")).toBeInTheDocument();
    expect(screen.getByText("OA-1")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("Ja")).toBeInTheDocument();
    expect(screen.getByText("Gas")).toBeInTheDocument();
    expect(screen.queryByText("Nur WEG")).toBeNull();
    expect(screen.getByText("Vertrag")).toBeInTheDocument();
    expect(screen.queryByText("Werte bearbeiten")).toBeNull();
    expect(screen.queryByText("Neues Zusatzfeld")).toBeNull();
  });

  it("saves typed values with If-Match and keeps API only values", async () => {
    const calls: Call[] = [];
    mockFetch(calls);
    const user = userEvent.setup();
    renderIntl(
      <CustomFieldsPanel propertyId={PID} version={3} values={{ akte: "OA-1", vertrag: "0192abcd-0000-7000-8000-000000000339" }} managementType="rental" canEdit canDefine={false} />,
    );
    await user.click(await screen.findByRole("button", { name: "Werte bearbeiten" }));
    await user.type(screen.getByLabelText("Stellplätze"), "12");
    await user.selectOptions(screen.getByLabelText("Aufzug"), "false");
    await user.selectOptions(screen.getByLabelText("Heizungsart"), "Fernwärme");
    const akte = screen.getByLabelText("Objektakte Nr.");
    await user.clear(akte);
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const patch = calls.find((c) => c.method === "PATCH");
    expect(patch?.url).toBe(`/api/bff/properties/${PID}`);
    expect(patch?.headers.get("if-match")).toBe('"3"');
    expect(patch?.body).toEqual({
      custom_fields: { akte: null, stellplaetze: 12, aufzug: false, heizung: "Fernwärme", vertrag: "0192abcd-0000-7000-8000-000000000339" },
    });
  });

  it("explains a version conflict instead of refreshing", async () => {
    mockFetch([], 412);
    const user = userEvent.setup();
    renderIntl(<CustomFieldsPanel propertyId={PID} version={3} values={{}} managementType="rental" canEdit canDefine={false} />);
    await user.click(await screen.findByRole("button", { name: "Werte bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("zwischenzeitlich geändert");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("defines a new choice field for properties", async () => {
    const calls: Call[] = [];
    mockFetch(calls);
    const user = userEvent.setup();
    renderIntl(<CustomFieldsPanel propertyId={PID} version={3} values={{}} managementType="rental" canEdit canDefine />);
    await user.click(await screen.findByRole("button", { name: "Neues Zusatzfeld" }));
    const create = screen.getByRole("button", { name: "Feld anlegen" });
    await user.type(screen.getByLabelText("Bezeichnung"), "Dachform");
    await user.type(screen.getByLabelText("Schlüssel"), "Dach Form");
    expect(create).toBeDisabled();
    await user.clear(screen.getByLabelText("Schlüssel"));
    await user.type(screen.getByLabelText("Schlüssel"), "dachform");
    await user.selectOptions(screen.getByLabelText("Typ"), "choice");
    expect(create).toBeDisabled();
    await user.type(screen.getByLabelText("Auswahlwerte"), "Satteldach, Flachdach");
    expect(create).toBeEnabled();
    await user.click(create);
    const post = await waitFor(() => {
      const found = calls.find((c) => c.method === "POST");
      expect(found).toBeDefined();
      return found;
    });
    expect(post?.url).toBe("/api/bff/custom-fields");
    expect(post?.body).toEqual({ entity_type: "property", key: "dachform", label: "Dachform", field_type: "choice", options: ["Satteldach", "Flachdach"] });
    // the definitions are reloaded after the creation
    await waitFor(() => expect(calls.filter((c) => c.url.startsWith("/api/bff/custom-fields?")).length).toBe(2));
  });
});
