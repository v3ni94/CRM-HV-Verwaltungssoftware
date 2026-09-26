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

test("address proposal: accept shows the reply draft with the new address and its date", async () => {
  // Ersatz für einen Playwright-Rauchtest: die e2e-Infrastruktur kann ohne Objektspeicher keine
  // eingehende E-Mail (Dokument, Ingest) anlegen, daher läuft der Akzeptieren-Fluss hier gegen
  // eine nachgestellte API (gleiche Endpunkte und Antwortformen wie das Backend).
  const ADDRESS_PROPOSAL = "0192abcd-0000-7000-8000-000000000004";
  const changes = [
    { field: "street", old: null, new: "Lindenallee", confidence: 0.6 },
    { field: "house_number", old: null, new: "7a", confidence: 0.6 },
    { field: "postal_code", old: null, new: "50667", confidence: 0.7 },
    { field: "city", old: null, new: "Köln", confidence: 0.6 },
  ];
  const body =
    "Guten Tag Tobias Brandt,\n\nvielen Dank. Ihre neue Anschrift Lindenallee 7a, 50667 Köln haben wir ab dem 01.10.2026 in unseren Stammdaten hinterlegt.\n\nMit freundlichen Grüßen\n[Name]\n[Firma]";
  const row = (decision: "pending" | "accepted") => ({
    id: ADDRESS_PROPOSAL,
    ticket_id: TICKET,
    decision,
    proposed: {
      title: "Stammdatenänderung: Kontakt Tobias Brandt, Straße, Hausnummer, PLZ, Ort",
      contact_id: CONTACT,
      contact_display_name: "Brandt, Tobias",
      matched_by: "sender_email",
      candidates: [],
      changes,
      bank_change_mentioned: false,
      bank_hint: null,
      reason: null,
      address_valid_from: "2026-10-01",
      mail_salutation: null,
      reply_draft: { subject: "AW: Neue Adresse ab 01.10.2026", body },
      source: { ai: "skipped" },
    },
    final: decision === "accepted" ? { changes: changes.map(({ field, old, new: value }) => ({ field, old, new: value })) } : null,
    contact: {
      id: CONTACT,
      display_name: "Brandt, Tobias",
      salutation: null,
      title: null,
      first_name: "Tobias",
      last_name: "Brandt",
      company_name: null,
      street: decision === "accepted" ? "Lindenallee" : "Altweg",
      house_number: decision === "accepted" ? "7a" : "1",
      postal_code: decision === "accepted" ? "50667" : "40789",
      city: decision === "accepted" ? "Köln" : "Monheim am Rhein",
      phone: null,
      email: "t.brandt@example.org",
    },
    reply_message_id: null,
    reply_message_status: null,
  });
  let state: "pending" | "accepted" = "pending";
  const calls: string[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    calls.push(`${init?.method ?? "GET"} ${url}`);
    if (url === `/api/bff/tickets/${TICKET}/proposals`) return jsonResponse([row(state)]);
    if (url.endsWith(`/proposals/${ADDRESS_PROPOSAL}/accept`)) {
      state = "accepted";
      return jsonResponse(row(state));
    }
    return jsonResponse({ title: "Fehler" }, 404);
  });

  renderIntl(<TicketProposals ticketId={TICKET} />);
  const card = await screen.findByTestId("ticket-proposal");
  expect(card).toHaveTextContent("Straße, Hausnummer, PLZ, Ort");
  expect(screen.getByText("Altweg")).toBeInTheDocument();
  expect(screen.getByText("Lindenallee")).toBeInTheDocument();
  expect(screen.queryByTestId("reply-draft")).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Akzeptieren" }));
  await waitFor(() => expect(calls).toContain(`POST /api/bff/tickets/${TICKET}/proposals/${ADDRESS_PROPOSAL}/accept`));
  const reply = await screen.findByTestId("reply-draft");
  expect(reply).toHaveTextContent("AW: Neue Adresse ab 01.10.2026");
  expect(reply).toHaveTextContent("Guten Tag Tobias Brandt,");
  expect(reply).toHaveTextContent("Lindenallee 7a, 50667 Köln haben wir ab dem 01.10.2026");
  expect(screen.getByText("Akzeptiert")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Akzeptieren" })).not.toBeInTheDocument();
});
