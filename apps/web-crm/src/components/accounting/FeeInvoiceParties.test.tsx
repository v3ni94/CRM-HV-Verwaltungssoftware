import { screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { FeeInvoiceParties } from "./FeeInvoiceParties";

const ENTITY = "0192abcd-0000-7000-8000-000000000a01";
const PARTY = "0192abcd-0000-7000-8000-000000000a02";
const MANAGER = "0192abcd-0000-7000-8000-000000000a03";

describe("FeeInvoiceParties", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows payer, invoice recipient and payee as separate labelled fields", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockResolvedValueOnce(jsonResponse([{ id: ENTITY, name: "WEG Musterstraße 1" }]))
      .mockResolvedValueOnce(jsonResponse({ id: PARTY, name: "Eigentümergemeinschaft Musterstraße 1" }))
      .mockResolvedValueOnce(jsonResponse({ display_name: "Hausverwaltung Müller GmbH" }));
    renderIntl(
      <FeeInvoiceParties propertyId="p1" debtorLegalEntityId={ENTITY} invoiceDebtorPartyId={PARTY} managerContactId={MANAGER} />,
    );
    expect(await screen.findByTestId("fee-party-payer")).toHaveTextContent("WEG Musterstraße 1");
    expect(screen.getByTestId("fee-party-recipient")).toHaveTextContent("Eigentümergemeinschaft Musterstraße 1");
    expect(screen.getByTestId("fee-party-payee")).toHaveTextContent("Verwaltungsgesellschaft, Ansprechpartner: Hausverwaltung Müller GmbH");
    expect(screen.getByText(/nie an den Zahler oder den Rechnungsempfänger/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("warns when payer and recipient are missing and fixes the payee to the management company", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<FeeInvoiceParties propertyId="p1" debtorLegalEntityId={null} invoiceDebtorPartyId={null} />);
    expect(await screen.findByTestId("fee-party-payee")).toHaveTextContent("Verwaltungsgesellschaft");
    expect(screen.getByTestId("fee-party-payer")).toHaveTextContent("nicht ermittelt");
    expect(screen.getByText(/kein zahlender Rechtsträger/)).toBeInTheDocument();
    expect(screen.getByText(/keine Vertragspartei als Rechnungsempfänger/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
