import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { HandoverMeterTransfer } from "./HandoverMeterTransfer";

const BASE = "/api/bff/handover/protocols/01920000-0000-7000-8000-000000000060";
const ROW = "01920000-0000-7000-8000-00000000000a";
const ROW2 = "01920000-0000-7000-8000-00000000000b";

describe("HandoverMeterTransfer", () => {
  afterEach(() => vi.restoreAllMocks());

  it("takes readings over after confirmation and lists created and skipped rows", async () => {
    const calls: { url: string; method: string; body: string | null }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? init.body : null });
      if (url === `${BASE}/meters/transfer` && method === "POST")
        return jsonResponse({
          created: [{ item_id: ROW, number: "E-1", meter_type: "electricity", meter_number: "E 1", value: "12345.678", read_at: "2026-09-28" }],
          skipped: [{ item_id: ROW2, number: "XX", meter_type: "gas", reason: "no_meter" }],
          already_transferred: [],
        });
      return jsonResponse({}, 404);
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onChanged = vi.fn(async () => {});
    renderIntl(
      <HandoverMeterTransfer
        base={BASE}
        meters={[
          { id: ROW, number: "E-1", meter_reading_id: null },
          { id: ROW2, number: "XX", meter_reading_id: null },
        ]}
        hasUnit
        cancelled={false}
        onChanged={onChanged}
        onError={vi.fn()}
      />,
    );
    expect(screen.getByText("2 noch nicht übernommen, 0 übernommen.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Zählerstände übernehmen" }));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("2 Zählerstände"));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(JSON.parse(calls.find((c) => c.method === "POST")?.body ?? "{}")).toEqual({ confirm: true });
    const result = await screen.findByTestId("handover-meter-transfer-result");
    expect(result).toHaveTextContent("1 übernommen, 1 übersprungen, 0 bereits übernommen.");
    expect(result).toHaveTextContent("electricity, Nr. E-1: 12345.678 am 28.09.2026 (Zähler E 1)");
    expect(result).toHaveTextContent("gas, Nr. XX: kein Zähler mit dieser Nummer in der Einheit");
  });

  it("does nothing without confirmation and is disabled without unit or when everything is done", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}, 404));
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const { unmount } = renderIntl(
      <HandoverMeterTransfer base={BASE} meters={[{ id: ROW, meter_reading_id: null }]} hasUnit cancelled={false} onChanged={vi.fn(async () => {})} onError={vi.fn()} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Zählerstände übernehmen" }));
    expect(fetchSpy).not.toHaveBeenCalled();
    unmount();
    renderIntl(
      <HandoverMeterTransfer base={BASE} meters={[{ id: ROW, meter_reading_id: "r1" }]} hasUnit={false} cancelled={false} onChanged={vi.fn(async () => {})} onError={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "Zählerstände übernehmen" })).toBeDisabled();
    expect(screen.getByText("0 noch nicht übernommen, 1 übernommen.")).toBeInTheDocument();
    expect(screen.getByText("Ohne Einheit aus dem Bestand gibt es keine Zähler, in die übernommen werden kann.")).toBeInTheDocument();
  });
});
