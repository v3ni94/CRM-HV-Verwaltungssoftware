import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ContractCustomFieldsForm } from "./ContractCustomFieldsForm";

describe("ContractCustomFieldsForm (GAI-415)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("patches changed, new and emptied values (null removes)", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: "01920000-0000-7000-8000-0000000a1701" }));
    renderIntl(<ContractCustomFieldsForm contractId="01920000-0000-7000-8000-0000000a1701" initial={{ stellplatz: "12", alt: "x" }} canEdit />);
    const stell = screen.getByLabelText("Wert stellplatz");
    await userEvent.clear(stell);
    await userEvent.type(stell, "14");
    await userEvent.clear(screen.getByLabelText("Wert alt"));
    await userEvent.click(screen.getByRole("button", { name: "Feld hinzufügen" }));
    const keys = screen.getAllByLabelText("Feldname");
    await userEvent.type(keys[keys.length - 1]!, "keller");
    await userEvent.type(screen.getAllByLabelText(/^Wert/).pop()!, "K3");
    await userEvent.click(screen.getByRole("button", { name: "Zusatzfelder speichern" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Zusatzfelder gespeichert.");
    const [url, init] = f.mock.calls[0]!;
    expect(url).toBe("/api/bff/contracts/01920000-0000-7000-8000-0000000a1701/custom-fields");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ custom_fields: { stellplatz: "14", alt: null, keller: "K3" } });
  });

  it("is read only without the right and shows errors", async () => {
    renderIntl(<ContractCustomFieldsForm contractId="01920000-0000-7000-8000-0000000a1701" initial={{ a: "1" }} canEdit={false} />);
    expect(screen.queryByRole("button", { name: "Zusatzfelder speichern" })).toBeNull();
    expect(screen.getByLabelText("Wert a")).toBeDisabled();
  });
});
