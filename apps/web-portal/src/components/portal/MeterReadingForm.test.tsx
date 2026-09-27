import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MeterReadingForm } from "./MeterReadingForm";

describe("MeterReadingForm", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("shows all required field errors at once and marks the fields", async () => {
    const user = userEvent.setup();
    renderIntl(<MeterReadingForm />);
    await user.click(screen.getByRole("button", { name: "Melden" }));
    expect(await screen.findByText("Bitte die Zähler-ID eingeben.")).toBeInTheDocument();
    expect(screen.getByText("Bitte einen Zählerstand eingeben.")).toBeInTheDocument();
    expect(screen.getByText("Bitte ein Ablesedatum eingeben.")).toBeInTheDocument();
    const meterId = screen.getByLabelText("Zähler-ID");
    expect(meterId).toHaveAttribute("aria-invalid", "true");
    expect(document.getElementById(meterId.getAttribute("aria-describedby") ?? "")).toHaveTextContent(
      "Bitte die Zähler-ID eingeben.",
    );
    expect(screen.getByLabelText("Zählerstand")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Ablesedatum")).toHaveAttribute("aria-invalid", "true");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("clears the field error after correcting the input", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: "m1" }, 201));
    renderIntl(<MeterReadingForm />);
    await user.click(screen.getByRole("button", { name: "Melden" }));
    expect(await screen.findByText("Bitte einen Zählerstand eingeben.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Zähler-ID"), "Z-100");
    await user.type(screen.getByLabelText("Zählerstand"), "12");
    await user.type(screen.getByLabelText("Ablesedatum"), "2026-09-01");
    await user.click(screen.getByRole("button", { name: "Melden" }));
    await waitFor(() => expect(screen.queryByText("Bitte einen Zählerstand eingeben.")).not.toBeInTheDocument());
  });

  it("submits the reading with a decimal point and shows the confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: "m1" }, 201));
    renderIntl(<MeterReadingForm />);
    await user.type(screen.getByLabelText("Zähler-ID"), " Z-100 ");
    await user.type(screen.getByLabelText("Zählerstand"), "1234,5");
    await user.type(screen.getByLabelText("Ablesedatum"), "2026-09-01");
    await user.click(screen.getByRole("button", { name: "Melden" }));
    await waitFor(() =>
      expect(screen.getByText("Der Zählerstand wurde als Vorschlag übermittelt.")).toBeInTheDocument(),
    );
    expect(fetch).toHaveBeenCalledWith(
      "/api/bff/portal/meter-readings",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ meter_id: "Z-100", value: "1234.5", read_at: "2026-09-01" }),
      }),
    );
  });
});
