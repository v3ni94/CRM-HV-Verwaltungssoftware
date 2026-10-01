import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import type { PortalFormField } from "./PortalFormsAdmin";
import { PortalFormPreview } from "./PortalFormPreview";

const FIELDS: PortalFormField[] = [
  { key: "kopf", label: "Angaben", type: "heading", required: false },
  { key: "anschrift", label: "Neue Anschrift", type: "address", required: true },
  { key: "name", label: "Unterschrift", type: "signature", required: true },
  { key: "betrag", label: "Betrag", type: "amount", required: false },
  { key: "ok", label: "Einwilligung", type: "consent", required: true },
  { key: "art", label: "Art", type: "select", required: false, options: ["A", "B"] },
  { key: "linie", label: "Linie", type: "divider", required: false },
  { key: "datei", label: "Anhang", type: "file", required: true },
];

describe("PortalFormPreview", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders every element type like the portal and sends sample values to the dry run", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ valid: true, errors: [], rendered: "Formular: Test\nBetrag: 1.234,50 EUR" }),
    );
    renderIntl(<PortalFormPreview name="Test" fields={FIELDS} />);
    expect(screen.getByRole("heading", { name: "Angaben" })).toBeInTheDocument();
    expect(screen.getByLabelText("Neue Anschrift *").tagName).toBe("TEXTAREA");
    expect(screen.getByLabelText("Anhang *")).toBeDisabled();
    await user.type(screen.getByLabelText("Neue Anschrift *"), "Weg 1, 12345 Ort");
    await user.type(screen.getByLabelText("Unterschrift *"), " Max Muster ");
    await user.type(screen.getByLabelText("Betrag"), "1234,5");
    await user.click(screen.getByLabelText("Einwilligung *"));
    await user.selectOptions(screen.getByLabelText("Art"), "B");
    await user.click(screen.getByRole("button", { name: "Beispielwerte prüfen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls.at(0)?.[0]).toBe("/api/bff/portal-admin/forms/preview");
    const sent = JSON.parse(String(fetchMock.mock.calls.at(0)?.[1]?.body));
    expect(sent.name).toBe("Test");
    expect(sent.values).toEqual({ anschrift: "Weg 1, 12345 Ort", name: "Max Muster", betrag: "1234,5", ok: "true", art: "B" });
    expect(sent.fields).toHaveLength(FIELDS.length);
    expect(await screen.findByText("Die Beispielwerte sind gültig.")).toBeInTheDocument();
    expect(screen.getByTestId("portal-form-preview-text")).toHaveTextContent("Betrag: 1.234,50 EUR");
  });

  it("shows the field errors of the dry run at the field", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        valid: false,
        errors: [{ field: "values.anschrift", message: "Anschrift unvollständig (Straße mit Hausnummer, Postleitzahl und Ort)." }],
        rendered: null,
      }),
    );
    renderIntl(<PortalFormPreview name="" fields={FIELDS} />);
    await user.type(screen.getByLabelText("Neue Anschrift *"), "Weg 1");
    await user.click(screen.getByRole("button", { name: "Beispielwerte prüfen" }));
    expect(await screen.findByText(/Anschrift unvollständig/)).toBeInTheDocument();
    expect(screen.getByLabelText("Neue Anschrift *")).toHaveAccessibleDescription(/Anschrift unvollständig/);
    expect(screen.getByText(/nicht gültig, 1 Angabe/)).toBeInTheDocument();
    expect(screen.queryByTestId("portal-form-preview-text")).toBeNull();
  });

  it("reports a defect of the definition", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ title: "Validierung", status: 422, detail: "Auswahl ohne Optionen." }, 422),
    );
    renderIntl(<PortalFormPreview name="X" fields={[{ key: "a", label: "A", type: "select", required: false, options: [] }]} />);
    await user.click(screen.getByRole("button", { name: "Beispielwerte prüfen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Auswahl ohne Optionen.");
  });

  it("is disabled without fields", () => {
    renderIntl(<PortalFormPreview name="X" fields={[]} />);
    expect(screen.getByText("Das Formular hat noch keine Felder.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Beispielwerte prüfen" })).toBeDisabled();
  });
});
