import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { Co2SplitPanel } from "./Co2SplitPanel";

describe("Co2SplitPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("calculates the split via the API and shows euro amounts (D10)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ tenant_percent: 90, tenant: "90.00", landlord: "10.00", rule_version: "co2-2023", note: "Anwendbarkeit prüfen (H04)." }),
    );
    renderIntl(<Co2SplitPanel />);
    const button = screen.getByText("Aufteilung berechnen");
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Spezifischer CO2-Ausstoß/), "12,0");
    await userEvent.type(screen.getByLabelText("CO2-Kosten (EUR)"), "100,00");
    await userEvent.click(button);
    await waitFor(() => expect(screen.getByTestId("co2-result")).toHaveTextContent("90 %"));
    expect(screen.getByTestId("co2-result")).toHaveTextContent("10,00");
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/bff/statements/co2-split");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ specific_emissions: "12.0", costs: "100.00" });
  });

  it("shows the API refusal", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ title: "Validierung", status: 422, detail: "Werte dürfen nicht negativ sein" }, 422));
    renderIntl(<Co2SplitPanel />);
    await userEvent.type(screen.getByLabelText(/Spezifischer CO2-Ausstoß/), "5");
    await userEvent.type(screen.getByLabelText("CO2-Kosten (EUR)"), "10");
    await userEvent.click(screen.getByText("Aufteilung berechnen"));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
