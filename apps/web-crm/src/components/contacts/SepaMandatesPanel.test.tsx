import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { SepaMandatesPanel } from "./SepaMandatesPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

const CONTACT = "0192abcd-0000-7000-8000-000000000061";
const ACC1 = "0192abcd-0000-7000-8000-000000000062";
const ACC2 = "0192abcd-0000-7000-8000-000000000063";
const mandates = [
  { bank_account_id: ACC1, iban_masked: "DE00 **** 1111", mandate_reference: "M-1", mandate_signed_on: "2025-02-03", mandate_status: "active", mandate_revoked_on: null },
  { bank_account_id: ACC2, iban_masked: "DE00 **** 2222", mandate_reference: null, mandate_signed_on: null, mandate_status: "revoked", mandate_revoked_on: "2026-01-15" },
] as never;

describe("SepaMandatesPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("shows the empty message without mandates", () => {
    renderIntl(<SepaMandatesPanel contactId={CONTACT} mandates={[]} />);
    expect(screen.getByText("Keine Einträge.")).toBeInTheDocument();
  });

  it("offers the revoke action only for active mandates", () => {
    renderIntl(<SepaMandatesPanel contactId={CONTACT} mandates={mandates} />);
    expect(screen.getAllByRole("button", { name: "Widerrufen" })).toHaveLength(1);
    expect(screen.getByText("aktiv")).toBeInTheDocument();
    expect(screen.getByText("widerrufen (15.01.2026)")).toBeInTheDocument();
    expect(screen.getByText("03.02.2025")).toBeInTheDocument();
  });

  it("does not call the API when the confirmation is declined", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderIntl(<SepaMandatesPanel contactId={CONTACT} mandates={mandates} />);
    await userEvent.click(screen.getByRole("button", { name: "Widerrufen" }));
    expect(window.confirm).toHaveBeenCalledWith("SEPA-Mandat für DE00 **** 1111 wirklich widerrufen?");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("revokes after confirmation and refreshes the page", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<SepaMandatesPanel contactId={CONTACT} mandates={mandates} />);
    await userEvent.click(screen.getByRole("button", { name: "Widerrufen" }));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/bff/contacts/${CONTACT}/bank-accounts/${ACC1}/mandate/revoke`);
    expect(init.method).toBe("POST");
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("shows the API error and does not refresh when revoking fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Mandat gesperrt", status: 409 }, 409));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderIntl(<SepaMandatesPanel contactId={CONTACT} mandates={mandates} />);
    await userEvent.click(screen.getByRole("button", { name: "Widerrufen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });
});
