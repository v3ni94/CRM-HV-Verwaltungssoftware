import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalProposalsPanel } from "./PortalProposalsPanel";

const CONTACT = "01920000-0000-7000-8000-00000000000a";
const MANDATE = {
  id: "m1",
  reference: "871-01-20260927-AB12",
  creditor_id: "DE98ZZZ09999999999",
  holder: "Erika Eigentum",
  iban_masked: "DE89 **** **** 3000",
  confirmed_at: "2026-09-27T10:00:00Z",
  status: "proposed",
  evidence_document_id: "d1",
  decision_note: null,
  contact_bank_account_id: null,
};
const ADDRESS = {
  id: "cr1",
  kind: "address",
  status: "proposed",
  payload: { street: "Neue Straße", house_number: "5", postal_code: "40213", city: "Düsseldorf", valid_from: "2026-10-01" },
  contact_id: CONTACT,
  created_at: "2026-09-27T09:00:00Z",
  decision_note: null,
};

describe("PortalProposalsPanel", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("lists mandate and address proposals of the contact and accepts the mandate with a note", async () => {
    const user = userEvent.setup();
    fetchMock
      .mockResolvedValueOnce(jsonResponse([ADDRESS]))
      .mockResolvedValueOnce(jsonResponse([MANDATE]))
      .mockResolvedValueOnce(jsonResponse({ ...MANDATE, status: "accepted" }))
      .mockResolvedValueOnce(jsonResponse([ADDRESS]))
      .mockResolvedValueOnce(jsonResponse([{ ...MANDATE, status: "accepted", decision_note: "geprüft" }]));
    renderIntl(<PortalProposalsPanel contactId={CONTACT} canDecide />);
    expect(await screen.findByText("871-01-20260927-AB12")).toBeInTheDocument();
    expect(screen.getByText(/Neue Straße 5, 40213 Düsseldorf \(gültig ab 01\.10\.2026\)/)).toBeInTheDocument();
    expect(screen.getByText(/Gläubiger-ID DE98ZZZ09999999999/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Vermerk (optional)", { selector: "#note-m1" }), "geprüft");
    await user.click(screen.getAllByRole("button", { name: "Übernehmen" })[0]!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(5));
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/bff/portal-admin/sepa-mandate-proposals/m1/decide");
    expect(JSON.parse(String((fetchMock.mock.calls[2]?.[1] as RequestInit).body))).toEqual({ accept: true, note: "geprüft" });
    expect(await screen.findByText("geprüft")).toBeInTheDocument();
  });

  it("shows no decision buttons without the permission", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([ADDRESS])).mockResolvedValueOnce(jsonResponse([MANDATE]));
    renderIntl(<PortalProposalsPanel contactId={CONTACT} canDecide={false} />);
    expect(await screen.findByText("871-01-20260927-AB12")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Übernehmen" })).not.toBeInTheDocument();
  });

  it("links an accepted invoice submission to its receipt draft", async () => {
    const invoice = {
      id: "cr2",
      kind: "invoice_submission",
      status: "accepted",
      payload: { number: "RE-1", gross: "119.00" },
      contact_id: CONTACT,
      created_at: "2026-09-27T09:00:00Z",
      decision_note: null,
      receipt_draft_id: "dr1",
    };
    fetchMock.mockResolvedValueOnce(jsonResponse([invoice])).mockResolvedValueOnce(jsonResponse([]));
    renderIntl(<PortalProposalsPanel contactId={CONTACT} canDecide />);
    const link = await screen.findByTestId("receipt-draft-link");
    expect(link).toHaveAttribute("href", "/rechnungen/belegeingang?entwurf=dr1");
  });
});
