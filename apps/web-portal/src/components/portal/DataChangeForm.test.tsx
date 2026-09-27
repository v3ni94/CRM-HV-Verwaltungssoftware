import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DataChangeForm } from "./DataChangeForm";

describe("DataChangeForm", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("names the missing input on an empty submit instead of showing the success text", async () => {
    const user = userEvent.setup();
    renderIntl(<DataChangeForm />);
    await user.click(screen.getByRole("button", { name: "Änderung vorschlagen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte mindestens eine Änderung angeben.");
    expect(screen.queryByText("Die Änderung wurde als Vorschlag übermittelt.")).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("uses matching input types and autocomplete attributes per kind", async () => {
    const user = userEvent.setup();
    renderIntl(<DataChangeForm />);
    expect(screen.getByLabelText("PLZ")).toHaveAttribute("autocomplete", "postal-code");
    await user.selectOptions(screen.getByLabelText("Art der Änderung"), "email");
    const email = screen.getByLabelText("E-Mail-Adresse");
    expect(email).toHaveAttribute("type", "email");
    expect(email).toHaveAttribute("autocomplete", "email");
    await user.selectOptions(screen.getByLabelText("Art der Änderung"), "phone");
    const phone = screen.getByLabelText("Telefonnummer");
    expect(phone).toHaveAttribute("type", "tel");
    expect(phone).toHaveAttribute("autocomplete", "tel");
  });

  it("assigns 422 field errors of the API to the fields via aria-invalid and aria-describedby", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(
        {
          status: 422,
          detail: null,
          errors: [
            {
              location: ["body", "payload", "email"],
              field: "email",
              code: "invalid",
              message: "Bitte eine gültige E-Mail-Adresse angeben.",
            },
          ],
        },
        422,
      ),
    );
    renderIntl(<DataChangeForm />);
    await user.selectOptions(screen.getByLabelText("Art der Änderung"), "email");
    await user.type(screen.getByLabelText("E-Mail-Adresse"), "keine-adresse");
    await user.click(screen.getByRole("button", { name: "Änderung vorschlagen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte die markierten Angaben prüfen.");
    const email = screen.getByLabelText("E-Mail-Adresse");
    expect(email).toHaveAttribute("aria-invalid", "true");
    const errorId = email.getAttribute("aria-describedby");
    expect(errorId).toBeTruthy();
    expect(document.getElementById(errorId ?? "")).toHaveTextContent("Bitte eine gültige E-Mail-Adresse angeben.");
  });

  it("submits the trimmed payload and shows the confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: "cr1" }, 201));
    renderIntl(<DataChangeForm />);
    await user.selectOptions(screen.getByLabelText("Art der Änderung"), "phone");
    await user.type(screen.getByLabelText("Telefonnummer"), " 0211 123456 ");
    await user.click(screen.getByRole("button", { name: "Änderung vorschlagen" }));
    await waitFor(() => expect(screen.getByText("Die Änderung wurde als Vorschlag übermittelt.")).toBeInTheDocument());
    // The confirmation receives the focus (keyboard/screen reader users).
    expect(screen.getByText("Die Änderung wurde als Vorschlag übermittelt.")).toHaveFocus();
    expect(fetch).toHaveBeenCalledWith(
      "/api/bff/portal/change-requests",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ kind: "phone", payload: { number: "0211 123456" } }),
      }),
    );
  });
});
