import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

import { DepositInterestRatesAdmin } from "./DepositInterestRatesAdmin";

describe("DepositInterestRatesAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists rates read only without the form", () => {
    renderIntl(<DepositInterestRatesAdmin rates={[{ id: "r1", year: 2025, rate: "1.00000", note: "zu prüfen" }]} canManage={false} />);
    expect(screen.getByText("2025")).toBeInTheDocument();
    expect(screen.getByText("1,00000 %")).toBeInTheDocument();
    expect(screen.getByText("zu prüfen")).toBeInTheDocument();
    expect(screen.queryByText("Zinssatz setzen")).not.toBeInTheDocument();
  });

  it("saves a rate per year with a German decimal comma", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: "r1", year: 2026, rate: "0.50000", note: null }, 200));
    renderIntl(<DepositInterestRatesAdmin rates={[]} canManage={true} />);
    expect(screen.getByText("Noch kein Referenzzinssatz hinterlegt.")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Jahr"));
    await userEvent.type(screen.getByLabelText("Jahr"), "2026");
    await userEvent.type(screen.getByLabelText("Zinssatz in Prozent"), "0,5");
    await userEvent.click(screen.getByText("Speichern"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/bff/deposit-interest-rates/2026");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual({ rate: "0.5", note: null });
    expect(await screen.findByText("Der Zinssatz wurde gespeichert.")).toBeInTheDocument();
  });

  it("refuses a rate above 100 percent before sending", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderIntl(<DepositInterestRatesAdmin rates={[]} canManage={true} />);
    await userEvent.type(screen.getByLabelText("Zinssatz in Prozent"), "101");
    expect(screen.getByText("Speichern")).toBeDisabled();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
