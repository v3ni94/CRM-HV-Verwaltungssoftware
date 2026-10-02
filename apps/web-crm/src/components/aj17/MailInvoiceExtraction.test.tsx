import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MailInvoiceExtraction } from "./MailInvoiceExtraction";

describe("MailInvoiceExtraction (GAI-418)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("starts the extraction and reports the proposal run", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ run_id: "run-7", proposal_id: null }, 202));
    renderIntl(<MailInvoiceExtraction messageId="01920000-0000-7000-8000-0000000a1701" attachmentId="01920000-0000-7000-8000-0000000a1702" />);
    await userEvent.click(screen.getByRole("button", { name: "Als Rechnung vorschlagen (KI)" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Extraktion gestartet (Lauf run-7)");
    expect(f.mock.calls[0]![0]).toBe("/api/bff/mail/messages/01920000-0000-7000-8000-0000000a1701/attachments/01920000-0000-7000-8000-0000000a1702/invoice-extraction");
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("shows the API reason and skips non PDF files", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Validierung", detail: "Nur PDF-Anhänge.", status: 422 }, 422));
    const { unmount } = renderIntl(<MailInvoiceExtraction messageId="01920000-0000-7000-8000-0000000a1701" attachmentId="01920000-0000-7000-8000-0000000a1702" />);
    await userEvent.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    unmount();
    const { container } = renderIntl(<MailInvoiceExtraction messageId="01920000-0000-7000-8000-0000000a1701" attachmentId="01920000-0000-7000-8000-0000000a1702" mimeType="image/png" />);
    expect(container).toBeEmptyDOMElement();
  });
});
