import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import type { AmountRow } from "./amounts";
import { AmountsPanel } from "./AmountsPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

const CONTRACT = "01920000-0000-7000-8000-0000000000k1";
const TYPES = [
  { code: "rent", label: "Miete" },
  { code: "operating_cost_advance", label: "Betriebskosten-Vorauszahlung" },
  { code: "rent_reduction", label: "Mietminderung" },
];

const rent: AmountRow = {
  id: "a1",
  contract_id: CONTRACT,
  payment_type_code: "rent",
  net: "800.00",
  vat_percent: "0",
  gross: "800.00",
  currency: "EUR",
  valid_from: "2026-01-01",
  valid_to: null,
  reason: "initial",
};
const advance: AmountRow = { ...rent, id: "a2", payment_type_code: "operating_cost_advance", net: "150.00", gross: "150.00" };

describe("AmountsPanel", () => {
  beforeEach(() => {
    refresh.mockReset();
    vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-09-28T10:00:00Z") });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("shows the history with the monthly total as of today and records a new rent from a date", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    let body: Record<string, unknown> | null = null;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (init?.method === "POST" && url === `/api/bff/contracts/${CONTRACT}/payments`) {
        body = JSON.parse(String(init.body)) as Record<string, unknown>;
        return jsonResponse({ ...rent, id: "a3", net: body["net"], gross: body["gross"], vat_percent: body["vat_percent"], valid_from: body["valid_from"], reason: body["reason"] }, 201);
      }
      return jsonResponse({ detail: "unexpected" }, 500);
    });
    renderIntl(<AmountsPanel contractId={CONTRACT} amounts={[rent, advance]} paymentTypes={TYPES} canUpdate startDate="2026-01-01" endDate={null} />);

    // Fixed expected value: 800,00 + 150,00 as of 28.09.2026.
    expect(screen.getByTestId("amounts-total")).toHaveTextContent("Summe je Monat (2 Beträge): 950,00 EUR");
    const current = screen.getAllByTestId("amount-row-current");
    expect(current).toHaveLength(2);
    expect(current[0]).toHaveTextContent("Betriebskosten-Vorauszahlung");
    expect(current[1]).toHaveTextContent("Miete");

    const form = within(screen.getByTestId("amount-form"));
    await user.selectOptions(form.getByLabelText("Zahlungsart"), "operating_cost_advance");
    await user.selectOptions(form.getByLabelText("Zahlungsart"), "rent");
    // A kind with an existing amount defaults the reason to an increase.
    expect(form.getByLabelText("Grund")).toHaveValue("increase");
    await user.type(form.getByLabelText("Netto"), "850,00");
    await user.clear(form.getByLabelText("USt in %"));
    await user.type(form.getByLabelText("USt in %"), "19");
    expect(screen.getByTestId("amount-gross")).toHaveTextContent("Brutto: 1.011,50 EUR");
    await user.clear(form.getByLabelText("Gültig ab"));
    await user.type(form.getByLabelText("Gültig ab"), "2026-11-01");
    await user.click(form.getByRole("button", { name: "Betrag erfassen" }));

    await waitFor(() => expect(body).toEqual({ payment_type_code: "rent", net: "850.00", vat_percent: "19", gross: "1011.50", valid_from: "2026-11-01", valid_to: null, reason: "increase" }));
    // The open rent now ends the day before; the new one is listed and the total as of today is unchanged.
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(4));
    expect(screen.getByText("31.10.2026")).toBeInTheDocument();
    expect(screen.getByTestId("amount-row")).toHaveTextContent("Erhöhung");
    expect(screen.getByTestId("amounts-total")).toHaveTextContent("950,00 EUR");
    expect(refresh).toHaveBeenCalled();

    // Moving the reference date shows the future total: 1.011,50 + 150,00.
    await user.clear(screen.getByLabelText("Stichtag"));
    await user.type(screen.getByLabelText("Stichtag"), "2026-11-01");
    expect(screen.getByTestId("amounts-total")).toHaveTextContent("Summe je Monat (2 Beträge): 1.161,50 EUR");
  });

  it("rejects an overlapping period, a date outside the term and a bad amount before calling the API", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ detail: "unexpected" }, 500));
    renderIntl(<AmountsPanel contractId={CONTRACT} amounts={[{ ...rent, valid_to: "2026-12-31" }]} paymentTypes={TYPES} canUpdate startDate="2026-01-01" endDate="2027-12-31" />);
    const form = within(screen.getByTestId("amount-form"));

    await user.type(form.getByLabelText("Netto"), "abc");
    await user.click(form.getByRole("button", { name: "Betrag erfassen" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Bitte den Nettobetrag im Format 1.234,56 angeben.");

    await user.clear(form.getByLabelText("Netto"));
    await user.type(form.getByLabelText("Netto"), "900");
    await user.clear(form.getByLabelText("Gültig ab"));
    await user.type(form.getByLabelText("Gültig ab"), "2025-12-01");
    await user.click(form.getByRole("button", { name: "Betrag erfassen" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Gültig ab muss in der Vertragslaufzeit liegen (01.01.2026 bis 31.12.2027).");

    // The limited rent (until 31.12.2026) is not closed automatically: overlap.
    await user.clear(form.getByLabelText("Gültig ab"));
    await user.type(form.getByLabelText("Gültig ab"), "2026-06-01");
    await user.click(form.getByRole("button", { name: "Betrag erfassen" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Der Zeitraum überschneidet sich mit Miete vom 01.01.2026 bis 31.12.2026.");

    await user.clear(form.getByLabelText("Gültig ab"));
    await user.type(form.getByLabelText("Gültig ab"), "2027-02-01");
    await user.type(form.getByLabelText("Gültig bis"), "2027-01-01");
    await user.click(form.getByRole("button", { name: "Betrag erfassen" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Gültig bis darf nicht vor Gültig ab liegen.");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("shows the API problem message and keeps the rows", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Konflikt", status: 409, detail: "Die Zahlung überschneidet sich mit einer bestehenden Zahlung." }, 409));
    renderIntl(<AmountsPanel contractId={CONTRACT} amounts={[]} paymentTypes={TYPES} canUpdate startDate="2026-01-01" endDate={null} />);
    expect(screen.getByText("Keine Sollbeträge am Vertrag erfasst.")).toBeInTheDocument();
    const form = within(screen.getByTestId("amount-form"));
    await user.type(form.getByLabelText("Netto"), "500");
    await user.click(form.getByRole("button", { name: "Betrag erfassen" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Die Zahlung überschneidet sich mit einer bestehenden Zahlung."));
    expect(screen.getByText("Keine Sollbeträge am Vertrag erfasst.")).toBeInTheDocument();
  });

  it("hides the form without the update permission and without payment types", () => {
    const { unmount } = renderIntl(<AmountsPanel contractId={CONTRACT} amounts={[rent]} paymentTypes={TYPES} canUpdate={false} startDate="2026-01-01" endDate={null} />);
    expect(screen.queryByTestId("amount-form")).not.toBeInTheDocument();
    expect(screen.getByText("800,00 EUR", { selector: "strong" })).toBeInTheDocument();
    unmount();
    renderIntl(<AmountsPanel contractId={CONTRACT} amounts={[]} paymentTypes={[]} canUpdate startDate="2026-01-01" endDate={null} />);
    expect(screen.queryByTestId("amount-form")).not.toBeInTheDocument();
    expect(screen.getByText("Keine Zahlungsarten im Katalog des Mandanten (Einstellungen, Kataloge, Zahlungsarten).")).toBeInTheDocument();
  });
});
