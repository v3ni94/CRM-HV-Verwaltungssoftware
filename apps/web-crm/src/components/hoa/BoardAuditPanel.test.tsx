import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { BoardAuditPanel, type BoardSection } from "./BoardAuditPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));
const AUDIT = "0192abcd-0000-7000-8000-000000000090";
const CONTACT = "0192abcd-0000-7000-8000-000000000091";
const NOTE = "0192abcd-0000-7000-8000-000000000092";

const section: BoardSection = {
  engagement_id: AUDIT,
  auditor_contact_ids: [CONTACT],
  access: [],
  notes: [
    {
      id: NOTE,
      audit_item_id: "i1",
      cost_item_id: null,
      kind: "question",
      text: "Warum ohne Angebot?",
      answer: null,
      created_at: "2026-09-01T00:00:00Z",
      answered_at: null,
    },
  ],
};

describe("BoardAuditPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates the board access with e-mail and shows the one time invitation token", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ id: "a1", account_id: "acc", contact_id: CONTACT, invitation_token: "tok.secret" }, 201));
    renderIntl(
      <BoardAuditPanel auditId={AUDIT} section={section} items={[{ id: "i1", label: "Position 1" }]} contactNames={{ [CONTACT]: "Erika Beirat" }} />,
    );
    await userEvent.type(screen.getByLabelText("E-Mail (nur für neuen Portalzugang)"), "erika@example.org");
    await userEvent.type(screen.getByLabelText("Anzeigename (nur für neuen Portalzugang)"), "Erika Beirat");
    await userEvent.click(screen.getByRole("button", { name: "Beiratszugang anlegen" }));
    await waitFor(() => expect(screen.getByText("tok.secret")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/hoa/audit-engagements/${AUDIT}/board-access`);
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({
      contact_id: CONTACT,
      email: "erika@example.org",
      display_name: "Erika Beirat",
    });
    expect(refresh).toHaveBeenCalled();
  });

  it("answers a board question", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ id: NOTE, kind: "answered", answer: "Unter der Wertgrenze." }));
    renderIntl(
      <BoardAuditPanel auditId={AUDIT} section={section} items={[{ id: "i1", label: "Position 1" }]} contactNames={{}} />,
    );
    expect(screen.getByText("Warum ohne Angebot?")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Antwort der Verwaltung"), "Unter der Wertgrenze.");
    await userEvent.click(screen.getByRole("button", { name: "Antwort senden" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/hoa/audit-engagements/${AUDIT}/notes/${NOTE}/answer`);
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ answer: "Unter der Wertgrenze." });
  });

  it("formats the dates itself and confirms an answer (review 26.09.2026)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: "n1" }));
    renderIntl(<BoardAuditPanel auditId={AUDIT} section={section} items={[]} contactNames={{}} />);
    expect(screen.getByText("01.09.2026")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Antwort der Verwaltung"), "Beleg liegt in der Akte.");
    await userEvent.click(screen.getByRole("button", { name: "Antwort senden" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Gespeichert.");
  });
});
