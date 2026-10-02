import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MailSourcesAdmin, type MailSource } from "./MailSourcesAdmin";

const ID = "11111111-1111-4111-8111-111111111111";
const source: MailSource = {
  id: ID, name: "Immoware", active: true, mailbox_id: null, auto_ticket: true,
  last_received_at: null, secret_rotated_at: null, created_at: "2026-10-01T08:00:00+00:00",
  delivery_path: `/api/v1/mail/inbound/sources/${ID}/classified-mails`,
};

describe("MailSourcesAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the secret once after rotation and never lists it again", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...source, secret: "geheim-123" }));
    renderIntl(<MailSourcesAdmin initial={[source]} canManage />);
    await userEvent.click(screen.getByRole("button", { name: "Geheimnis erneuern" }));
    await waitFor(() => expect(screen.getByTestId("secret-once")).toHaveTextContent("geheim-123"));
    expect(String(fetchMock.mock.calls[0]![0])).toBe(`/api/bff/mail/inbound/sources/${ID}/rotate-secret`);
    await userEvent.click(screen.getByRole("button", { name: "Ich habe den Wert gesichert" }));
    expect(screen.queryByText("geheim-123")).not.toBeInTheDocument();
    expect(screen.getByTestId(`mail-source-${ID}`)).not.toHaveTextContent("geheim-123");
  });

  it("hides actions without update permission and loads the receipt log", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
    renderIntl(<MailSourcesAdmin initial={[source]} canManage={false} />);
    expect(screen.queryByRole("button", { name: "Geheimnis erneuern" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Protokoll" }));
    await waitFor(() => expect(screen.getByText("Noch keine Empfänge.")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[0]![0])).toBe(`/api/bff/mail/inbound/sources/${ID}/events?limit=50`);
  });
});
