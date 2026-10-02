import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createTranslator } from "next-intl";

import { jsonResponse } from "@/test/intl";
import messages from "../../../messages/de.json";

import { PortalAccessBox } from "./PortalAccessBox";
import type { Item } from "./types";

vi.mock("@/components/portal/InvitationQr", () => ({
  InvitationQr: ({ url }: { url?: string | null }) => <div data-testid="qr" data-url={url ?? ""} />,
}));

const translator = createTranslator({ locale: "de", messages, namespace: "Handover" });
const t = (key: string, values?: Record<string, string | number>) => translator(key as never, values as never);
const BASE = "/api/bff/handover/protocols/0192abcd-0000-7000-8000-0000000000a1";
const ITEM_ID = "0192abcd-0000-7000-8000-0000000000a2";

function setup(item: Partial<Item> = {}, disabled = false) {
  const onChanged = vi.fn(async () => {});
  const onError = vi.fn();
  render(<PortalAccessBox base={BASE} item={{ id: ITEM_ID, email: "mieter@example.org", ...item } as Item} disabled={disabled} onChanged={onChanged} onError={onError} t={t} />);
  return { onChanged, onError };
}

describe("PortalAccessBox", () => {
  afterEach(() => vi.restoreAllMocks());

  it("grants access with the trimmed email and shows the invitation once", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ account_id: "a", invitation_token: "TOKEN-123", invitation_url: "https://portal.example/invite", email: "mieter@example.org" }),
    );
    const { onChanged } = setup();
    await userEvent.clear(screen.getByLabelText("E-Mail-Adresse für die Einladung"));
    await userEvent.type(screen.getByLabelText("E-Mail-Adresse für die Einladung"), " neu@example.org ");
    await userEvent.click(screen.getByRole("button", { name: "Portalzugang einrichten" }));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE}/participants/${ITEM_ID}/portal-access`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ email: "neu@example.org" });
    expect(await screen.findByTestId("invitation-token")).toHaveTextContent("TOKEN-123");
    expect(screen.getByTestId("qr")).toHaveAttribute("data-url", "https://portal.example/invite");
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  it("reports the API error and shows no invitation", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Kein Kontakt", status: 422 }, 422));
    const { onError, onChanged } = setup();
    await userEvent.click(screen.getByRole("button", { name: "Portalzugang einrichten" }));
    await vi.waitFor(() => expect(onError).toHaveBeenLastCalledWith(expect.any(String)));
    expect(screen.queryByTestId("invitation-token")).not.toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it("shows the status of an existing read grant with date and offers renew and revoke", () => {
    setup({ portal_access: { account_status: "active", right: "read", valid_to: "2026-10-15", active: true } });
    expect(screen.getByText("Nur lesen bis 15.10.2026")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zugang erneuern" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zugang beenden" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Portalzugang einrichten" })).not.toBeInTheDocument();
  });

  it("offers no renew for an active edit grant and shows the invited state", () => {
    setup({ portal_access: { account_status: "invited", right: "edit", valid_to: null, active: true } });
    expect(screen.getByText("Eingeladen, Passwort noch nicht gesetzt")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Zugang erneuern" })).not.toBeInTheDocument();
  });

  it("revokes only after confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}));
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    const { onChanged } = setup({ portal_access: { account_status: "active", right: "edit", valid_to: null, active: true } });
    await userEvent.click(screen.getByRole("button", { name: "Zugang beenden" }));
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Zugang beenden" }));
    expect(confirm).toHaveBeenCalledTimes(2);
    expect((fetchMock.mock.calls[0] as [string, RequestInit])[1].method).toBe("DELETE");
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  });

  it("hides all actions when disabled", () => {
    setup({}, true);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("Portalzugang")).toBeInTheDocument();
  });
});
