import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketProposals } from "./TicketProposals";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const TICKET = "0192abcd-0000-7000-8000-000000000001";
const PROPOSAL = "0192abcd-0000-7000-8000-000000000002";
const CONTACT = "0192abcd-0000-7000-8000-000000000003";

function proposal(decision: "pending" | "accepted" = "pending") {
  return {
    id: PROPOSAL,
    ticket_id: TICKET,
    decision,
    proposed: {
      title: "Stammdatenänderung: Kontakt Jacqueline Kampmeier ändern zu Jacqueline Müller",
      contact_id: CONTACT,
      contact_display_name: "Kampmeier, Jacqueline",
      matched_by: "sender_email",
      candidates: [],
      changes: [{ field: "last_name", old: "Kampmeier", new: "Müller", confidence: 0.95 }],
      bank_change_mentioned: false,
      bank_hint: null,
      reason: "Hochzeit",
      reply_draft: { subject: "AW: Namensänderung", body: "Hallo Frau Müller,\n\nvielen Dank. Wir haben unsere Stammdaten soeben korrigiert." },
      source: { ai: "used" },
    },
    final: decision === "accepted" ? { changes: [{ field: "last_name", old: "Kampmeier", new: "Müller" }] } : null,
    contact: {
      id: CONTACT,
      display_name: decision === "accepted" ? "Müller, Jacqueline" : "Kampmeier, Jacqueline",
      salutation: "Frau",
      title: null,
      first_name: "Jacqueline",
      last_name: decision === "accepted" ? "Müller" : "Kampmeier",
      company_name: null,
      street: null,
      house_number: null,
      postal_code: null,
      city: null,
      phone: null,
      email: "j@example.org",
    },
    reply_message_id: null,
    reply_message_status: null,
  };
}

function mockApi(calls: { url: string; method: string; body: string | null }[]) {
  let state: "pending" | "accepted" = "pending";
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: typeof init?.body === "string" ? init.body : null });
    if (url === `/api/bff/tickets/${TICKET}/proposals`) return jsonResponse([proposal(state)]);
    if (url.endsWith("/accept") || url.endsWith("/correct")) {
      state = "accepted";
      return jsonResponse(proposal(state));
    }
    if (url.endsWith("/reply-draft")) return jsonResponse({ id: "m1", status: "draft" }, 201);
    if (url.endsWith("/submit")) return jsonResponse({ id: "m1", status: "pending" });
    return jsonResponse({ title: "Fehler" }, 404);
  });
}

afterEach(() => vi.restoreAllMocks());

test("shows the diff and accepts the proposal, then submits the reply through the mail path", async () => {
  const calls: { url: string; method: string; body: string | null }[] = [];
  mockApi(calls);
  renderIntl(<TicketProposals ticketId={TICKET} />);
  await screen.findByText(/Kontakt Jacqueline Kampmeier ändern zu Jacqueline Müller/);
  expect(screen.getByText("Kampmeier")).toBeInTheDocument();
  expect(screen.getByText("Müller")).toBeInTheDocument();
  expect(screen.getByText("Nachname")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Akzeptieren" }));
  await waitFor(() => expect(calls.some((c) => c.url.endsWith(`/proposals/${PROPOSAL}/accept`) && c.method === "POST")).toBe(true));
  expect(refresh).toHaveBeenCalled();
  await screen.findByTestId("reply-draft");
  expect(screen.getByText(/Hallo Frau Müller/)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Senden" }));
  await waitFor(() => expect(calls.some((c) => c.url.endsWith("/reply-draft") && c.method === "POST")).toBe(true));
  expect(calls.some((c) => c.url === "/api/bff/mail/messages/m1/submit" && c.method === "POST")).toBe(true);
  await screen.findByText(/zur Freigabe eingereicht/);
});

test("correct sends the edited final values", async () => {
  const calls: { url: string; method: string; body: string | null }[] = [];
  mockApi(calls);
  renderIntl(<TicketProposals ticketId={TICKET} />);
  await screen.findByRole("button", { name: "Korrigieren" });
  await userEvent.click(screen.getByRole("button", { name: "Korrigieren" }));
  const input = screen.getByLabelText("Neu Nachname");
  await userEvent.clear(input);
  await userEvent.type(input, "Mueller");
  await userEvent.click(screen.getByRole("button", { name: "Übernehmen" }));
  await waitFor(() => expect(calls.some((c) => c.url.endsWith("/correct"))).toBe(true));
  const sent = calls.find((c) => c.url.endsWith("/correct"));
  expect(JSON.parse(sent?.body ?? "{}")).toEqual({
    contact_id: CONTACT,
    changes: [{ field: "last_name", old: "Kampmeier", new: "Mueller" }],
  });
});

test("reject posts the reason and never touches the contact endpoints", async () => {
  const calls: { url: string; method: string; body: string | null }[] = [];
  mockApi(calls);
  renderIntl(<TicketProposals ticketId={TICKET} />);
  await screen.findByRole("button", { name: "Ablehnen" });
  await userEvent.type(screen.getByPlaceholderText("Grund der Ablehnung (optional)"), "falsch");
  await userEvent.click(screen.getByRole("button", { name: "Ablehnen" }));
  await waitFor(() => expect(calls.some((c) => c.url.endsWith("/reject"))).toBe(true));
  expect(JSON.parse(calls.find((c) => c.url.endsWith("/reject"))?.body ?? "{}")).toEqual({ reason: "falsch" });
  expect(calls.some((c) => c.url.includes("/contacts/"))).toBe(false);
});
