import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MfaResetAdmin, type MfaResetRequest } from "./MfaResetAdmin";

const MEMBERS = [{ membership_id: "m1", display_name: "Erika Beispiel" }];
const OPEN: MfaResetRequest = { id: "r1", membership_id: "m1", reason: "Telefon verloren", status: "requested", requested_by: "u1", created_at: "2026-10-02T08:00:00Z" };

describe("MfaResetAdmin (AJ08, GAI-603)", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("hides the request form while the switch is off", () => {
    renderIntl(<MfaResetAdmin members={MEMBERS} initialRequests={[]} enabled={false} />);
    expect(screen.getByText(/Die Funktion ist ausgeschaltet/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Zurücksetzen beantragen" })).toBeNull();
  });

  it("files a request with a reason", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...OPEN, id: "r2" }, 201));
    renderIntl(<MfaResetAdmin members={MEMBERS} initialRequests={[]} enabled />);
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Mitglied"), "m1");
    await user.type(screen.getByLabelText(/Begründung/), "Telefon verloren");
    await user.click(screen.getByRole("button", { name: "Zurücksetzen beantragen" }));
    await waitFor(() => expect(screen.getByText("Antrag gestellt.")).toBeInTheDocument());
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/bff/auth/mfa-reset/requests");
  });

  it("rejects an open request", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ...OPEN, status: "rejected" }));
    renderIntl(<MfaResetAdmin members={MEMBERS} initialRequests={[OPEN]} enabled />);
    await userEvent.setup().click(screen.getByRole("button", { name: "Ablehnen" }));
    await waitFor(() => expect(screen.getByText("Entscheidung gespeichert.")).toBeInTheDocument());
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/bff/auth/mfa-reset/requests/r1/reject");
  });
});
