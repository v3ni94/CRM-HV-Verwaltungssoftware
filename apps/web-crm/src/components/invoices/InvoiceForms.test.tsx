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
    expect(body).toMatchObject({ work_order_id: null, resolution_id: null, plan_item_id: null, recurring_plan_id: null, net: "100.05", vat: "19.01", gross: "119.06", lines: [{ account_id: "a1", vat_percent: "19" }] });
  });
});

describe("InvoiceCreate, AP16 kind and split", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends a final invoice with the deduction of a booked progress invoice (D12)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("filter[kind]=partial")) return jsonResponse([{ id: "x1", number: "A-1", invoice_date: "2026-01-10", gross: "2380.00" }]);
      if (url.includes("/contacts")) return jsonResponse({ items: [{ id: "p1", display_name: "Dachdecker GmbH" }], total: 1, page: 1, page_size: 50 });
      return jsonResponse({ id: ID }, 201);
    });
    renderIntl(<InvoiceCreate ledgers={[{ id: "l1", label: "WEG" }]} accounts={{ l1: [{ id: "a1", label: "043000 Allgemeinstrom" }] }} />);
    await userEvent.type(screen.getByLabelText("Aussteller suchen"), "Dach");
    await userEvent.click(screen.getByText("Suchen"));
    await userEvent.selectOptions(await screen.findByLabelText("Aussteller"), "p1");
    await userEvent.selectOptions(screen.getByLabelText("Rechnungsart"), "final");
    await userEvent.type(screen.getByLabelText("Rechnungsnummer"), "S-1");
    await userEvent.type(screen.getByLabelText("Rechnungsdatum"), "2026-03-01");
    await userEvent.type(screen.getByLabelText("Netto"), "5000,00");
    await userEvent.selectOptions(screen.getByLabelText("Kostenkonto"), "a1");
    await userEvent.click(await screen.findByRole("checkbox", { name: /A-1/ }));
    expect(screen.getByTestId("final-summary")).toHaveTextContent("Restverpflichtung 3.570,00 EUR");
    await userEvent.click(screen.getByText("Rechnung erfassen"));
    await waitFor(() => expect(push).toHaveBeenCalled());
    const post = fetchMock.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "POST");
    expect(JSON.parse((post?.[1] as RequestInit).body as string)).toMatchObject({ kind: "final", gross: "5950.00", deductions: [{ invoice_id: "x1", gross: "2380.00" }] });
  });

  it("blocks saving a split invoice until the lines add up to the document gross (D22)", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ items: [{ id: "p1", display_name: "Dachdecker GmbH" }], total: 1, page: 1, page_size: 50 }));
    renderIntl(<InvoiceCreate ledgers={[{ id: "l1", label: "WEG" }]} accounts={{ l1: [{ id: "a1", label: "043000 Allgemeinstrom" }] }} />);
    await userEvent.type(screen.getByLabelText("Aussteller suchen"), "Dach");
    await userEvent.click(screen.getByText("Suchen"));
    await userEvent.selectOptions(await screen.findByLabelText("Aussteller"), "p1");
    await userEvent.type(screen.getByLabelText("Rechnungsnummer"), "M-1");
    await userEvent.type(screen.getByLabelText("Rechnungsdatum"), "2026-03-01");
    await userEvent.click(screen.getByLabelText("Rechnung auf mehrere Zeilen aufteilen (Mischrechnung)"));
    for (const n of [1, 2]) {
      await userEvent.selectOptions(screen.getByLabelText(`Konto Zeile ${n}`), "a1");
      await userEvent.type(screen.getByLabelText(`Netto Zeile ${n}`), "300,00");
      await userEvent.type(screen.getByLabelText(`Begründung Zeile ${n}`), n === 1 ? "umlagefähig" : "Verwaltung");
    }
    await userEvent.type(screen.getByLabelText("Brutto laut Beleg"), "713,99");
    expect(screen.getByTestId("split-mismatch")).toBeInTheDocument();
    expect(screen.getByText("Rechnung erfassen")).toBeDisabled();
    await userEvent.clear(screen.getByLabelText("Brutto laut Beleg"));
    await userEvent.type(screen.getByLabelText("Brutto laut Beleg"), "714,00");
    expect(screen.getByText("Rechnung erfassen")).toBeEnabled();
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

describe("InvoiceCreate extra details (M14)", () => {
  it("offers the optional review fields inside a collapsed section", async () => {
    renderIntl(<InvoiceCreate ledgers={[{ id: "l1", label: "WEG" }]} accounts={{ l1: [{ id: "a1", label: "043000 Allgemeinstrom" }] }} />);
    const extra = screen.getByTestId("invoice-extra");
    expect(extra).not.toHaveAttribute("open");
    for (const label of ["Leistungsort", "USt-IdNr. des Aussteller", "Sicherheitseinbehalt", "Anzahlung", "Reverse Charge", "Bauabzugsteuer relevant"]) {
      expect(extra).toHaveTextContent(label);
    }
  });
});

describe("InvoiceCreate attachments (Q02)", () => {
  afterEach(() => vi.restoreAllMocks());
  const A = "0192abcd-0000-7000-8000-0000000000a1";
  const B = "0192abcd-0000-7000-8000-0000000000a2";

  it("sends the attachment set and rejects invalid IDs", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementationOnce(async () => jsonResponse({ items: [{ id: "p1", display_name: "Dachdecker GmbH" }], total: 1, page: 1, page_size: 50 }))
      .mockImplementationOnce(async () => jsonResponse({ id: ID }, 201));
    renderIntl(<InvoiceCreate ledgers={[{ id: "l1", label: "WEG" }]} accounts={{ l1: [{ id: "a1", label: "043000 Allgemeinstrom" }] }} />);
    await userEvent.type(screen.getByLabelText("Aussteller suchen"), "Dach");
    await userEvent.click(screen.getByText("Suchen"));
    await userEvent.selectOptions(await screen.findByLabelText("Aussteller"), "p1");
    await userEvent.type(screen.getByLabelText("Rechnungsnummer"), "D-2");
    await userEvent.type(screen.getByLabelText("Rechnungsdatum"), "2026-03-01");
    await userEvent.type(screen.getByLabelText("Netto"), "10");
    await userEvent.selectOptions(screen.getByLabelText("Kostenkonto"), "a1");
    const field = screen.getByTestId("attachment-ids");
    await userEvent.type(field, "kein-uuid");
    expect(screen.getByText("Rechnung erfassen")).toBeDisabled();
    await userEvent.clear(field);
    await userEvent.click(field);
    await userEvent.paste(`${A}, ${B}`);
    expect(screen.getByText(/2 Anlage\(n\) verknüpft/)).toBeInTheDocument();
    await userEvent.click(screen.getByText("Rechnung erfassen"));
    await waitFor(() => expect(push).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string);
    expect(body.attachment_document_ids).toEqual([A, B]);
  }, 20000);
});
