import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DunningSettingsForm, type DunningSettings } from "./DunningSettingsForm";

const EMPTY: DunningSettings = {
  levels: [{ level: 1, min_days_overdue: 7, text: "Erinnerung", fee_amount: null }],
  threshold_amount: "0.00",
  fee_from_level: null,
  interest_enabled: false,
  interest_base_rate: null,
  interest_spread: null,
  status: "kein_betrag_hinterlegt",
};

describe("DunningSettingsForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("keeps the interest switch disabled until a base rate is entered", async () => {
    renderIntl(<DunningSettingsForm initial={EMPTY} canUpdate />);
    const toggle = screen.getByLabelText("Verzugszins aktiv") as HTMLInputElement;
    expect(toggle).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Basiszinssatz (%, vom Betreiber zu pflegen, ändert sich halbjährlich)"), "3.62");
    expect(toggle).not.toBeDisabled();
  });

  it("loads presets without any fee amount or base rate and shows the hint", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({
        levels: [
          { level: 1, min_days_overdue: 7, text: "Zahlungserinnerung", fee_amount: null },
          { level: 2, min_days_overdue: 14, text: "1. Mahnung", fee_amount: null },
        ],
        threshold_amount: "0.00",
        fee_from_level: 2,
        interest_enabled: false,
        interest_base_rate: null,
        interest_spread: "5",
        status: "kein_betrag_hinterlegt",
      }),
    );
    renderIntl(<DunningSettingsForm initial={EMPTY} canUpdate />);
    await userEvent.click(screen.getByText("Vorschlagswerte laden"));
    expect(await screen.findByText("Vorschlagswerte geladen. Beträge und Basiszinssatz bitte selbst eintragen.")).toBeInTheDocument();
    expect(screen.getByDisplayValue("1. Mahnung")).toBeInTheDocument();
    expect((screen.getByLabelText("Gebühr ab Stufe") as HTMLInputElement).value).toBe("2");
  });

  it("sets the spread to the consumer preset value without touching the base rate", async () => {
    renderIntl(<DunningSettingsForm initial={EMPTY} canUpdate />);
    await userEvent.click(screen.getByText("Verbraucher (5)"));
    expect((screen.getByLabelText("Aufschlag (Prozentpunkte)") as HTMLInputElement).value).toBe("5");
    expect((screen.getByLabelText("Basiszinssatz (%, vom Betreiber zu pflegen, ändert sich halbjährlich)") as HTMLInputElement).value).toBe("");
  });

  it("disables editing when the caller has no update permission", () => {
    renderIntl(<DunningSettingsForm initial={EMPTY} canUpdate={false} />);
    expect(screen.getByText("Vorschlagswerte laden")).toBeDisabled();
    expect(screen.getByText("Speichern")).toBeDisabled();
  });
});
