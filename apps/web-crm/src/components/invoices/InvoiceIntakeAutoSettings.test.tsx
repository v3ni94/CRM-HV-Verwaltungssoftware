import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InvoiceIntakeAutoSettings } from "./InvoiceIntakeAutoSettings";

describe("InvoiceIntakeAutoSettings", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is off by default, shows the cost hint and saves the switch", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/api/bff/ai/invoice-intake-auto") && init?.method === "PUT") {
        return jsonResponse({ enabled: true }, 200);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<InvoiceIntakeAutoSettings initial={false} />);
    const box = screen.getByLabelText(/automatisch erfassen/);
    expect(box).not.toBeChecked();
    expect(screen.getByText(/KI-Kosten/)).toBeInTheDocument();
    await userEvent.click(box);
    await waitFor(() => expect(screen.getByText("Einstellung gespeichert.")).toBeInTheDocument());
    expect(box).toBeChecked();
    const call = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/api/bff/ai/invoice-intake-auto"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ enabled: true });
  });
});
