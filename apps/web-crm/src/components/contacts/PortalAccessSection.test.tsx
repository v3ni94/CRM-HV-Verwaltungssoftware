import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalAccessSection, type PortalAccount, type PortalEmail } from "./PortalAccessSection";

vi.mock("qrcode", () => ({
  default: { toDataURL: vi.fn(async () => "data:image/png;base64,QUJD") },
}));

const CONTACT = "01920000-0000-7000-8000-00000000000a";
const EMAILS: PortalEmail[] = [
  { id: "e1", email: "erika@example.test", is_primary: true, is_portal_login: false },
];
const ACCOUNT: PortalAccount = {
  id: "acc",
  contact_id: CONTACT,
  email: "erika@example.test",
  status: "invited",
  locked: false,
  invited_at: "2026-09-26T08:00:00Z",
  invitation_expires_at: "2026-10-10T08:00:00Z",
  activated_at: null,
  last_login_at: null,
  magic_link_2fa: false,
};

describe("PortalAccessSection", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("loads the accounts on mount, invites the contact and shows code, link and QR code once", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            id: "acc",
            user_id: "usr",
            grants: 1,
            invitation_token: "abcd.efgh",
            invitation_url: "https://portal.example.test/einladung?code=abcd.efgh",
          },
          201,
        ),
      )
      .mockResolvedValueOnce(jsonResponse([ACCOUNT]));
    renderIntl(<PortalAccessSection contactId={CONTACT} displayName="Erika Mustermann" emails={EMAILS} canInvite />);
    expect(screen.getByTestId("contact-portal-status")).toHaveTextContent("Wird geladen");
    await waitFor(() => expect(screen.getByText("Kein Portalzugang")).toBeInTheDocument());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/portal-admin/accounts?contact_id=${CONTACT}`);
    await userEvent.click(screen.getByRole("button", { name: "Einladen" }));
    await waitFor(() => expect(screen.getByTestId("contact-invitation")).toBeInTheDocument());
    expect(screen.getByText("abcd.efgh")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://portal.example.test/einladung?code=abcd.efgh" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("img", { name: "QR-Code des Einladungslinks" })).toBeInTheDocument());
    const [url, init] = fetchMock.mock.calls[1] ?? [];
    expect(String(url)).toBe("/api/bff/portal-admin/accounts");
    expect(JSON.parse(String(init?.body))).toEqual({
      contact_id: CONTACT,
      email: "erika@example.test",
      display_name: "Erika Mustermann",
      send_invitation: true,
    });
    // After inviting the status is reloaded from the API.
    await waitFor(() => expect(screen.getByText("Eingeladen, Passwort noch nicht gesetzt")).toBeInTheDocument());
    expect(screen.getByText("Eingeladen am 26.09.2026, Code gültig bis 10.10.2026")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Einladen" })).not.toBeInTheDocument();
  });

  it("shows an active account with lock indication and last login instead of the invite form", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse([
        {
          ...ACCOUNT,
          status: "active",
          locked: true,
          activated_at: "2026-09-27T09:00:00Z",
          last_login_at: "2026-09-28T07:30:00Z",
        },
      ]),
    );
    renderIntl(<PortalAccessSection contactId={CONTACT} displayName="Erika Mustermann" emails={EMAILS} canInvite />);
    await waitFor(() => expect(screen.getByTestId("contact-portal-status")).toHaveTextContent("Zugang aktiv, gesperrt"));
    expect(screen.getByText("Anmeldung: erika@example.test")).toBeInTheDocument();
    expect(screen.getByText("Aktiviert am 27.09.2026")).toBeInTheDocument();
    expect(screen.getByText(/Letzte Anmeldung 28\.09\.2026/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Einladen" })).not.toBeInTheDocument();
  });

  it("falls back to the conflict answer when the list is unavailable", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ title: "Fehler", status: 500 }, 500))
      .mockResolvedValueOnce(
        jsonResponse({ title: "Konflikt", status: 409, detail: "Für den Kontakt besteht bereits ein Portalzugang." }, 409),
      );
    renderIntl(<PortalAccessSection contactId={CONTACT} displayName="Erika Mustermann" emails={EMAILS} canInvite />);
    await waitFor(() => expect(screen.getByText("Status nicht abrufbar")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Einladen" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("bereits ein Portalzugang"));
    expect(screen.getByText("Portalzugang besteht bereits")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Einladen" })).not.toBeInTheDocument();
  });

  it("hides the invitation form without contacts:update but still shows the status", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));
    renderIntl(
      <PortalAccessSection contactId={CONTACT} displayName="Erika Mustermann" emails={EMAILS} canInvite={false} />,
    );
    await waitFor(() => expect(screen.getByText("Kein Portalzugang")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Einladen" })).not.toBeInTheDocument();
    expect(screen.getByText("Einladen nur mit dem Recht contacts:update.")).toBeInTheDocument();
  });

  it("downloads the invitation letter as PDF and toggles the e-mail code second factor (M21-01)", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse([ACCOUNT]))
      .mockResolvedValueOnce(new Response("%PDF-1.4", { status: 200 }))
      .mockResolvedValueOnce(jsonResponse([ACCOUNT]))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse([{ ...ACCOUNT, magic_link_2fa: true }]));
    // createObjectURL/revokeObjectURL and <a>.click() are not implemented in jsdom.
    const createUrl = vi.fn(() => "blob:test");
    const revokeUrl = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL: createUrl, revokeObjectURL: revokeUrl });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    renderIntl(<PortalAccessSection contactId={CONTACT} displayName="Erika Mustermann" emails={EMAILS} canInvite />);
    await waitFor(() => expect(screen.getByTestId("contact-portal-letter")).toBeInTheDocument());

    await userEvent.click(screen.getByTestId("contact-portal-letter"));
    await waitFor(() => expect(createUrl).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe(`/api/bff/portal-admin/accounts/${ACCOUNT.id}/invitation-letter`);
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({ method: "POST" });
    expect(click).toHaveBeenCalled();

    await userEvent.click(screen.getByRole("checkbox", { name: "Zweiter Faktor per E-Mail-Code beim Anmeldelink" }));
    await waitFor(() => expect(fetchMock.mock.calls[3]).toBeDefined());
    expect(String(fetchMock.mock.calls[3]?.[0])).toBe(`/api/bff/portal-admin/accounts/${ACCOUNT.id}/security`);
    expect(JSON.parse(String(fetchMock.mock.calls[3]?.[1]?.body))).toEqual({ magic_link_2fa: true });
    await waitFor(() => expect(screen.getByRole("checkbox")).toBeChecked());
  });

  it("offers renewing only for a lapsed invitation and shows the new code once", async () => {
    const lapsed: PortalAccount = { ...ACCOUNT, invitation_expires_at: "2026-01-10T08:00:00Z" };
    fetchMock
      .mockResolvedValueOnce(jsonResponse([lapsed]))
      .mockResolvedValueOnce(
        jsonResponse(
          { id: "acc", user_id: "usr", grants: 1, invitation_token: "neu.code", invitation_url: null, reissued: true },
          201,
        ),
      )
      .mockResolvedValueOnce(jsonResponse([{ ...lapsed, invitation_expires_at: "2099-01-01T00:00:00Z" }]));
    renderIntl(<PortalAccessSection contactId={CONTACT} displayName="Erika Mustermann" emails={EMAILS} canInvite />);
    await userEvent.click(await screen.findByTestId("contact-portal-renew"));
    await waitFor(() => expect(screen.getByTestId("contact-invitation")).toBeInTheDocument());
    const call = fetchMock.mock.calls[1];
    expect(String(call?.[0])).toBe("/api/bff/portal-admin/accounts");
    expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({ contact_id: CONTACT, email: "erika@example.test" });
    expect(screen.getByText("neu.code")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId("contact-portal-renew")).toBeNull());
  });

  it("hides the renew button for a valid invitation and without permission", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([{ ...ACCOUNT, invitation_expires_at: "2099-01-01T00:00:00Z" }]));
    renderIntl(<PortalAccessSection contactId={CONTACT} displayName="Erika Mustermann" emails={EMAILS} canInvite />);
    await screen.findByTestId("contact-portal-account");
    expect(screen.queryByTestId("contact-portal-renew")).toBeNull();
  });

  it("creates the access without invitation when the switch is off and sends send_invitation=false", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse({ id: "acc", user_id: "usr", grants: 0, invitation_token: null, invitation_url: null }, 201))
      .mockResolvedValueOnce(jsonResponse([{ ...ACCOUNT, status: "not_invited" }]));
    renderIntl(<PortalAccessSection contactId={CONTACT} displayName="Erika Mustermann" emails={EMAILS} canInvite />);
    const toggle = await screen.findByTestId("contact-portal-send-invitation");
    expect(toggle).toBeChecked();
    await userEvent.click(toggle);
    await userEvent.click(screen.getByRole("button", { name: "Zugang ohne Einladung anlegen" }));
    await waitFor(() => expect(screen.getByTestId("contact-portal-status")).toHaveTextContent("Nicht eingeladen"));
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toMatchObject({ send_invitation: false });
    expect(screen.queryByTestId("contact-invitation")).toBeNull();
  });

  it("offers Einladen for not_invited and sends the invitation", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse([{ ...ACCOUNT, status: "not_invited" }]))
      .mockResolvedValueOnce(jsonResponse({ id: "acc", user_id: "usr", grants: 0, invitation_token: "x.y", invitation_url: null }, 201))
      .mockResolvedValueOnce(jsonResponse([ACCOUNT]));
    renderIntl(<PortalAccessSection contactId={CONTACT} displayName="Erika Mustermann" emails={EMAILS} canInvite />);
    await userEvent.click(await screen.findByRole("button", { name: "Einladen" }));
    await waitFor(() => expect(screen.getByText("x.y")).toBeInTheDocument());
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toMatchObject({ email: "erika@example.test" });
  });

  it.each([
    ["not_invited", "Nicht eingeladen"],
    ["invited", "Eingeladen, Passwort noch nicht gesetzt"],
    ["active", "Zugang aktiv"],
    ["locked", "Zugang aktiv, gesperrt"],
    ["expired", "Einladung abgelaufen"],
    ["revoked", "Zugang entzogen"],
  ])("labels the status %s", async (status, label) => {
    fetchMock.mockResolvedValueOnce(jsonResponse([{ ...ACCOUNT, status, invitation_expires_at: "2099-01-01T00:00:00Z" }]));
    renderIntl(<PortalAccessSection contactId={CONTACT} displayName="Erika Mustermann" emails={EMAILS} canInvite />);
    await screen.findByTestId("contact-portal-account");
    expect(screen.getByTestId("contact-portal-status")).toHaveTextContent(label);
  });
});
