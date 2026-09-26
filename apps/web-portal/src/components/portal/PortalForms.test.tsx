import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { PortalForm } from "@/components/portal/types";
import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalForms } from "./PortalForms";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

const FORM: PortalForm = {
  id: "01920000-0000-7000-8000-0000000000f1",
  name: "Antrag Untervermietung",
  description: "Bitte alle Angaben ausfüllen.",
  audience: "tenant",
  fields: [
    { key: "anliegen", label: "Anliegen", type: "text", required: true, options: null },
    { key: "ab", label: "Ab dem", type: "date", required: false, options: null },
    { key: "art", label: "Art", type: "select", required: true, options: ["Untervermietung", "Haustier"] },
  ],
};

describe("PortalForms", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("shows the empty notice without forms", () => {
    renderIntl(<PortalForms forms={[]} />);
    expect(screen.getByText("Derzeit stellt Ihre Verwaltung keine Formulare bereit.")).toBeInTheDocument();
  });

  it("checks required fields before sending", async () => {
    const user = userEvent.setup();
    renderIntl(<PortalForms forms={[FORM]} />);
    await user.click(screen.getByRole("button", { name: /Antrag Untervermietung/ }));
    await user.click(screen.getByRole("button", { name: "Absenden" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte das Feld Anliegen ausfüllen.");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("submits the values as a case and shows the confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: "s1", ticket_number: 12 }, 201));
    renderIntl(<PortalForms forms={[FORM]} />);
    await user.click(screen.getByRole("button", { name: /Antrag Untervermietung/ }));
    await user.type(screen.getByLabelText("Anliegen *"), "Untervermietung an meine Schwester");
    await user.selectOptions(screen.getByLabelText("Art *"), "Untervermietung");
    await user.click(screen.getByRole("button", { name: "Absenden" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Antrag Untervermietung wurde übermittelt"));
    expect(fetch).toHaveBeenCalledWith(
      `/api/bff/portal/forms/${FORM.id}/submissions`,
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ values: { anliegen: "Untervermietung an meine Schwester", art: "Untervermietung" } }),
      }),
    );
  });
});
