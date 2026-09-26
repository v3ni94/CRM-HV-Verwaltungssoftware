import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DunningSettingsForm, type DunningSettings } from "./DunningSettingsForm";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

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

  it("sends null for inherited fields of an object override and keeps own values", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ ...EMPTY, own: { id: "o1" } }));
    renderIntl(
      <DunningSettingsForm
        propertyId="p1"
        canUpdate
        initial={{
          ...EMPTY,
          threshold_amount: "20.00",
          sources: { levels: "mandant", threshold_amount: "mandant", fee_from_level: "mandant" },
          own: null,
          tenant_default_exists: true,
        }}
      />,
    );
    // Everything inherits by default: the ladder inputs are disabled.
    expect(screen.getByLabelText(/Mahnstufen vom Mandanten übernehmen/)).toBeChecked();
    expect(screen.getByDisplayValue("Erinnerung")).toBeDisabled();
    // Override only the threshold.
    await userEvent.click(screen.getByLabelText("Mahngrenze vom Mandanten übernehmen"));
    const threshold = screen.getByLabelText(/Mahngrenze \(EUR\)/) as HTMLInputElement;
    await userEvent.clear(threshold);
    await userEvent.type(threshold, "50");
    await userEvent.click(screen.getByText("Speichern"));
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
    const body = JSON.parse(String((fetchSpy.mock.calls[0]?.[1] as RequestInit).body));
    expect(body).toEqual({
      property_id: "p1",
      levels: null,
      threshold_amount: "50",
      fee_from_level: null,
      interest_enabled: null,
      interest_base_rate: null,
      interest_spread: null,
    });
    expect(refresh).toHaveBeenCalled();
  });

  it("blocks an object override while no tenant default exists", () => {
    renderIntl(
      <DunningSettingsForm propertyId="p1" canUpdate initial={{ ...EMPTY, tenant_default_exists: false }} />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Zuerst die Mandantenvorgabe speichern");
    expect(screen.getByText("Speichern")).toBeDisabled();
  });

  it("removes an object override after confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(null, { status: 204 }));
    renderIntl(
      <DunningSettingsForm
        propertyId="p1"
        canUpdate
        initial={{
          ...EMPTY,
          tenant_default_exists: true,
          own: {
            id: "o1",
            levels: null,
            threshold_amount: "50.00",
            fee_from_level: null,
            interest_enabled: null,
            interest_base_rate: null,
            interest_spread: null,
          },
        }}
      />,
    );
    await userEvent.click(screen.getByText("Überschreibung entfernen"));
    expect(await screen.findByText("Überschreibung entfernt. Das Objekt erbt wieder die Mandantenvorgabe.")).toBeInTheDocument();
    expect(String(fetchSpy.mock.calls[0]?.[0])).toBe("/api/bff/accounting/dunning-settings?property_id=p1");
    expect((fetchSpy.mock.calls[0]?.[1] as RequestInit).method).toBe("DELETE");
  });
});
