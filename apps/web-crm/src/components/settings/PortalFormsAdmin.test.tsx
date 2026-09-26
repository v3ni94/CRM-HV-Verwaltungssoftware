import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalFormsAdmin, type PortalFormTemplate } from "./PortalFormsAdmin";

const TPL: PortalFormTemplate = {
  id: "01920000-0000-7000-8000-0000000000f1",
  name: "Antrag Untervermietung",
  description: null,
  category: "Antrag",
  audience: "tenant",
  active: true,
  sort_order: 0,
  fields: [{ key: "anliegen", label: "Anliegen", type: "text", required: true, options: null }],
};

describe("PortalFormsAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates a template with a select field and sends it to the BFF", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
      expect(String(input)).toBe("/api/bff/portal-admin/forms");
      return jsonResponse({ id: TPL.id, active: true, sort_order: 0, description: null, ...body }, 201);
    });
    const user = userEvent.setup();
    renderIntl(<PortalFormsAdmin initialTemplates={[]} canManage />);
    await user.click(screen.getByRole("button", { name: "Neues Formular" }));
    await user.type(screen.getByLabelText("Name"), "Haustierantrag");
    await user.type(screen.getByLabelText("Ticketkategorie"), "Antrag");
    await user.selectOptions(screen.getByLabelText("Zielgruppe"), "tenant");
    await user.type(screen.getByLabelText("Neues Feld"), "Tierart");
    await user.selectOptions(screen.getByLabelText("Feldtyp"), "select");
    await user.type(screen.getByLabelText("Optionen"), "Hund, Katze");
    await user.click(screen.getByRole("button", { name: "Hinzufügen" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByTestId("portal-form-template")).toHaveTextContent("Haustierantrag"));
    const sent = JSON.parse(String(fetchMock.mock.calls[0]![1]?.body)) as { fields: unknown[]; audience: string };
    expect(sent.audience).toBe("tenant");
    expect(sent.fields).toEqual([{ key: "tierart", label: "Tierart", type: "select", required: false, options: ["Hund", "Katze"] }]);
  });

  it("requires a name before saving", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const user = userEvent.setup();
    renderIntl(<PortalFormsAdmin initialTemplates={[]} canManage />);
    await user.click(screen.getByRole("button", { name: "Neues Formular" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte einen Namen eingeben.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("deactivates a template and hides the actions without the permission", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      expect(String(input)).toBe(`/api/bff/portal-admin/forms/${TPL.id}`);
      expect(init?.method).toBe("PATCH");
      return jsonResponse({ ...TPL, active: false });
    });
    const user = userEvent.setup();
    const { unmount } = renderIntl(<PortalFormsAdmin initialTemplates={[TPL]} canManage />);
    expect(screen.getByTestId("portal-form-template")).toHaveTextContent("Nur Mieter");
    await user.click(screen.getByRole("button", { name: "Deaktivieren" }));
    await waitFor(() => expect(screen.getByText("inaktiv")).toBeInTheDocument());
    unmount();
    renderIntl(<PortalFormsAdmin initialTemplates={[TPL]} canManage={false} />);
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).toBeNull();
  });
});

describe("PortalFormsAdmin feedback (review 26.09.2026)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("confirms a deactivation and shows the API error of a failed one", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementationOnce(async () => jsonResponse({ ...TPL, active: false }));
    const user = userEvent.setup();
    renderIntl(<PortalFormsAdmin initialTemplates={[TPL]} canManage />);
    await user.click(screen.getByRole("button", { name: "Deaktivieren" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Gespeichert."));
    expect(screen.getByText("inaktiv")).toBeInTheDocument();
    vi.spyOn(globalThis, "fetch").mockImplementationOnce(async () => jsonResponse({ title: "Nicht erlaubt", status: 403 }, 403));
    await user.click(screen.getByRole("button", { name: "Aktivieren" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Nicht erlaubt"));
  });
});
