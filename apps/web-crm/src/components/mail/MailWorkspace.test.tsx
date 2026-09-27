import { screen, waitFor } from "@testing-library/react";
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
