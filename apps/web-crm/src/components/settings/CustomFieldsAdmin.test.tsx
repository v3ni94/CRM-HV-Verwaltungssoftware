import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CustomFieldsAdmin, type CustomField } from "./CustomFieldsAdmin";

const TYPES = [
  { code: "string", label: "Zeichenkette" },
  { code: "integer", label: "Ganzzahl" },
  { code: "choice", label: "Einzelauswahl" },
];
const FIELD: CustomField = {
  id: "11111111-1111-4111-8111-111111111111",
  entity_type: "property",
  key: "baujahr",
  label: "Baujahr",
  field_type: "integer",
  required: false,
  group: "Gebäudedaten",
  valid_for_management_types: ["hoa"],
  valid_for_contract_kinds: [],
  uniqueness: "none",
  visible_in_main: true,
  min_value: "1800.00000000",
  max_value: null,
  default_value: null,
  options: [],
  description: null,
  sort_order: 0,
};

function mockFetch(created: Partial<CustomField> = {}) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/bff/custom-fields") && method === "GET")
        return jsonResponse([FIELD, { ...FIELD, ...created }]);
      if (url.endsWith("/api/bff/custom-fields") && method === "POST")
        return jsonResponse(
          { ...FIELD, ...JSON.parse(String(init?.body)), id: "2" },
          201,
        );
      if (method === "PATCH")
        return jsonResponse({ ...FIELD, ...JSON.parse(String(init?.body)) });
      if (method === "DELETE") return new Response(null, { status: 204 });
      return jsonResponse({ title: "unerwartet" }, 500);
    });
}

describe("CustomFieldsAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists fields per entity and creates a choice field with options", async () => {
    const fetchMock = mockFetch({
      id: "2",
      key: "lage",
      label: "Lage",
      field_type: "choice",
    });
    renderIntl(
      <CustomFieldsAdmin fields={[FIELD]} fieldTypes={TYPES} canManage />,
    );
    const table = screen.getByTestId("custom-fields-property");
    expect(within(table).getByText("Baujahr")).toBeInTheDocument();
    expect(within(table).getByText("Ganzzahl")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Interner Name"), "lage");
    await user.type(screen.getByLabelText("Bezeichnung"), "Lage");
    await user.selectOptions(screen.getByLabelText("Feldtyp"), "choice");
    await user.click(screen.getByText("Feld anlegen"));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Eine Einzelauswahl benötigt Auswahlwerte.",
    );
    await user.type(screen.getByLabelText("Auswahlwerte"), "Stadt, Land");
    await user.click(screen.getByLabelText("WEG-Verwaltung"));
    await user.click(screen.getByText("Feld anlegen"));
    await waitFor(() =>
      expect(screen.getByText("Gespeichert.")).toBeInTheDocument(),
    );
    const post = fetchMock.mock.calls.find(
      ([, init]) => init?.method === "POST",
    )!;
    const sent = JSON.parse(String(post[1]?.body));
    expect(sent).toMatchObject({
      entity_type: "property",
      key: "lage",
      field_type: "choice",
      label: "Lage",
      options: ["Stadt", "Land"],
      valid_for_management_types: ["hoa"],
      uniqueness: "none",
      min_value: null,
    });
    await waitFor(() =>
      expect(
        within(screen.getByTestId("custom-fields-property")).getByText("Lage"),
      ).toBeInTheDocument(),
    );
  });

  it("edits a field with immutable entity, key and type and sends a PATCH", async () => {
    const fetchMock = mockFetch();
    renderIntl(
      <CustomFieldsAdmin fields={[FIELD]} fieldTypes={TYPES} canManage />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByText("Bearbeiten"));
    expect(screen.getByLabelText("Interner Name")).toBeDisabled();
    expect(screen.getByLabelText("Feldtyp")).toBeDisabled();
    expect(screen.getByLabelText("Entität")).toBeDisabled();
    await user.clear(screen.getByLabelText("Maximum"));
    await user.type(screen.getByLabelText("Maximum"), "2100");
    await user.click(screen.getByText("Speichern"));
    await waitFor(() =>
      expect(screen.getByText("Gespeichert.")).toBeInTheDocument(),
    );
    const patch = fetchMock.mock.calls.find(
      ([, init]) => init?.method === "PATCH",
    )!;
    expect(String(patch[0])).toContain(`/api/bff/custom-fields/${FIELD.id}`);
    const sent = JSON.parse(String(patch[1]?.body));
    expect(sent).toMatchObject({
      label: "Baujahr",
      max_value: "2100",
      min_value: "1800.00000000",
      group: "Gebäudedaten",
    });
    expect(sent.key).toBeUndefined();
  });

  it("is read only without the settings permission", () => {
    mockFetch();
    renderIntl(
      <CustomFieldsAdmin
        fields={[FIELD]}
        fieldTypes={TYPES}
        canManage={false}
      />,
    );
    expect(screen.queryByText("Bearbeiten")).not.toBeInTheDocument();
    expect(screen.queryByText("Feld anlegen")).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Die Pflege erfordert das Recht Mandanteneinstellungen ändern.",
      ),
    ).toBeInTheDocument();
  });
});
