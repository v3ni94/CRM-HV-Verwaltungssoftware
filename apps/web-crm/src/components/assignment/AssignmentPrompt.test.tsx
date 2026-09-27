import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AssignmentPrompt, type AssignmentReview } from "./AssignmentPrompt";

const CONTACT = "0192abcd-0000-7000-8000-000000000001";
const OTHER = "0192abcd-0000-7000-8000-000000000002";
const MSG = "0192abcd-0000-7000-8000-000000000010";

function review(over: Partial<AssignmentReview>): AssignmentReview {
  return {
    id: "r-1",
    entity_type: "message",
    entity_id: MSG,
    dimension: "contact",
    status: "open",
    candidates: [
      { id: CONTACT, label: "Max Mustermann", detail: "Mieter, Objekt 012", confidence: 0.7, reasons: ["Vor- und Nachname im Text"] },
    ],
    chosen_id: null,
    reason: null,
    decision: null,
    ...over,
  };
}

describe("AssignmentPrompt", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders nothing when no question is open", () => {
    const { container } = renderIntl(
      <AssignmentPrompt entityType="message" entityId={MSG} canDecide={true} initialReviews={[review({ status: "auto", chosen_id: CONTACT })]} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("asks the question and accepts with Ja", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      expect(String(input)).toBe(`/api/bff/mail/messages/${MSG}/assignment-review/decide`);
      expect(JSON.parse(String(init?.body))).toEqual({ dimension: "contact", decision: "accept", candidate_id: null });
      return jsonResponse([review({ status: "accepted", chosen_id: CONTACT, decision: "accept" })]);
    });
    const onDecided = vi.fn();
    renderIntl(<AssignmentPrompt entityType="message" entityId={MSG} canDecide={true} initialReviews={[review({})]} onDecided={onDecided} />);
    expect(screen.getByText("Handelt es sich um den Kontakt Max Mustermann (Mieter, Objekt 012)?")).toBeInTheDocument();
    expect(screen.getByText("Konfidenz 70 %, Vor- und Nachname im Text")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ja" }));
    await waitFor(() => expect(onDecided).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("assignment-prompt")).not.toBeInTheDocument();
  });

  it("rejects with Nein, searches and applies a manual pick", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push(url);
      if (url.endsWith("/decide") && JSON.parse(String(init?.body)).decision === "reject") {
        return jsonResponse([review({ status: "rejected", decision: "reject" })]);
      }
      if (url.startsWith("/api/bff/contacts?q=Erna")) {
        return jsonResponse({ items: [{ id: OTHER, display_name: "Erna Beispiel" }] });
      }
      if (url.endsWith("/decide")) {
        expect(JSON.parse(String(init?.body))).toEqual({ dimension: "contact", decision: "accept", candidate_id: OTHER });
        return jsonResponse([review({ status: "accepted", chosen_id: OTHER, decision: "manual" })]);
      }
      throw new Error(`unexpected ${url}`);
    });
    renderIntl(<AssignmentPrompt entityType="ticket" entityId={MSG} canDecide={true} initialReviews={[review({ entity_type: "ticket" })]} />);
    await userEvent.click(screen.getByRole("button", { name: "Nein" }));
    expect(await screen.findByText("Vorschlag verworfen. Kontakt suchen und zuordnen:")).toBeInTheDocument();
    expect(calls[0]).toBe(`/api/bff/tickets/${MSG}/assignment-review/decide`);
    await userEvent.type(screen.getByLabelText("Suchbegriff"), "Erna");
    await userEvent.click(screen.getByRole("button", { name: "Suchen" }));
    expect(await screen.findByText("Erna Beispiel")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Übernehmen" }));
    await waitFor(() => expect(screen.queryByTestId("assignment-prompt")).not.toBeInTheDocument());
  });

  it("lists several candidates and hides the buttons without permission", () => {
    const many = review({
      dimension: "property",
      candidates: [
        { id: CONTACT, label: "012 Musterhaus", detail: "Musterstraße 5", confidence: 0.6, reasons: ["Straße Musterstraße im Text"] },
        { id: OTHER, label: "013 Anderes Haus", detail: null, confidence: 0.5, reasons: [] },
      ],
    });
    renderIntl(<AssignmentPrompt entityType="message" entityId={MSG} canDecide={false} initialReviews={[many]} />);
    expect(screen.getByText("Mehrere Verwaltungsobjekte kommen in Frage. Welches ist gemeint?")).toBeInTheDocument();
    expect(screen.getByText("012 Musterhaus")).toBeInTheDocument();
    expect(screen.getByText("013 Anderes Haus")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Übernehmen" })).not.toBeInTheDocument();
    expect(screen.getByText("Zur Entscheidung fehlt die Berechtigung.")).toBeInTheDocument();
  });

  it("loads the reviews itself when none are given", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      expect(String(input)).toBe(`/api/bff/mail/messages/${MSG}/assignment-review`);
      return jsonResponse([review({})]);
    });
    renderIntl(<AssignmentPrompt entityType="message" entityId={MSG} canDecide={true} />);
    expect(await screen.findByTestId("assignment-prompt-contact")).toBeInTheDocument();
  });
});
