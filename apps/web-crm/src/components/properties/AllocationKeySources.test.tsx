import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AllocationKeySources, canConfirm, type KeySource } from "./AllocationKeySources";

const PID = "0192abcd-0000-7000-8000-000000000041";
const KID = "0192abcd-0000-7000-8000-000000000042";
const KEY: KeySource = {
  id: KID,
  code: "WFL",
  name: "Wohnfläche",
  is_template_derived: true,
  source_kind: null,
  source_reference: null,
  source_document_id: null,
  source_valid_from: null,
  confirmed_at: null,
};

describe("AllocationKeySources (GAM-108)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("needs kind, start and reference before a confirmation", () => {
    expect(canConfirm(KEY)).toBe(false);
    expect(canConfirm({ ...KEY, source_kind: "resolution", source_valid_from: "2020-01-01" })).toBe(false);
    expect(canConfirm({ ...KEY, source_kind: "resolution", source_valid_from: "2020-01-01", source_reference: "TOP 4" })).toBe(true);
  });

  it("shows the template origin, saves the source and confirms", async () => {
    let state: KeySource = KEY;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "PATCH") state = { ...state, ...JSON.parse(String(init.body)) };
      if (url.endsWith("/confirmation")) state = { ...state, confirmed_at: "2026-10-03T08:00:00Z" };
      return jsonResponse(init?.method ? state : [state]);
    });
    renderIntl(<AllocationKeySources propertyId={PID} canEdit />);
    expect(await screen.findByText("aus Muster übernommen")).toBeInTheDocument();
    expect(screen.getByText("WFL bestätigen")).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Quelle WFL"), "declaration_of_division");
    await userEvent.type(screen.getByLabelText("Fundstelle WFL"), "TE § 7");
    await userEvent.type(screen.getByLabelText("Geltungsbeginn WFL"), "2020-01-01");
    await userEvent.click(screen.getByText("Quelle speichern"));
    await waitFor(() => expect(screen.getByText("WFL bestätigen")).toBeEnabled());
    const patch = fetchMock.mock.calls.find(([, i]) => i?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body))).toEqual({
      source_kind: "declaration_of_division",
      source_reference: "TE § 7",
      source_valid_from: "2020-01-01",
    });
    await userEvent.click(screen.getByText("WFL bestätigen"));
    expect(await screen.findByText(/bestätigt am/)).toBeInTheDocument();
    const put = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/confirmation"));
    expect(String(put?.[0])).toBe(`/api/bff/properties/${PID}/allocation-keys/${KID}/confirmation`);
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({ confirmed: true });
    expect(screen.getByText("Bestätigung aufheben")).toBeInTheDocument();
  });

  it("is read only without edit right", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([KEY]));
    renderIntl(<AllocationKeySources propertyId={PID} canEdit={false} />);
    expect(await screen.findByLabelText("Quelle WFL")).toBeDisabled();
    expect(screen.queryByText("WFL bestätigen")).not.toBeInTheDocument();
  });
});
