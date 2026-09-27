import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DmsPersonExport } from "./DmsPersonExport";

describe("DmsPersonExport", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends the list and links the import review", async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(jsonResponse({ units: 12, units_with_owner: 11, units_with_tenant: 7, batch_id: 77, created: true, review_url: "https://uebernahme.example/importe/77/" })),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<DmsPersonExport number="523" />);
    await userEvent.click(screen.getByTestId("dms-person-export"));
    expect(await screen.findByTestId("dms-person-export-result")).toHaveTextContent("Übergeben: 12 Einheiten, 11 mit Eigentümer, 7 mit Mieter.");
    expect(screen.getByRole("link", { name: "Import prüfen" })).toHaveAttribute("href", "https://uebernahme.example/importe/77/");
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toBe("/api/bff/integrations/objektakte/objects/523/persons-export");
  });
});
