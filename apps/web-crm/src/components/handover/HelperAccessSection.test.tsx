import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse } from "@/test/intl";

import { HelperAccessSection } from "./HelperAccessSection";

const BASE = "/api/bff/handover/protocols/01920000-0000-7000-8000-000000000001";
const GRANT = "01920000-0000-7000-8000-0000000000aa";
const t = (key: string) => key;

function row(hasEmail: boolean) {
  return {
    grant_id: GRANT,
    account_id: "01920000-0000-7000-8000-0000000000bb",
    contact_id: "01920000-0000-7000-8000-0000000000cc",
    name: "Erika Muster",
    kind: "helper",
    right: "edit",
    valid_from: "2026-09-26",
    valid_to: "2026-10-26",
    account_status: "invited",
    activated: false,
    has_email: hasEmail,
  };
}

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(window, "confirm").mockReturnValue(true);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("HelperAccessSection invitation delivery (M30-01)", () => {
  it("creates an e-mail draft for a helper with e-mail and never shows the code", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST")
        return Promise.resolve(jsonResponse({ mail_draft_id: "m1", invitation_expires_at: null }));
      return Promise.resolve(jsonResponse([row(true)]));
    });
    render(<HelperAccessSection base={BASE} disabled={false} t={t} />);
    await userEvent.click(await screen.findByText("helperAccess.invitationDraft"));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        `${BASE}/helper-access/${GRANT}/invitation-draft`,
        expect.objectContaining({ method: "POST" }),
      ),
    );
    expect(await screen.findByText("helperAccess.mailDrafted")).toBeInTheDocument();
    expect(screen.queryByTestId("helper-invitation-token")).toBeNull();
  });

  it("offers only the letter download without e-mail and posts to invitation-letter", async () => {
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST")
        return Promise.resolve(
          new Response(new Blob(["%PDF"]), { status: 200, headers: { "content-type": "application/pdf" } }),
        );
      return Promise.resolve(jsonResponse([row(false)]));
    });
    render(<HelperAccessSection base={BASE} disabled={false} t={t} />);
    const button = await screen.findByText("helperAccess.invitationLetter");
    expect(screen.queryByText("helperAccess.invitationDraft")).toBeNull();
    await userEvent.click(button);
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        `${BASE}/helper-access/${GRANT}/invitation-letter`,
        expect.objectContaining({ method: "POST" }),
      ),
    );
    expect(screen.queryByTestId("helper-invitation-token")).toBeNull();
  });

  it("sends the mail draft option when creating an access", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "POST")
        return Promise.resolve(
          jsonResponse({ grant_id: GRANT, invitation_token: "abc.def", mail_draft_id: null }, 201),
        );
      return Promise.resolve(jsonResponse([]));
    });
    render(<HelperAccessSection base={BASE} disabled={false} t={t} />);
    await userEvent.type(screen.getByLabelText("helperAccess.name"), "Erika Muster");
    await userEvent.type(screen.getByLabelText("helperAccess.email"), "erika@example.test");
    await userEvent.click(screen.getByLabelText("helperAccess.mailDraftOption"));
    await userEvent.click(screen.getByText("helperAccess.create"));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "POST");
      expect(JSON.parse(String((post?.[1] as RequestInit).body)).invitation_as_mail_draft).toBe(false);
    });
    expect(await screen.findByText("helperAccess.tokenHelpManual")).toBeInTheDocument();
  });
});
