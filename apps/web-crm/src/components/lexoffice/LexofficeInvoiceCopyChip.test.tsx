import { screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LexofficeInvoiceCopyChip } from "./LexofficeInvoiceCopyChip";

const TICKET = "01920000-0000-7000-8000-00000000f404";
const MSG = "01920000-0000-7000-8000-0000000000a1";

describe("LexofficeInvoiceCopyChip", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the request found at the ticket for this mail with a link to the ticket", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([{ id: "r1", message_id: MSG, invoice_number: "RE-1019", status: "found" }]));
    renderIntl(<LexofficeInvoiceCopyChip messageId={MSG} ticketId={TICKET} />);
    await waitFor(() => expect(screen.getByTestId("lexoffice-invoice-copy-chip")).toHaveTextContent("Rechnungskopie erkannt: RE-1019"));
    expect(screen.getByRole("link", { name: "Zum Ticket" })).toHaveAttribute("href", `/tickets/${TICKET}`);
  });

  it("falls back to the stored suggestion intent without a ticket and fetches nothing", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    renderIntl(<LexofficeInvoiceCopyChip messageId={MSG} ticketId={null} intent="invoice_copy_requested" />);
    expect(screen.getByTestId("lexoffice-invoice-copy-chip")).toHaveTextContent("Rechnungskopie erkannt");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("renders nothing when no request and no intent exist", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([{ id: "r1", message_id: "other", invoice_number: "RE-1", status: "found" }]));
    const { container } = renderIntl(<LexofficeInvoiceCopyChip messageId={MSG} ticketId={TICKET} />);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
