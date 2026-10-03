import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { SuggestionCard } from "./SuggestionCard";
import type { Message } from "./MailWorkspace";

vi.mock("@/components/lexoffice/LexofficeInvoiceCopyChip", () => ({ LexofficeInvoiceCopyChip: () => null }));
vi.mock("@/components/tickets/TicketProcessBadge", () => ({ TicketProcessBadge: ({ code }: { code: string }) => <span>{`proc:${code}`}</span> }));

const m = messages.Mail.suggestion;

function message(over: Record<string, unknown> = {}, status = "ready"): Message {
  return {
    id: "mmmmmmmm-1111-4111-8111-111111111111",
    ticket_id: null,
    suggestion_status: status,
    classification: {},
    suggestion: { category: "Reparatur", urgency: "high", summary: "Heizung defekt", reply_draft: "Guten Tag", playbook_id: "pb-1", playbook_score: 0.83, ...over },
  } as unknown as Message;
}

describe("SuggestionCard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the proposal and creates a reply draft only on explicit action", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ id: "draft" }));
    const onDraft = vi.fn();
    renderIntl(<SuggestionCard message={message()} onUpdated={vi.fn()} onDraftCreated={onDraft} />);
    expect(screen.getByText("Heizung defekt")).toBeInTheDocument();
    expect(screen.getByText(/Übereinstimmung 83%/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: m.sendReplyDraft }));
    await screen.findByRole("button", { name: m.sendReplyDraft });
    expect(onDraft).toHaveBeenCalledWith({ id: "draft" });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("/api/bff/mail/messages/mmmmmmmm-1111-4111-8111-111111111111/reply-draft");
    expect(JSON.parse(String(init?.body))).toEqual({ body: "Guten Tag" });
  });

  it("shows the API refusal when applying the playbook fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Verboten", status: 403, detail: "Keine Berechtigung" }, 403));
    const onDraft = vi.fn();
    renderIntl(<SuggestionCard message={message()} onUpdated={vi.fn()} onDraftCreated={onDraft} />);
    await userEvent.click(screen.getByRole("button", { name: m.applyPlaybook }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Keine Berechtigung");
    expect(onDraft).not.toHaveBeenCalled();
  });

  it("records playbook feedback and applies the process to the ticket", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input).endsWith("/apply-process") ? jsonResponse({ ticket_id: "t-1", number: 42, applied: true }) : jsonResponse({}),
    );
    const onUpdated = vi.fn();
    renderIntl(<SuggestionCard message={message({ process_code: "heating_failure" })} onUpdated={onUpdated} onDraftCreated={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: m.playbookHelpful }));
    expect(await screen.findByText(m.feedbackSaved)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: m.playbookHelpful })).toHaveAttribute("aria-pressed", "true");
    expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({ helpful: true });
    await userEvent.click(screen.getByRole("button", { name: m.applyProcess }));
    expect(await screen.findByText("Flow auf Ticket 42 angewendet.")).toBeInTheDocument();
    expect(onUpdated).toHaveBeenCalledWith(expect.objectContaining({ ticket_id: "t-1" }));
  });

  it("shows only the status text without a ready proposal", () => {
    renderIntl(<SuggestionCard message={message({ reason: "Kein Text" }, "skipped")} onUpdated={vi.fn()} onDraftCreated={vi.fn()} />);
    expect(screen.getByText("Kein Vorschlag: Kein Text")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: m.sendReplyDraft })).not.toBeInTheDocument();
  });
});
