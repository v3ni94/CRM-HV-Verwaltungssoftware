import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { SchadenstoolPanel } from "./SchadenstoolPanel";

const TICKET = "01920000-0000-7000-8000-000000000042";
const BASE = `/api/bff/integrations/schadenstool/tickets/${TICKET}`;

describe("SchadenstoolPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing when the connection is off and the ticket is not linked", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ enabled: false, linked: false }, 200));
    const { container } = renderIntl(<SchadenstoolPanel ticketId={TICKET} canUpdate />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("hands the ticket over with the form data only", async () => {
    let linked = false;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "POST") {
        linked = true;
        return jsonResponse({ queued: true, link_id: "l1" }, 202);
      }
      return jsonResponse(
        linked
          ? { enabled: true, linked: true, sync_status: "pending_create", remote_status_label: null, pending: 1, failed: 0, items: [], documents: [] }
          : { enabled: true, linked: false },
        200,
      );
    });
    renderIntl(<SchadenstoolPanel ticketId={TICKET} canUpdate />);
    await userEvent.type(await screen.findByLabelText("Meldende Person"), "Herr Melder");
    await userEvent.type(screen.getByLabelText("Schadenart"), "Leitungswasser");
    await userEvent.click(screen.getByRole("button", { name: "An Schadenbearbeiter übergeben" }));
    await waitFor(() => expect(screen.getByText("Übergabe ist eingeplant.")).toBeInTheDocument());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(String(post?.[0])).toBe(`${BASE}/handover`);
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ reporter: "Herr Melder", damage_type: "Leitungswasser" });
    expect(screen.getByText("Übergabe läuft")).toBeInTheDocument();
  });

  it("shows remote status, inbound items, token errors and sends a chosen comment and document", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      if (init?.method === "POST") return jsonResponse({ queued: true, link_id: "l1" }, 202);
      return jsonResponse(
        {
          enabled: true,
          linked: true,
          remote_status: "gutachten",
          remote_status_label: "gutachten",
          sync_status: "linked",
          last_synced_at: "2026-09-28T10:00:00Z",
          last_error: null,
          token_invalid: true,
          pending: 0,
          failed: 0,
          items: [
            { id: "i1", kind: "comment", direction: "inbound", local_id: "c1", remote_id: "r1", author_name: "Frau Gutachter", state: "received", last_error: null, created_at: "2026-09-28T10:00:00Z" },
          ],
          documents: [
            { id: "01920000-0000-7000-8000-0000000000d1", filename: "foto.pdf", sent: false },
            { id: "01920000-0000-7000-8000-0000000000d2", filename: "alt.pdf", sent: true },
          ],
        },
        200,
      );
    });
    renderIntl(<SchadenstoolPanel ticketId={TICKET} canUpdate />);
    expect(await screen.findByText("gutachten")).toBeInTheDocument();
    expect(screen.getByText(/Kommentar von Frau Gutachter/)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Token ungültig.");
    await userEvent.type(screen.getByLabelText("Kommentar an Schadenbearbeiter senden"), "Bitte Termin");
    await userEvent.click(screen.getByRole("button", { name: "Kommentar senden" }));
    await waitFor(() => expect(screen.getByText("Kommentar ist eingeplant.")).toBeInTheDocument());
    expect(screen.getByRole("option", { name: "alt.pdf (bereits gesendet)" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Dokument an Schadenbearbeiter senden"), "01920000-0000-7000-8000-0000000000d1");
    await userEvent.click(screen.getByRole("button", { name: "Dokument senden" }));
    await waitFor(() => expect(screen.getByText("Dokument ist eingeplant.")).toBeInTheDocument());
    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts.map(([input]) => String(input))).toEqual([`${BASE}/comments`, `${BASE}/attachments`]);
    expect(JSON.parse(String(posts[0]?.[1]?.body))).toEqual({ body: "Bitte Termin" });
    expect(JSON.parse(String(posts[1]?.[1]?.body))).toEqual({ document_id: "01920000-0000-7000-8000-0000000000d1" });
  });
});
