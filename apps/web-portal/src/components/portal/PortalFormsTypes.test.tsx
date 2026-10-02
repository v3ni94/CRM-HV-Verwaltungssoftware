import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { PortalForm } from "@/components/portal/types";
import { renderIntl } from "@/test/intl";

import { PortalForms } from "./PortalForms";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const FORM: PortalForm = {
  id: "01920000-0000-7000-8000-0000000000f2",
  name: "Adressänderung",
  description: null,
  audience: "all",
  fields: [
    { key: "anschrift", label: "Neue Anschrift", type: "address", required: true, options: null },
    { key: "ort", label: "Standort", type: "location", required: false, options: null },
    { key: "name", label: "Unterschrift", type: "signature", required: true, options: null },
    { key: "betrag", label: "Betrag", type: "amount", required: false, options: null },
    { key: "ok", label: "Einwilligung", type: "consent", required: true, options: null },
    { key: "linie", label: "Linie", type: "divider", required: false, options: null },
  ],
};

describe("PortalForms element types (AA14-01)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("shows hints and limits for the typed elements", async () => {
    const user = userEvent.setup();
    renderIntl(<PortalForms forms={[FORM]} />);
    await user.click(screen.getByRole("button", { name: /Adressänderung/ }));
    expect(screen.getByText(/Straße mit Hausnummer, Postleitzahl und Ort/)).toBeInTheDocument();
    expect(screen.getByText(/ersetzt keine handschriftliche Unterschrift/)).toBeInTheDocument();
    expect(screen.getByText(/höchstens zwei Nachkommastellen/)).toBeInTheDocument();
    expect(screen.getByLabelText("Unterschrift *")).toHaveAttribute("maxlength", "120");
    expect(screen.getByLabelText("Standort")).toHaveAttribute("maxlength", "300");
    expect(screen.getByLabelText("Neue Anschrift *").tagName).toBe("TEXTAREA");
    expect(screen.getByLabelText("Betrag")).toHaveAttribute("inputmode", "decimal");
  });

  it("shows the defect named by the API at the field", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(
      new Response(
        JSON.stringify({
          title: "Validierung",
          status: 422,
          detail: null,
          errors: [
            { location: ["values", "anschrift"], field: "values.anschrift", code: "invalid", message: "Anschrift unvollständig (Straße mit Hausnummer, Postleitzahl und Ort)." },
          ],
        }),
        { status: 422, headers: { "content-type": "application/problem+json" } },
      ),
    );
    renderIntl(<PortalForms forms={[FORM]} />);
    await user.click(screen.getByRole("button", { name: /Adressänderung/ }));
    await user.type(screen.getByLabelText("Neue Anschrift *"), "Weg 1");
    await user.type(screen.getByLabelText("Unterschrift *"), "Mia Muster");
    await user.click(screen.getByLabelText("Einwilligung *"));
    await user.click(screen.getByRole("button", { name: "Absenden" }));
    const field = screen.getByLabelText("Neue Anschrift *");
    await waitFor(() => expect(field).toHaveAttribute("aria-invalid", "true"));
    expect(field).toHaveAccessibleDescription(/Anschrift unvollständig/);
    expect(screen.getByRole("alert")).toHaveTextContent("Validierung");
    expect(screen.getByLabelText("Unterschrift *")).not.toHaveAttribute("aria-invalid");
  });
});
