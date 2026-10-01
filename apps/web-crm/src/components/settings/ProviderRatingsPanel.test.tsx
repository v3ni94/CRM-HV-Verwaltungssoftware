import { screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ProviderRatingsPanel } from "./ProviderRatingsPanel";

const NOTE = "Bewertungen sind interne Einschätzungen der Verwaltung. Die Anzeige gilt nur für die Verwaltung, nicht für Dienstleister oder Dritte, und enthält keine Freitexte.";

describe("ProviderRatingsPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows count, mean and distribution per provider without free text", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({
        mode: "staff",
        enabled: true,
        note: NOTE,
        providers: [
          {
            provider_contact_id: "01920000-0000-7000-8000-0000000000a1",
            provider_name: "Heizung Müller GmbH",
            rated_count: 2,
            average: "4.5",
            distribution: { "1": 0, "2": 0, "3": 0, "4": 1, "5": 1 },
          },
        ],
      }),
    );
    renderIntl(<ProviderRatingsPanel />);
    const panel = await screen.findByTestId("provider-ratings");
    expect(await screen.findByText("Heizung Müller GmbH")).toBeInTheDocument();
    expect(fetchMock.mock.calls.at(0)?.[0]).toBe("/api/bff/portal-admin/provider-ratings");
    expect(panel).toHaveTextContent("4,5");
    expect(panel).toHaveTextContent("5: 1, 4: 1, 3: 0, 2: 0, 1: 0");
    expect(panel).toHaveTextContent("nicht für Dienstleister oder Dritte");
  });

  it("states that the display is switched off and shows no data", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ mode: "off", enabled: false, note: NOTE, providers: [] }));
    renderIntl(<ProviderRatingsPanel />);
    expect(await screen.findByText("Die Anzeige ist ausgeschaltet.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows an empty notice and errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ mode: "staff", enabled: true, note: NOTE, providers: [] }));
    const { unmount } = renderIntl(<ProviderRatingsPanel />);
    expect(await screen.findByText("Noch keine bewerteten Aufträge.")).toBeInTheDocument();
    unmount();
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ title: "Verboten", status: 403, detail: "Keine Berechtigung." }, 403));
    renderIntl(<ProviderRatingsPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Keine Berechtigung.");
  });
});
