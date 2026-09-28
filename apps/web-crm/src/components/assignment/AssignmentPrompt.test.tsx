import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { IntlTestProvider, jsonResponse, renderIntl } from "@/test/intl";

import { AssignmentPrompt, type AssignmentReview } from "./AssignmentPrompt";

const CONTACT = "0192abcd-0000-7000-8000-000000000001";
const OTHER = "0192abcd-0000-7000-8000-000000000002";
const MSG = "0192abcd-0000-7000-8000-000000000010";
const NEXT = "0192abcd-0000-7000-8000-000000000011";
const ERIKA = "0192abcd-0000-7000-8000-000000000003";

function withIntl(ui: React.ReactElement) {
  return (
    <IntlTestProvider>
      {ui}
    </IntlTestProvider>
  );
}

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
      expect(JSON.parse(String(init?.body))).toEqual({ dimension: "contact", decision: "accept", candidate_id: CONTACT, seen_value: null });
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
        expect(JSON.parse(String(init?.body))).toEqual({ dimension: "contact", decision: "accept", candidate_id: OTHER, seen_value: null });
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

  it("starts empty for the next mail and ignores a late answer for the previous one (review 1.36.0)", async () => {
    let answerFirst: (() => void) | null = null;
    const decided: { url: string; body: unknown }[] = [];
    const nextReview = review({
      id: "r-2",
      entity_id: NEXT,
      candidates: [{ id: ERIKA, label: "Erika Beispiel", detail: "Eigentümerin", confidence: 0.8, reasons: [] }],
    });
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === `/api/bff/mail/messages/${MSG}/assignment-review`) {
        return new Promise<Response>((resolve) => {
          answerFirst = () => resolve(jsonResponse([review({})]));
        });
      }
      if (url === `/api/bff/mail/messages/${NEXT}/assignment-review`) return jsonResponse([nextReview]);
      if (url.endsWith("/decide")) {
        decided.push({ url, body: JSON.parse(String(init?.body)) });
        return jsonResponse([{ ...nextReview, status: "accepted", chosen_id: ERIKA, decision: "accept" }]);
      }
      throw new Error(`unexpected ${url}`);
    });
    const { rerender } = renderIntl(<AssignmentPrompt entityType="message" entityId={MSG} canDecide={true} />);
    rerender(withIntl(<AssignmentPrompt entityType="message" entityId={NEXT} canDecide={true} />));
    expect(await screen.findByText("Handelt es sich um den Kontakt Erika Beispiel (Eigentümerin)?")).toBeInTheDocument();

    // The slow first view of the previous mail answers now and must not replace the question.
    await act(async () => {
      answerFirst?.();
      await Promise.resolve();
    });
    expect(screen.queryByText(/Max Mustermann/)).not.toBeInTheDocument();
    expect(screen.getByText("Handelt es sich um den Kontakt Erika Beispiel (Eigentümerin)?")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Ja" }));
    await waitFor(() => expect(decided).toHaveLength(1));
    expect(decided[0]?.url).toBe(`/api/bff/mail/messages/${NEXT}/assignment-review/decide`);
  });

  it("drops the previous mail's question, search and hits while the next mail loads (review 1.36.0)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === `/api/bff/mail/messages/${MSG}/assignment-review`) return jsonResponse([review({})]);
      if (url === `/api/bff/mail/messages/${NEXT}/assignment-review`) return new Promise<Response>(() => {});
      if (url.endsWith("/decide") && JSON.parse(String(init?.body)).decision === "reject") {
        return jsonResponse([review({ status: "rejected", decision: "reject" })]);
      }
      if (url.startsWith("/api/bff/contacts?q=Erna")) return jsonResponse({ items: [{ id: OTHER, display_name: "Erna Beispiel" }] });
      throw new Error(`unexpected ${url}`);
    });
    const { rerender } = renderIntl(<AssignmentPrompt entityType="message" entityId={MSG} canDecide={true} />);
    await userEvent.click(await screen.findByRole("button", { name: "Nein" }));
    await userEvent.type(await screen.findByLabelText("Suchbegriff"), "Erna");
    await userEvent.click(screen.getByRole("button", { name: "Suchen" }));
    expect(await screen.findByText("Erna Beispiel")).toBeInTheDocument();

    rerender(withIntl(<AssignmentPrompt entityType="message" entityId={NEXT} canDecide={true} />));
    expect(screen.queryByTestId("assignment-prompt")).not.toBeInTheDocument();
    expect(screen.queryByText("Erna Beispiel")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Übernehmen" })).not.toBeInTheDocument();
  });

  it("sends the value shown with the question as seen_value (review 1.36.0)", async () => {
    const bodies: unknown[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      bodies.push(JSON.parse(String(init?.body)));
      return jsonResponse([review({ status: "accepted", chosen_id: OTHER, decision: "accept" })]);
    });
    const shown = review({
      chosen_id: CONTACT,
      candidates: [{ id: OTHER, label: "Erna Beispiel", detail: null, confidence: 0.7, reasons: [] }],
    });
    renderIntl(<AssignmentPrompt entityType="ticket" entityId={MSG} canDecide={true} initialReviews={[shown]} />);
    await userEvent.click(screen.getByRole("button", { name: "Ja" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toEqual({ dimension: "contact", decision: "accept", candidate_id: OTHER, seen_value: CONTACT });
  });

  it("reloads the review and shows the German detail on 409 (review 1.36.0)", async () => {
    const DETAIL = "Die Zuordnung wurde inzwischen anders gesetzt. Die Rückfrage ist überholt, bitte neu laden.";
    const calls: string[] = [];
    const onDecided = vi.fn();
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      if (url.endsWith("/decide")) {
        return jsonResponse({ type: "about:blank", title: "Zuordnung inzwischen geändert", status: 409, detail: DETAIL, code: "MHVP-COMM-0003" }, 409);
      }
      if (url === `/api/bff/mail/messages/${MSG}/assignment-review`) {
        return jsonResponse([review({ status: "superseded", chosen_id: OTHER, reason: "Inzwischen anders zugeordnet" })]);
      }
      throw new Error(`unexpected ${url}`);
    });
    renderIntl(<AssignmentPrompt entityType="message" entityId={MSG} canDecide={true} initialReviews={[review({})]} onDecided={onDecided} />);
    await userEvent.click(screen.getByRole("button", { name: "Ja" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(DETAIL);
    await waitFor(() => expect(calls).toEqual([`/api/bff/mail/messages/${MSG}/assignment-review/decide`, `/api/bff/mail/messages/${MSG}/assignment-review`]));
    expect(screen.queryByRole("button", { name: "Ja" })).not.toBeInTheDocument();
    expect(onDecided).not.toHaveBeenCalled();
  });

  it("asks no question for a superseded row (review 1.36.0)", () => {
    const rows: AssignmentReview[] = [review({ status: "superseded", chosen_id: OTHER, reason: "Inzwischen anders zugeordnet" })];
    const { container } = renderIntl(<AssignmentPrompt entityType="message" entityId={MSG} canDecide={true} initialReviews={rows} />);
    expect(container).toBeEmptyDOMElement();
  });
});
