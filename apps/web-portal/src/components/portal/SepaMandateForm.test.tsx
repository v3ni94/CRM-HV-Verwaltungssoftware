import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ibanValid, SepaMandateForm } from "./SepaMandateForm";

const CONTRACTS = [{ id: "c1", kind: "ownership", number: "871-01" }];
const PREVIEW = {
  contract_id: "c1",
  contract_number: "871-01",
  creditor_name: "WEG Musterweg",
  creditor_id: "DE98ZZZ09999999999",
  reference: "871-01-20260927-AB12",
  scheme: "core",
  sequence: "recurrent",
  text: "SEPA-Lastschriftmandat\nGläubiger-Identifikationsnummer: DE98ZZZ09999999999\nMandatsreferenz: 871-01-20260927-AB12",
};

describe("ibanValid", () => {
  it("accepts a valid IBAN with spaces and rejects a wrong check digit", () => {
    expect(ibanValid("DE89 3704 0044 0532 0130 00")).toBe(true);
    expect(ibanValid("DE88370400440532013000")).toBe(false);
    expect(ibanValid("DE00")).toBe(false);
  });
});

describe("SepaMandateForm", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("shows creditor id, reference and recurring payment after loading the text", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(PREVIEW));
    renderIntl(<SepaMandateForm contracts={CONTRACTS} proposals={[]} />);
    expect(screen.getByText("Noch kein Mandat erteilt.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mandatstext anzeigen" }));
    expect(await screen.findByText("DE98ZZZ09999999999")).toBeInTheDocument();
    expect(screen.getByText("871-01-20260927-AB12")).toBeInTheDocument();
    expect(screen.getByText("wiederkehrende Zahlung")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/bff/portal/sepa-mandates/preview?contract_id=c1", expect.anything());
  });

  it("requires holder, a valid IBAN and the confirmation before submitting", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(PREVIEW));
    renderIntl(<SepaMandateForm contracts={CONTRACTS} proposals={[]} />);
    await user.click(screen.getByRole("button", { name: "Mandatstext anzeigen" }));
    await screen.findByTestId("mandate-text");
    await user.click(screen.getByRole("button", { name: "Mandat erteilen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte den Kontoinhaber angeben.");
    await user.type(screen.getByLabelText("Kontoinhaber (Vor- und Nachname)"), "Erika Eigentum");
    await user.type(screen.getByLabelText("IBAN"), "DE88370400440532013000");
    await user.click(screen.getByRole("button", { name: "Mandat erteilen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte eine gültige IBAN eingeben.");
    await user.clear(screen.getByLabelText("IBAN"));
    await user.type(screen.getByLabelText("IBAN"), "DE89 3704 0044 0532 0130 00");
    await user.click(screen.getByRole("button", { name: "Mandat erteilen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte das Mandat bestätigen.");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("submits the confirmed mandate as a proposal and lists it as under review", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(PREVIEW))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            id: "p1",
            reference: PREVIEW.reference,
            iban_masked: "DE89 **** **** 3000",
            status: "proposed",
            confirmed_at: "2026-09-27T10:00:00Z",
            evidence_document_id: "d1",
          },
          201,
        ),
      );
    renderIntl(<SepaMandateForm contracts={CONTRACTS} proposals={[]} />);
    await user.click(screen.getByRole("button", { name: "Mandatstext anzeigen" }));
    await screen.findByTestId("mandate-text");
    await user.type(screen.getByLabelText("Kontoinhaber (Vor- und Nachname)"), "Erika Eigentum");
    await user.type(screen.getByLabelText("IBAN"), "DE89 3704 0044 0532 0130 00");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Mandat erteilen" }));
    await waitFor(() => expect(screen.getByText(/Das Mandat wurde als Vorschlag übermittelt/)).toBeInTheDocument());
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/bff/portal/sepa-mandates",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          contract_id: "c1",
          iban: "DE89370400440532013000",
          holder: "Erika Eigentum",
          bic: null,
          confirmed: true,
        }),
      }),
    );
    expect(screen.getByText(/in Prüfung/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Nachweis (PDF)" })).toHaveAttribute(
      "href",
      "/api/portal-files/portal/documents/d1/download",
    );
  });
});
