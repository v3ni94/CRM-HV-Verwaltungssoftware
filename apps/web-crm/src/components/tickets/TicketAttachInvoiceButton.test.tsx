import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketAttachInvoiceButton } from "./TicketAttachInvoiceButton";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

describe("TicketAttachInvoiceButton", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is disabled when the ticket has no property", () => {
    renderIntl(<TicketAttachInvoiceButton ticketId="t-1" hasProperty={false} />);
    expect(screen.getByRole("button", { name: "Als Rechnung zuordnen" })).toBeDisabled();
  });

  it("attaches an invoice and reports the drive filing", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      expect(JSON.parse(String(init?.body))).toEqual({ invoice_id: "0192abcd-0000-7000-8000-000000000020" });
      return jsonResponse({ id: "t-1", category: "invoice" });
    });
    renderIntl(<TicketAttachInvoiceButton ticketId="t-1" hasProperty={true} />);
    await userEvent.click(screen.getByRole("button", { name: "Als Rechnung zuordnen" }));
    await userEvent.type(screen.getByLabelText("Rechnungs-ID"), "0192abcd-0000-7000-8000-000000000020");
    await userEvent.click(screen.getByRole("button", { name: "Als Rechnung zuordnen" }));
    expect(await screen.findByText("Als Rechnung zugeordnet und im Objektordner abgelegt.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/bff/tickets/t-1/attach-invoice", expect.objectContaining({ method: "POST" }));
    expect(refresh).toHaveBeenCalled();
  });
});
