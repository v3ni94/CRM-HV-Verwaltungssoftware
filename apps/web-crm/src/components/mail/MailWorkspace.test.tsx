import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MailWorkspace } from "./MailWorkspace";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

describe("MailWorkspace Erledigte anzeigen", () => {
  let fetchMock: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    window.history.replaceState(null, "", "/mail");
    fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
  });
  afterEach(() => vi.restoreAllMocks());

  const messageUrls = () =>
    fetchMock.mock.calls.map((c: unknown[]) => String(c[0])).filter((u: string) => u.includes("/mail/messages?"));

  it("hides done mails by default and requests include_closed when switched on", async () => {
    renderIntl(<MailWorkspace canApprove={false} canReadMembers={false} />);
    await waitFor(() => expect(messageUrls().length).toBeGreaterThan(0));
    expect(messageUrls().every((u: string) => !u.includes("include_closed"))).toBe(true);

    await userEvent.click(screen.getByLabelText("Erledigte anzeigen"));
    await waitFor(() => expect(messageUrls().at(-1)).toContain("include_closed=true"));
    expect(window.location.search).toContain("erledigt=1");
  });

  it("shows the archive permission banner with a link to the mailbox settings", async () => {
    fetchMock.mockImplementation(async (input: unknown) => {
      if (String(input).endsWith("/api/bff/mail/mailboxes")) {
        return jsonResponse([
          { id: "m1", address: "info@example.com", archive_scope_missing: true },
          { id: "m2", address: "buchhaltung@example.com", archive_scope_missing: false },
        ]);
      }
      return jsonResponse([]);
    });
    renderIntl(<MailWorkspace canApprove={false} canReadMembers={false} />);
    await waitFor(() => expect(screen.getByTestId("archive-scope-banner")).toBeInTheDocument());
    const banner = screen.getByTestId("archive-scope-banner");
    expect(banner.textContent).toContain("info@example.com");
    expect(banner.textContent).not.toContain("buchhaltung@example.com");
    expect(screen.getByRole("link", { name: "Postfach neu verbinden" })).toHaveAttribute("href", "/einstellungen/postfaecher");
  });
});

describe("MailWorkspace Reiter per URL (?tab=)", () => {
  let fetchMock: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
  });
  afterEach(() => vi.restoreAllMocks());

  it("preselects the tab named in ?tab= on load", async () => {
    window.history.replaceState(null, "", "/mail?tab=drafts");
    renderIntl(<MailWorkspace canApprove={false} canReadMembers={false} />);
    await waitFor(() => expect(screen.getByRole("tab", { name: "Entwürfe", selected: true })).toBeInTheDocument());
  });

  it("falls back to inbox for an unknown ?tab= value", async () => {
    window.history.replaceState(null, "", "/mail?tab=unbekannt");
    renderIntl(<MailWorkspace canApprove={false} canReadMembers={false} />);
    await waitFor(() => expect(screen.getByRole("tab", { name: "Posteingang", selected: true })).toBeInTheDocument());
  });

  it("writes the tab into the URL when the user switches tabs", async () => {
    window.history.replaceState(null, "", "/mail");
    renderIntl(<MailWorkspace canApprove={false} canReadMembers={false} />);
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(0));
    await userEvent.click(screen.getByRole("tab", { name: "Entwürfe" }));
    await waitFor(() => expect(window.location.search).toContain("tab=drafts"));
  });
});

describe("MailWorkspace Seitensteuerung (Betreibermeldung 27.09.2026)", () => {
  let fetchMock: ReturnType<typeof vi.spyOn>;

  const page = (label: number, count: number) =>
    Array.from({ length: count }, (_v, i) => ({
      id: `m${label}-${i}`,
      channel: "email",
      direction: "in",
      status: "new",
      from_address: `x${i}@example.com`,
      to_addresses: [],
      subject: `Seite ${label} Nachricht ${i}`,
      received_at: null,
      sent_at: null,
      contact_id: null,
      property_id: null,
      ticket_id: null,
      thread_id: null,
      document_id: null,
      attachment_document_ids: [],
      classification: {},
      appointment_suggestions: [],
      created_by: null,
      mailbox_id: null,
      submitted_by: null,
      submitted_at: null,
      approved_by: null,
      approved_at: null,
      rejection_note: null,
      suggestion: {},
      suggestion_status: "none",
    }));

  beforeEach(() => {
    window.history.replaceState(null, "", "/mail");
    fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input: unknown) => {
      const url = String(input);
      if (url.includes("/mail/messages?")) {
        const isPage2 = url.includes("page=2");
        return jsonResponse(isPage2 ? page(2, 5) : page(1, 50), 200, {
          "x-total-count": "55",
          "x-page": isPage2 ? "2" : "1",
          "x-page-size": "50",
        });
      }
      return jsonResponse([]);
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("requests page 2 and replaces the list when the user clicks Weiter", async () => {
    renderIntl(<MailWorkspace canApprove={false} canReadMembers={false} />);
    await waitFor(() => expect(screen.getByTestId("mail-pagination")).toBeInTheDocument());
    expect(screen.getByText("Seite 1 von 2")).toBeInTheDocument();
    expect(screen.getAllByText("Seite 1 Nachricht 0").length).toBeGreaterThan(0);

    await userEvent.click(screen.getByText("Weiter"));

    await waitFor(() => expect(screen.getByText("Seite 2 von 2")).toBeInTheDocument());
    expect(screen.getAllByText("Seite 2 Nachricht 0").length).toBeGreaterThan(0);
    expect(screen.queryAllByText("Seite 1 Nachricht 0").length).toBe(0);
    expect(window.location.search).toContain("seite=2");
    expect(
      fetchMock.mock.calls.map((c: unknown[]) => String(c[0])).some((u: string) => u.includes("page=2") && u.includes("page_size=50")),
    ).toBe(true);
  });

  it("resets to page 1 when a filter changes", async () => {
    renderIntl(<MailWorkspace canApprove={false} canReadMembers={false} />);
    await waitFor(() => expect(screen.getByTestId("mail-pagination")).toBeInTheDocument());
    await userEvent.click(screen.getByText("Weiter"));
    await waitFor(() => expect(window.location.search).toContain("seite=2"));

    await userEvent.click(screen.getByRole("tab", { name: "Entwürfe" }));

    await waitFor(() => expect(window.location.search).not.toContain("seite=2"));
  });
});

describe("MailWorkspace Antwortentwurf beim Wechsel der Mail (Review 1.36.0)", () => {
  const mail = (id: string, subject: string, extra: Record<string, unknown> = {}) => ({
    id,
    channel: "email",
    direction: "in",
    status: "new",
    from_address: `${id}@example.com`,
    to_addresses: [],
    subject,
    received_at: null,
    sent_at: null,
    contact_id: null,
    property_id: null,
    ticket_id: null,
    thread_id: null,
    document_id: null,
    attachment_document_ids: [],
    classification: {},
    appointment_suggestions: [],
    created_by: null,
    mailbox_id: null,
    submitted_by: null,
    submitted_at: null,
    approved_by: null,
    approved_at: null,
    rejection_note: null,
    suggestion: {},
    suggestion_status: "none",
    ...extra,
  });
  afterEach(() => vi.restoreAllMocks());

  it("keeps a late reply draft of the previous mail out of the next mail", async () => {
    window.history.replaceState(null, "", "/mail");
    const a = mail("a", "Heizung Mail A");
    const b = mail("b", "Wasser Mail B");
    let resolveDraft: ((r: Response) => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input: unknown, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/mail/messages?")) {
        return jsonResponse([a, b], 200, { "x-total-count": "2", "x-page": "1", "x-page-size": "50" });
      }
      if (url.endsWith("/mail/messages/a/reply-draft") && init?.method === "POST") {
        return new Promise<Response>((resolve) => {
          resolveDraft = resolve;
        });
      }
      // The detail call carries the full text (body), which shows the action bar.
      if (url.endsWith("/mail/messages/a")) return jsonResponse({ ...a, body: "Text A" });
      if (url.endsWith("/mail/messages/b")) return jsonResponse({ ...b, body: "Text B" });
      return jsonResponse([]);
    });
    renderIntl(<MailWorkspace canApprove={false} canReadMembers={false} />);
    await userEvent.click((await screen.findAllByText("Heizung Mail A"))[0]!);
    const toolbar = await screen.findByTestId("mail-actions-top");
    await userEvent.click(within(toolbar).getAllByRole("button")[0]!);
    await waitFor(() => expect(resolveDraft).toBeDefined());
    const beforeB = screen.getAllByText("Wasser Mail B").length;
    await userEvent.click(screen.getAllByText("Wasser Mail B")[0]!);
    await waitFor(() => expect(screen.getAllByText("Wasser Mail B").length).toBeGreaterThan(beforeB));
    resolveDraft!(jsonResponse(mail("draft-a", "AW: Heizung Mail A", { direction: "out", status: "draft" })));
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId("mail-reply-draft")).not.toBeInTheDocument();
  });
});


describe("MailWorkspace Filter per URL (GAI-110)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("preselects status, search and sync filter from the URL and rejects invalid values", async () => {
    window.history.replaceState(null, "", "/mail?status=assigned&q=Heizung&abgleich=bogus&postfach=nicht-uuid");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
    renderIntl(<MailWorkspace canApprove={false} canReadMembers={false} />);
    await waitFor(() => expect(fetchMock.mock.calls.some((c: unknown[]) => String(c[0]).includes("/mail/messages?"))).toBe(true));
    const url = fetchMock.mock.calls.map((c: unknown[]) => String(c[0])).find((u: string) => u.includes("/mail/messages?"))!;
    expect(url).toContain("status=assigned");
    expect(url).toContain("q=Heizung");
    expect(url).not.toContain("sync_state");
    expect(url).not.toContain("mailbox_id");
    await waitFor(() => expect(window.location.search).not.toContain("abgleich"));
    expect(window.location.search).toContain("status=assigned");
  });
});

describe("MailWorkspace gespeicherte Filter (AL05)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("applies a saved filter of the resource mailbox", async () => {
    window.history.replaceState(null, "", "/mail");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input: unknown) => {
      if (String(input).includes("/api/bff/workspace/filters?resource=mailbox")) {
        return jsonResponse([{ id: "f1", resource: "mailbox", name: "Offene Rechnungen", params: { status: "new", q: "Rechnung" } }]);
      }
      return jsonResponse([]);
    });
    renderIntl(<MailWorkspace canApprove={false} canReadMembers={false} />);
    await userEvent.click(await screen.findByRole("button", { name: "Offene Rechnungen" }));
    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((c: unknown[]) => String(c[0])).filter((u: string) => u.includes("/mail/messages?"));
      expect(urls.at(-1)).toContain("status=new");
      expect(urls.at(-1)).toContain("q=Rechnung");
    });
  });
});
