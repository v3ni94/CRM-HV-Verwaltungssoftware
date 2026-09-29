import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { LetterRecordForm } from "./LetterRecordForm";

const PROPERTY = "01920000-0000-7000-8000-0000000000a1";
const CONTACT = "01920000-0000-7000-8000-0000000000c1";
const DOCUMENT = "01920000-0000-7000-8000-0000000000d1";

describe("LetterRecordForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("files the letter with recipient, ticket and postal dispatch record", async () => {
    const calls: { url: string; method: string; body: unknown }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (url.startsWith("/api/bff/contacts?")) return jsonResponse({ items: [{ id: CONTACT, display_name: "Vorverwaltung GmbH" }] });
      if (url.startsWith("/api/bff/tickets?")) return jsonResponse([{ id: "t1", number: 42, title: "Übernahme" }]);
      return jsonResponse({ document_id: DOCUMENT, title: "Nachforderungsschreiben 811", dispatch: { channel: "post", status: "sent" } }, 201);
    });
    renderIntl(
      <LetterRecordForm path={`objektakte/properties/${PROPERTY}/completeness/nachforderungsschreiben/pdf`} recipient={{ kind: "search" }} canCreate requiredPermission="documents:create" />,
    );
    await userEvent.type(screen.getByTestId("letter-recipient-search"), "Vor");
    await userEvent.click(await screen.findByText("Vorverwaltung GmbH"));
    expect(screen.getByTestId("letter-recipient")).toHaveTextContent("Vorverwaltung GmbH");
    await userEvent.type(screen.getByTestId("letter-ticket-search"), "Üb");
    await userEvent.click(await screen.findByText("#42 Übernahme"));
    await userEvent.type(screen.getByTestId("letter-date"), "2026-09-29");
    await userEvent.selectOptions(screen.getByTestId("letter-channel"), "post");
    await userEvent.type(screen.getByTestId("letter-sent-on"), "2026-09-30");
    await userEvent.type(screen.getByTestId("letter-evidence-ref"), "RR 1234");
    await userEvent.click(screen.getByTestId("letter-create"));
    await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toBe(`/api/bff/objektakte/properties/${PROPERTY}/completeness/nachforderungsschreiben/pdf`);
    expect(post?.body).toEqual({
      contact_id: CONTACT,
      letter_date: "2026-09-29",
      ticket_id: "t1",
      dispatch: { channel: "post", sent_on: "2026-09-30", evidence_kind: null, evidence_ref: "RR 1234" },
    });
    expect(await screen.findByTestId("letter-result")).toHaveTextContent("Abgelegt: Nachforderungsschreiben 811");
    expect(screen.getByTestId("letter-result")).toHaveTextContent("Versand erfasst: Post, Status sent");
    expect(screen.getByText("Dokument öffnen")).toHaveAttribute("href", `/dokumente/${DOCUMENT}`);
  });

  it("requires a recipient, hides the portal channel when locked and shows the permission hint", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<LetterRecordForm path="letting/rent-increases/x/letter/pdf" recipient={{ kind: "search" }} portalLocked canCreate requiredPermission="contracts:approve" />);
    expect(screen.queryByRole("option", { name: "Portal" })).not.toBeInTheDocument();
    expect(screen.getByText("Portalzustellung erst mit Freigabestufe G3.")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("letter-create"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte einen Empfänger wählen.");
    expect(fetchMock).not.toHaveBeenCalled();
    renderIntl(<LetterRecordForm path="x" recipient={{ kind: "fixed", label: "Hauptkontakt" }} canCreate={false} requiredPermission="contracts:approve" />);
    expect(screen.getByText("Zum Ablegen fehlt das Recht contracts:approve.")).toBeInTheDocument();
  });

  it("sends the fixed recipient without contact id and reports the API problem", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ title: "Freigabestufe", status: 403, detail: "Freigabestufe G3 ist nicht erteilt." }, 403));
    renderIntl(<LetterRecordForm path="letting/rent-increases/x/letter/pdf" recipient={{ kind: "fixed", label: "Hauptkontakt der Mietpartei" }} portalLocked canCreate requiredPermission="contracts:approve" />);
    expect(screen.getByText("Hauptkontakt der Mietpartei")).toBeInTheDocument();
    await userEvent.click(screen.getByTestId("letter-create"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({});
    expect(await screen.findByRole("alert")).toHaveTextContent("G3");
  });
});
