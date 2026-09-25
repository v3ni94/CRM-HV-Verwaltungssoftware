import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InvoiceForwardingSettings } from "./InvoiceForwardingSettings";

const initial = {
  enabled: false,
  forward_address: null,
  sender_allowlist: [],
  learning_list: [],
};

describe("InvoiceForwardingSettings", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves the forwarding address and allowlist", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/api/bff/mail/invoice-forwarding") && method === "PUT") {
        return jsonResponse(
          {
            enabled: true,
            forward_address: "muellerhv@inbox.lexware.email",
            sender_allowlist: ["rechnung@telekom.de"],
            learning_list: [],
          },
          200,
        );
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });

    renderIntl(<InvoiceForwardingSettings initial={initial} />);

    await userEvent.click(screen.getByLabelText("Weiterleitung aktiv"));
    await userEvent.type(screen.getByLabelText("Zieladresse"), "muellerhv@inbox.lexware.email");
    await userEvent.type(screen.getByLabelText(/Positivliste/), "rechnung@telekom.de");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(screen.getByText("Gespeichert.")).toBeInTheDocument());
    const call = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/api/bff/mail/invoice-forwarding"));
    expect(call).toBeDefined();
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      enabled: true,
      forward_address: "muellerhv@inbox.lexware.email",
      sender_allowlist: ["rechnung@telekom.de"],
    });
  });

  it("shows the learning list once senders were auto-confirmed", () => {
    renderIntl(
      <InvoiceForwardingSettings
        initial={{ ...initial, learning_list: ["poetter@example.com"] }}
      />,
    );
    expect(screen.getByText(/poetter@example.com/)).toBeInTheDocument();
  });
});
