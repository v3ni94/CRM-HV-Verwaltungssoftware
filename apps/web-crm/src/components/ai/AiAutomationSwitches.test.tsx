import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AiAutomationSwitches } from "./AiAutomationSwitches";

const base = { rent_increase_check: false, batch_mail_classification: false, provider_released: false, blocked_reason: "Kein Anbieter" };

describe("AiAutomationSwitches", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads both switches off and saves one change", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/api/bff/ai/automation")) {
        return jsonResponse(init?.method === "PUT" ? { ...base, rent_increase_check: true } : base, 200);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<AiAutomationSwitches />);
    const box = screen.getByLabelText(/Mieterhöhungsfälle/);
    await waitFor(() => expect(box).toBeEnabled());
    expect(box).not.toBeChecked();
    expect(screen.getByText(/Kein Anbieter/)).toBeInTheDocument();
    await userEvent.click(box);
    await waitFor(() => expect(box).toBeChecked());
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({ rent_increase_check: true });
  });
});
