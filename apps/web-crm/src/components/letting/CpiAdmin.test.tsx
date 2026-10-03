import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CpiAdmin } from "./CpiAdmin";

const ROWS = [
  { series: "VPI", month: "2026-07-01", value: "121.4", source: "Quelle", data_as_of: "2026-08-15", released: true },
  { series: "VPI", month: "2026-08-01", value: "121.9", source: "Quelle", data_as_of: "2026-09-15", released: false },
];

describe("CpiAdmin (AO03 mask)", () => {
  afterEach(() => vi.restoreAllMocks());

  function fill() {
    fireEvent.change(screen.getByLabelText(/^Reihe/), { target: { value: "VPI" } });
    fireEvent.change(screen.getByLabelText("Quelle"), { target: { value: "Statistisches Bundesamt" } });
    fireEvent.change(screen.getByLabelText("Stand der Daten"), { target: { value: "2026-09-15" } });
    fireEvent.change(screen.getByLabelText("CSV-Inhalt"), { target: { value: "2026-08;121,9" } });
  }

  it("imports as unchecked values and shows them with their status", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input).includes("/import") ? jsonResponse({ created: 1, updated: 0, unchanged: 0 }) : jsonResponse(ROWS),
    );
    renderIntl(<CpiAdmin />);
    const importButton = screen.getByRole("button", { name: "Importieren" });
    expect(importButton).toBeDisabled();
    fill();
    fireEvent.click(importButton);
    expect(await screen.findByText(/1 neu, 0 geändert, 0 unverändert/)).toBeInTheDocument();
    expect(await screen.findByText("ungeprüft")).toBeInTheDocument();
    const post = fetchMock.mock.calls.find((c) => String(c[0]).includes("/import")) as [string, RequestInit];
    expect(post[0]).toBe("/api/bff/platform/consumer-price-index/import");
    expect(JSON.parse(String(post[1].body))).toEqual({ series: "VPI", source: "Statistisches Bundesamt", data_as_of: "2026-09-15", csv: "2026-08;121,9" });
  });

  it("releases only after the explicit confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input).includes("/release") ? jsonResponse({ released: 1 }) : jsonResponse(ROWS),
    );
    renderIntl(<CpiAdmin />);
    fireEvent.change(screen.getByLabelText(/^Reihe/), { target: { value: "VPI" } });
    fireEvent.click(screen.getByRole("button", { name: "Werte anzeigen" }));
    await screen.findByTestId("cpi-values");
    const release = screen.getByRole("button", { name: "Freigeben" });
    fireEvent.change(screen.getByLabelText("Freigeben bis Monat"), { target: { value: "2026-08" } });
    expect(release).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/gebe 1 ungeprüfte Werte frei/));
    fireEvent.click(release);
    await waitFor(() => expect(screen.getByText("1 Werte freigegeben.")).toBeInTheDocument());
    const post = fetchMock.mock.calls.find((c) => String(c[0]).includes("/release")) as [string, RequestInit];
    expect(JSON.parse(String(post[1].body))).toEqual({ series: "VPI", up_to: "2026-08-01" });
  });

  it("shows the refusal of the API (not a platform administrator)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "Keine Berechtigung" }, 403));
    renderIntl(<CpiAdmin />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Importieren" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
