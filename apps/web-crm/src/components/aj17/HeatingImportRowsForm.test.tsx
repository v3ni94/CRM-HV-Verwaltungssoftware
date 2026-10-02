import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { HeatingImportRowsForm } from "./HeatingImportRowsForm";

describe("HeatingImportRowsForm (GAI-419)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("puts the rows with decimal point amounts as strings", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: "01920000-0000-7000-8000-0000000a1701", rows: [] }));
    const onSaved = vi.fn();
    renderIntl(<HeatingImportRowsForm importId="01920000-0000-7000-8000-0000000a1701" editable onSaved={onSaved} />);
    await userEvent.type(screen.getByLabelText("Nutzernummer 1"), "N-7");
    await userEvent.type(screen.getByLabelText("Heizung Grundkosten 1"), "100,5");
    await userEvent.type(screen.getByLabelText("Heizung Verbrauch 1"), "200");
    await userEvent.type(screen.getByLabelText("Warmwasser Grundkosten 1"), "30.25");
    await userEvent.type(screen.getByLabelText("Warmwasser Verbrauch 1"), "0");
    await userEvent.click(screen.getByRole("button", { name: "Zeilen speichern" }));
    expect(await screen.findByRole("status")).toHaveTextContent("1 Zeilen gespeichert.");
    const [url, init] = f.mock.calls[0]!;
    expect(url).toBe("/api/bff/billing/heating-cost-imports/01920000-0000-7000-8000-0000000a1701/rows");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({
      rows: [{ user_number: "N-7", heating_base: "100.5", heating_consumption: "200", hot_water_base: "30.25", hot_water_consumption: "0" }],
    });
    expect(onSaved).toHaveBeenCalled();
  });

  it("validates amounts locally and is hidden for applied imports", async () => {
    const f = vi.spyOn(globalThis, "fetch");
    const { unmount } = renderIntl(<HeatingImportRowsForm importId="01920000-0000-7000-8000-0000000a1701" editable />);
    await userEvent.type(screen.getByLabelText("Nutzernummer 1"), "N-7");
    await userEvent.type(screen.getByLabelText("Heizung Grundkosten 1"), "1,234");
    await userEvent.click(screen.getByRole("button", { name: "Zeilen speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("alle vier Beträge");
    expect(f).not.toHaveBeenCalled();
    unmount();
    const { container } = renderIntl(<HeatingImportRowsForm importId="01920000-0000-7000-8000-0000000a1701" editable={false} />);
    expect(container).toBeEmptyDOMElement();
  });
});
