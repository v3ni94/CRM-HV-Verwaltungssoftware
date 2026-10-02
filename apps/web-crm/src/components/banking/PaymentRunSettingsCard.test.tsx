import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PaymentRunSettingsCard } from "./PaymentRunSettingsCard";

describe("PaymentRunSettingsCard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is read only without the settings right", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ weekly_preview_enabled: false, schedule: "Montag 08:00" }),
    );
    renderIntl(<PaymentRunSettingsCard canUpdate={false} />);
    expect(await screen.findByRole("checkbox")).toBeDisabled();
  });

  it("switches the weekly preview on", async () => {
    let body = "";
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "PUT") {
        body = String(init.body);
        return jsonResponse({ weekly_preview_enabled: true, schedule: "Montag 08:00" });
      }
      return jsonResponse({ weekly_preview_enabled: false, schedule: "Montag 08:00" });
    });
    renderIntl(<PaymentRunSettingsCard canUpdate={true} />);
    await userEvent.click(await screen.findByRole("checkbox"));
    await waitFor(() => expect(body).toBe('{"weekly_preview_enabled":true}'));
  });
});
