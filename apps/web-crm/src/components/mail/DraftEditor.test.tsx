import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { IntlTestProvider, jsonResponse, renderIntl } from "@/test/intl";

import { DraftEditor } from "./DraftEditor";
import type { Message } from "./MailWorkspace";

function makeDraft(overrides: Partial<Message> = {}): Message {
  return {
    id: "d1",
    channel: "email",
    direction: "out",
    status: "draft",
    from_address: null,
    to_addresses: ["mieter@example.com"],
    subject: "AW: Heizung defekt",
    body: "Sehr geehrte Damen und Herren,",
    received_at: null,
    sent_at: null,
    contact_id: null,
    property_id: null,
    ticket_id: null,
    thread_id: "m1",
    document_id: null,
    attachment_document_ids: [],
    classification: {},
    appointment_suggestions: [],
    created_by: "u1",
    mailbox_id: "b1",
    submitted_by: null,
    submitted_at: null,
    approved_by: null,
    approved_at: null,
    rejection_note: null,
    suggestion: {},
    suggestion_status: "none",
    ...overrides,
  };
}

function withIntl(ui: React.ReactElement) {
  return (
    <IntlTestProvider>
      {ui}
    </IntlTestProvider>
  );
}

/** Hands the saved draft back as a prop, like MailDetail and MailWorkspace do. */
function Harness({ initial }: { initial: Message }) {
  const [message, setMessage] = useState(initial);
  return <DraftEditor message={message} onUpdated={setMessage} />;
}

function patchPayloads(fetchMock: { mock: { calls: unknown[][] } }): Record<string, unknown>[] {
  return fetchMock.mock.calls
    .filter(([, init]) => (init as RequestInit | undefined)?.method === "PATCH")
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)) as Record<string, unknown>);
}

const pdf = { document_id: "doc1", title: "Hausordnung", filename: "hausordnung.pdf", mime_type: "application/pdf", size: 2048 };
const upload = { document_id: "doc2", title: "nachweis.pdf", filename: "nachweis.pdf", mime_type: "application/pdf", size: 512 };

describe("DraftEditor", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves To, Cc, subject and text through the draft endpoint (operator 27.09.2026)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/attachments") && !init?.method) return jsonResponse([], 200);
      if (url.endsWith("/draft") && init?.method === "PATCH") {
        return jsonResponse(makeDraft({ body: JSON.parse(String(init.body)).body }), 200);
      }
      return jsonResponse([], 200);
    });
    const onUpdated = vi.fn();
    renderIntl(<DraftEditor message={makeDraft()} onUpdated={onUpdated} />);
    await screen.findByText("Keine Anhänge.");
    await userEvent.type(screen.getByLabelText("Kopie (Cc, kommagetrennt)"), "kopie@example.com");
    const body = screen.getByLabelText("Text");
    await userEvent.clear(body);
    await userEvent.type(body, "Manuell bearbeiteter Text.");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(onUpdated).toHaveBeenCalled());
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(patch).toBeDefined();
    const payload = JSON.parse(String(patch?.[1]?.body));
    expect(payload).toEqual({
      subject: "AW: Heizung defekt",
      body: "Manuell bearbeiteter Text.",
      to_addresses: ["mieter@example.com"],
      cc_addresses: ["kopie@example.com"],
    });
  });

  it("lists attachments, removes one, adds one from the DMS and uploads a local file", async () => {
    let attachments = [pdf];
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/messages/d1/attachments") && method === "GET") return jsonResponse(attachments, 200);
      if (url.endsWith("/messages/d1/attachments/doc1") && method === "DELETE") {
        attachments = [];
        return jsonResponse(attachments, 200);
      }
      if (url.includes("/messages/d1/attachment-candidates?q=")) return jsonResponse([pdf], 200);
      if (url.endsWith("/messages/d1/attachments") && method === "POST") {
        attachments = [pdf];
        return jsonResponse(attachments, 201);
      }
      if (url.endsWith("/messages/d1/attachments/upload") && method === "POST") {
        expect(init?.body).toBeInstanceOf(FormData);
        attachments = [...attachments, upload];
        return jsonResponse(attachments, 201);
      }
      return jsonResponse([], 200);
    });
    renderIntl(<DraftEditor message={makeDraft({ attachment_document_ids: ["doc1"] })} onUpdated={() => {}} />);
    const section = screen.getByTestId("mail-draft-attachments");
    await within(section).findByText("hausordnung.pdf", { exact: false });

    await userEvent.click(screen.getByRole("button", { name: "Anhang hausordnung.pdf entfernen" }));
    await within(section).findByText("Keine Anhänge.");
    expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith("/attachments/doc1") && init?.method === "DELETE")).toBe(true);

    await userEvent.click(screen.getByRole("button", { name: "Aus dem DMS hinzufügen" }));
    await userEvent.type(screen.getByPlaceholderText("Titel oder Dateiname (mindestens 2 Zeichen)"), "haus");
    await userEvent.click(screen.getByRole("button", { name: "Suchen" }));
    await userEvent.click(await screen.findByRole("button", { name: "Anhängen" }));
    await within(section).findByText("hausordnung.pdf", { exact: false });
    const linked = fetchMock.mock.calls.find(([input, init]) => String(input).endsWith("/messages/d1/attachments") && init?.method === "POST");
    expect(JSON.parse(String(linked?.[1]?.body))).toEqual({ document_id: "doc1" });
    expect(within(section).getByText("Keine Dokumente gefunden.")).toBeInTheDocument();

    const file = new File(["%PDF-1.4 nachweis"], "nachweis.pdf", { type: "application/pdf" });
    await userEvent.upload(screen.getByTestId("mail-draft-upload-input"), file);
    await within(section).findByText("nachweis.pdf", { exact: false });
  });

  it("shows the server's reason when an upload is refused", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/attachments/upload") && init?.method === "POST") {
        return jsonResponse({ title: "Upload abgelehnt", status: 422, detail: "Dateityp application/x-msdownload ist nicht zulässig." }, 422);
      }
      return jsonResponse([], 200);
    });
    renderIntl(<DraftEditor message={makeDraft()} onUpdated={() => {}} />);
    await screen.findByText("Keine Anhänge.");
    const file = new File(["MZ"], "setup.exe", { type: "application/x-msdownload" });
    await userEvent.upload(screen.getByTestId("mail-draft-upload-input"), file);
    expect(await screen.findByRole("alert")).toHaveTextContent("Dateityp application/x-msdownload ist nicht zulässig.");
  });

  it("explains a refused submit instead of failing silently", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/draft") && init?.method === "PATCH") return jsonResponse(makeDraft(), 200);
      if (url.endsWith("/submit") && init?.method === "POST") {
        return jsonResponse({ title: "Konflikt", status: 409, detail: "Das Postfach info@example.com ist nicht mit Google verbunden." }, 409);
      }
      return jsonResponse([], 200);
    });
    renderIntl(<DraftEditor message={makeDraft()} onUpdated={() => {}} />);
    await screen.findByText("Keine Anhänge.");
    await userEvent.click(screen.getByRole("button", { name: "Zur Freigabe" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("nicht mit Google verbunden");
  });

  it("shows the newer text when the same draft comes back from outside and submits it (review 1.36.0)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/draft") && init?.method === "PATCH") return jsonResponse(makeDraft({ body: JSON.parse(String(init.body)).body }), 200);
      if (url.endsWith("/submit") && init?.method === "POST") return jsonResponse(makeDraft({ status: "pending" }), 200);
      return jsonResponse([], 200);
    });
    const { rerender } = renderIntl(<DraftEditor message={makeDraft({ body: "Guten Tag [Name]," })} onUpdated={() => {}} />);
    await screen.findByText("Keine Anhänge.");
    expect(screen.getByLabelText("Text")).toHaveValue("Guten Tag [Name],");

    // "Vorschlag übernehmen" stored a new text on the same draft id.
    rerender(withIntl(<DraftEditor message={makeDraft({ body: "Übernommener Vorschlag" })} onUpdated={() => {}} />));
    expect(screen.getByLabelText("Text")).toHaveValue("Übernommener Vorschlag");
    expect(screen.queryByTestId("mail-draft-newer-version")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Zur Freigabe" }));
    await waitFor(() => expect(patchPayloads(fetchMock)).toHaveLength(1));
    expect(patchPayloads(fetchMock)[0]?.body).toBe("Übernommener Vorschlag");
  });

  it("asks before a newer text replaces unsaved edits (review 1.36.0)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([], 200));
    const { rerender } = renderIntl(<DraftEditor message={makeDraft({ body: "Vorlage" })} onUpdated={() => {}} />);
    await screen.findByText("Keine Anhänge.");
    const text = screen.getByLabelText("Text");
    await userEvent.clear(text);
    await userEvent.type(text, "Eigene Formulierung");

    rerender(withIntl(<DraftEditor message={makeDraft({ body: "Vorschlag eins" })} onUpdated={() => {}} />));
    const notice = screen.getByTestId("mail-draft-newer-version");
    expect(notice).toHaveTextContent("Sie haben ungespeicherte Änderungen");
    expect(screen.getByLabelText("Text")).toHaveValue("Eigene Formulierung");
    // Nothing is written back until the user has decided.
    expect(screen.getByRole("button", { name: "Speichern" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Zur Freigabe" })).toBeDisabled();

    await userEvent.click(within(notice).getByRole("button", { name: "Meine Änderungen behalten" }));
    expect(screen.queryByTestId("mail-draft-newer-version")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Text")).toHaveValue("Eigene Formulierung");
    expect(screen.getByRole("button", { name: "Speichern" })).toBeEnabled();

    rerender(withIntl(<DraftEditor message={makeDraft({ body: "Vorschlag zwei" })} onUpdated={() => {}} />));
    await userEvent.click(within(screen.getByTestId("mail-draft-newer-version")).getByRole("button", { name: "Neuen Text übernehmen" }));
    expect(screen.getByLabelText("Text")).toHaveValue("Vorschlag zwei");
    expect(screen.queryByTestId("mail-draft-newer-version")).not.toBeInTheDocument();
  });

  it("does not take its own saved answer for a newer version", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/draft") && init?.method === "PATCH") {
        const sent = JSON.parse(String(init.body));
        return jsonResponse(makeDraft({ subject: sent.subject, body: sent.body }), 200);
      }
      return jsonResponse([], 200);
    });
    renderIntl(<Harness initial={makeDraft()} />);
    await screen.findByText("Keine Anhänge.");
    // The server stores the trimmed subject, the input keeps the trailing blank.
    await userEvent.type(screen.getByLabelText("Betreff"), " ");
    await userEvent.type(screen.getByLabelText("Text"), " Danke.");
    await userEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Speichern" })).toBeEnabled());
    expect(screen.queryByTestId("mail-draft-newer-version")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Text")).toHaveValue("Sehr geehrte Damen und Herren, Danke.");
  });
});
