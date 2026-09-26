import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InvoiceActions, InvoiceCreate } from "./InvoiceForms";

const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push }) }));
const ID = "0192abcd-0000-7000-8000-000000000060";

describe("InvoiceCreate", () => {
  afterEach(() => vi.restoreAllMocks());

  it("computes VAT in cents and sends one line", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(async () => jsonResponse({ items: [{ id: "p1", display_name: "Dachdecker GmbH" }], total: 1, page: 1, page_size: 50 }))
      .mockImplementationOnce(async () => jsonResponse({ id: ID }, 201));
    renderIntl(<InvoiceCreate ledgers={[{ id: "l1", label: "WEG" }]} accounts={{ l1: [{ id: "a1", label: "043000 Allgemeinstrom" }] }} />);
    await userEvent.type(screen.getByLabelText("Aussteller suchen"), "Dach");
    await userEvent.click(screen.getByText("Suchen"));
    await userEvent.selectOptions(await screen.findByLabelText("Aussteller"), "p1");
    await userEvent.type(screen.getByLabelText("Rechnungsnummer"), "D-1");
    await userEvent.type(screen.getByLabelText("Rechnungsdatum"), "2026-03-01");
    await userEvent.type(screen.getByLabelText("Netto"), "100,05");
    await userEvent.selectOptions(screen.getByLabelText("Kostenkonto"), "a1");
    expect(screen.getByTestId("gross")).toHaveTextContent("Brutto 119,06 EUR (Steuer 19,01 EUR)");
    await userEvent.click(screen.getByText("Rechnung erfassen"));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/rechnungen/${ID}`));
    const body = JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string);
    expect(body).toMatchObject({ net: "100.05", vat: "19.01", gross: "119.06", lines: [{ account_id: "a1", vat_percent: "19" }] });
  });
});

describe("InvoiceActions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("records a review step with a reason and offers release only when closed", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}, 201));
    const first = renderIntl(<InvoiceActions id={ID} reviewStatus="open" postingStatus="unposted" released={false} ibanOpen={false} />);
    expect(screen.queryByText("Rechnung freigeben (zweite Person)")).toBeNull();
    await userEvent.selectOptions(screen.getByLabelText("Ergebnis"), "query");
    await userEvent.type(screen.getByLabelText("Begründung"), "Leistungsnachweis fehlt");
    await userEvent.click(screen.getByText("Prüfschritt erfassen"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ step: "completeness", result: "query", reason: "Leistungsnachweis fehlt" });
    first.unmount();
    renderIntl(<InvoiceActions id={ID} reviewStatus="closed_ok" postingStatus="unposted" released={false} ibanOpen={false} />);
    expect(screen.getByText("Rechnung freigeben (zweite Person)")).toBeInTheDocument();
  });

  it("shows nothing once posted", () => {
    const { container } = renderIntl(<InvoiceActions id={ID} reviewStatus="closed_ok" postingStatus="posted" released ibanOpen={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("names the next step so no missing button stays unexplained", () => {
    const open = renderIntl(<InvoiceActions id={ID} reviewStatus="open" postingStatus="unposted" released={false} ibanOpen={false} />);
    expect(screen.getByTestId("invoice-next-step")).toHaveTextContent("alle drei Prüfschritte erfassen");
    open.unmount();
    const iban = renderIntl(<InvoiceActions id={ID} reviewStatus="open" postingStatus="unposted" released={false} ibanOpen />);
    expect(screen.getByTestId("invoice-next-step")).toHaveTextContent("abweichende IBAN");
    iban.unmount();
    const closed = renderIntl(<InvoiceActions id={ID} reviewStatus="closed_with_reservation" postingStatus="unposted" released={false} ibanOpen={false} />);
    expect(screen.getByTestId("invoice-next-step")).toHaveTextContent("Freigabe durch eine zweite Person");
    closed.unmount();
    renderIntl(<InvoiceActions id={ID} reviewStatus="closed_ok" postingStatus="unposted" released ibanOpen={false} />);
    expect(screen.getByTestId("invoice-next-step")).toHaveTextContent("Freigabestufe G1");
    expect(screen.getByText("Buchen")).toBeInTheDocument();
  });
});

describe("InvoiceCreate gross preview", () => {
  it("formats thousands with a dot and decimals with a comma", async () => {
    renderIntl(<InvoiceCreate ledgers={[{ id: "l1", label: "WEG" }]} accounts={{ l1: [] }} />);
    await userEvent.type(screen.getByLabelText("Netto"), "1234.56");
    expect(screen.getByTestId("gross")).toHaveTextContent("Brutto 1.469,13 EUR (Steuer 234,57 EUR)");
  });
});
