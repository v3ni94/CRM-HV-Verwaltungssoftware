import { fireEvent, screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { VatOptionHistory, type VatOptionRow } from "./VatOptionHistory";

const UNIT = "11111111-1111-7111-8111-111111111111";
const ROWS: VatOptionRow[] = [
  { id: "a", option: "commercial_full_vat", occupant: "contract", valid_from: "2026-01-01", valid_to: null },
  { id: "b", option: "none", occupant: "vacancy", valid_from: "2024-03-01", valid_to: "2025-12-31" },
];

describe("VatOptionHistory", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the periods with option, occupant and German dates", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(ROWS));
    renderIntl(<VatOptionHistory unitId={UNIT} canEdit={false} />);
    const rows = await screen.findAllByTestId("vat-history-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Gewerbe mit vollem Umsatzsteuersatz");
    expect(rows[0]).toHaveTextContent("Vertrag");
    expect(rows[0]).toHaveTextContent("01.01.2026");
    expect(rows[0]).toHaveTextContent("offen");
    expect(rows[1]).toHaveTextContent("Leerstand");
    expect(rows[1]).toHaveTextContent("31.12.2025");
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/units/${UNIT}/vat-options`);
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]));
    renderIntl(<VatOptionHistory unitId={UNIT} canEdit={false} />);
    expect(await screen.findByText("Keine Umsatzsteueroptionen erfasst.")).toBeInTheDocument();
  });

  it("adds a period and reloads", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse({}, 201))
      .mockResolvedValueOnce(jsonResponse([ROWS[0]]));
    renderIntl(<VatOptionHistory unitId={UNIT} canEdit />);
    await screen.findByText("Keine Umsatzsteueroptionen erfasst.");
    fireEvent.change(screen.getByLabelText("gültig ab"), { target: { value: "2026-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Zeitraum hinzufügen" }));
    await screen.findByTestId("vat-history-row");
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(`/api/bff/units/${UNIT}/vat-options`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      option: "commercial_full_vat",
      occupant: "contract",
      valid_from: "2026-01-01",
      valid_to: null,
    });
  });

  it("validates the period order and shows the overlap message of the API", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse({ title: "Konflikt", status: 409, detail: "Der Zeitraum überschneidet sich." }, 409));
    renderIntl(<VatOptionHistory unitId={UNIT} canEdit />);
    await screen.findByText("Keine Umsatzsteueroptionen erfasst.");
    fireEvent.change(screen.getByLabelText("gültig ab"), { target: { value: "2026-05-01" } });
    fireEvent.change(screen.getByLabelText("gültig bis"), { target: { value: "2026-04-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Zeitraum hinzufügen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Das Ende liegt vor dem Beginn.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText("gültig bis"), { target: { value: "2026-06-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Zeitraum hinzufügen" }));
    expect(await screen.findByText("Der Zeitraum überschneidet sich.")).toBeInTheDocument();
  });
});
