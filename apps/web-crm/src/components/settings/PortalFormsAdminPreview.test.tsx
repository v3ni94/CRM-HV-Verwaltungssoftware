import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalFormsAdmin, type PortalFormTemplate } from "./PortalFormsAdmin";

const TPL: PortalFormTemplate = {
  id: "01920000-0000-7000-8000-0000000000f1",
  name: "Adressänderung",
  description: null,
  category: "Antrag",
  audience: "all",
  active: true,
  sort_order: 0,
  fields: [{ key: "anschrift", label: "Neue Anschrift", type: "address", required: true, options: null }],
};

describe("PortalFormsAdmin preview and element types (AA14-01)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("opens the preview of a template without a request and offers all 20 types in the builder", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const user = userEvent.setup();
    renderIntl(<PortalFormsAdmin initialTemplates={[TPL]} canManage={false} />);
    expect(fetchMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Vorschau anzeigen" }));
    expect(screen.getByTestId("portal-form-preview")).toBeInTheDocument();
    expect(screen.getByLabelText("Neue Anschrift *")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Vorschau ausblenden" }));
    expect(screen.queryByTestId("portal-form-preview")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("previews the fields of a new template in the editor and checks a sample", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ valid: true, errors: [], rendered: "Formular: Neu" }));
    const user = userEvent.setup();
    renderIntl(<PortalFormsAdmin initialTemplates={[]} canManage />);
    await user.click(screen.getByRole("button", { name: "Neues Formular" }));
    expect(screen.getByRole("combobox", { name: "Feldtyp" }).querySelectorAll("option")).toHaveLength(20);
    await user.type(screen.getByLabelText("Neues Feld"), "Standort");
    await user.selectOptions(screen.getByLabelText("Feldtyp"), "location");
    await user.click(screen.getByRole("button", { name: "Hinzufügen" }));
    await user.click(screen.getByRole("button", { name: "Vorschau anzeigen" }));
    await user.type(screen.getByLabelText("Standort"), "Keller");
    await user.click(screen.getByRole("button", { name: "Beispielwerte prüfen" }));
    expect(await screen.findByText("Die Beispielwerte sind gültig.")).toBeInTheDocument();
    const sent = JSON.parse(String(fetchMock.mock.calls.at(0)?.[1]?.body));
    expect(sent.values).toEqual({ standort: "Keller" });
  });
});
