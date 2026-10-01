import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DocumentIntakeSettings, type IntakeAddress } from "./DocumentIntakeSettings";

const empty: IntakeAddress = { configured: false, enabled: false, address: null, mailbox_address: null, allowed_senders: [], distribute: false };

describe("DocumentIntakeSettings", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("saves the address with senders and the distribution switch and shows the address", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async () =>
      jsonResponse({ configured: true, enabled: true, address: "belege+ab12@example.de", mailbox_address: "belege@example.de", allowed_senders: ["@lieferant.de"], distribute: true }),
    );
    renderIntl(<DocumentIntakeSettings initial={empty} directUpload={false} />);
    expect(screen.getByText("Noch nicht eingerichtet.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Sammelpostfach"), "belege@example.de");
    await user.type(screen.getByLabelText("Erlaubte Absender"), "@lieferant.de");
    await user.click(screen.getByLabelText("Nachrichten anderer Mandanten dieses Postfachs verteilen"));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByTestId("intake-address-value")).toHaveTextContent("belege+ab12@example.de");
    const call = fetchMock.mock.calls[0];
    expect(String(call?.[0])).toBe("/api/bff/document-intake-address");
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({
      mailbox_address: "belege@example.de",
      allowed_senders: ["@lieferant.de"],
      enabled: true,
      distribute: true,
    });
  });

  it("switches the direct upload on and off, default off", async () => {
    const user = userEvent.setup();
    fetchMock.mockImplementation(async (_input, init) => jsonResponse({ enabled: JSON.parse(String((init as RequestInit).body)).enabled }));
    renderIntl(<DocumentIntakeSettings initial={empty} directUpload={false} />);
    const box = screen.getByLabelText("Dateien direkt in den Objektspeicher hochladen (signierte URL)");
    expect(box).not.toBeChecked();
    await user.click(box);
    await waitFor(() => expect(box).toBeChecked());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe("/api/bff/document-direct-upload");
  });
});
