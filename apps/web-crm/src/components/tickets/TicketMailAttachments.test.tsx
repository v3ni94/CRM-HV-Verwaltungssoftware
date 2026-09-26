import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketMailAttachments, type TicketMailAttachment } from "./TicketMailAttachments";

const base = { message_id: "m-1", received_at: "2026-09-20T08:00:00Z", subject: "Rechnung Heizung" };
const pdf: TicketMailAttachment = { ...base, document_id: "d-1", filename: "rechnung.pdf", mime_type: "application/pdf" };
const image: TicketMailAttachment = { ...base, document_id: "d-2", filename: "foto.jpg", mime_type: "image/jpeg" };
const zip: TicketMailAttachment = { ...base, document_id: "d-3", filename: "archiv.zip", mime_type: "application/zip" };

describe("TicketMailAttachments", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing without attachments", () => {
    const { container } = renderIntl(<TicketMailAttachments attachments={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("offers the receipt action for PDF and image attachments only", () => {
    renderIntl(<TicketMailAttachments attachments={[pdf, image, zip]} />);
    expect(screen.getByText("rechnung.pdf")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Als Rechnung erfassen" })).toHaveLength(2);
    expect(screen.getByText("kein Beleg (Dateityp)")).toBeInTheDocument();
  });

  it("starts the draft with message and document of the attachment", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      expect(JSON.parse(String(init?.body))).toEqual({ document_id: "d-1", source: "mail_attachment", message_id: "m-1" });
      return jsonResponse({ id: "draft-9", status: "extracting" }, 202);
    });
    renderIntl(<TicketMailAttachments attachments={[pdf]} />);
    await userEvent.click(screen.getByRole("button", { name: "Als Rechnung erfassen" }));
    expect(await screen.findByRole("link", { name: "Entwurf im Belegeingang öffnen" })).toHaveAttribute("href", "/rechnungen/belegeingang?entwurf=draft-9");
    expect(fetchMock).toHaveBeenCalledWith("/api/bff/receipts/drafts", expect.objectContaining({ method: "POST" }));
  });
});
