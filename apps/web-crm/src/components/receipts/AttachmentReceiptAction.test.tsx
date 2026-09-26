import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AttachmentReceiptAction } from "./AttachmentReceiptAction";

const MESSAGE = "0192abcd-0000-7000-8000-000000000001";
const DOCUMENT = "0192abcd-0000-7000-8000-000000000002";

describe("AttachmentReceiptAction", () => {
  afterEach(() => vi.restoreAllMocks());

  it("starts a receipt draft from the mail attachment and links to the Belegeingang", async () => {
    const onCreated = vi.fn();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      expect(JSON.parse(String(init?.body))).toEqual({ document_id: DOCUMENT, source: "mail_attachment", message_id: MESSAGE });
      return jsonResponse({ id: "draft-1", status: "extracting" }, 202);
    });
    renderIntl(<AttachmentReceiptAction messageId={MESSAGE} documentId={DOCUMENT} label="Anhang 1" onCreated={onCreated} />);
    await userEvent.click(screen.getByRole("button", { name: "Anhang 1: Als Rechnung erfassen" }));
    const link = await screen.findByRole("link", { name: "Entwurf im Belegeingang öffnen" });
    expect(link).toHaveAttribute("href", "/rechnungen/belegeingang?entwurf=draft-1");
    expect(fetchMock).toHaveBeenCalledWith("/api/bff/receipts/drafts", expect.objectContaining({ method: "POST" }));
    expect(onCreated).toHaveBeenCalledWith({ id: "draft-1", status: "extracting" });
  });

  it("shows the API reason when the extraction cannot be started", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ title: "Validierung", detail: "Nur PDF, Bild oder Textbelege können als Rechnung erfasst werden.", status: 422 }, 422),
    );
    renderIntl(<AttachmentReceiptAction messageId={MESSAGE} documentId={DOCUMENT} />);
    await userEvent.click(screen.getByRole("button", { name: "Als Rechnung erfassen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Rechnungserfassung nicht möglich: Nur PDF, Bild oder Textbelege können als Rechnung erfasst werden.",
    );
    expect(screen.getByRole("button", { name: "Als Rechnung erfassen" })).toBeEnabled();
  });
});
