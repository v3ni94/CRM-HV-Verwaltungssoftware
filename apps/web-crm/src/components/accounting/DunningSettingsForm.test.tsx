import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DunningSettingsForm, reminderFeeViolation, type DunningSettings } from "./DunningSettingsForm";

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

  it("previews the text of a level with sample items and shows the claim table", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({
        level: 1,
        paragraphs: [
          "Sehr geehrte Damen und Herren,",
          "für Objekt 000 Musterobjekt, Einheit 01 sind nach unseren Unterlagen die nachfolgend aufgeführten Beträge noch offen.",
          "Bitte überweisen Sie den Gesamtbetrag von 700,00 EUR auf das Ihnen bekannte Konto.",
          "Sollten Sie den Betrag in der Zwischenzeit bereits überwiesen haben, betrachten Sie dieses Schreiben bitte als gegenstandslos.",
        ],
        table: {
          header: ["Posten", "Fälligkeit", "Betrag"],
          rows: [
            ["Hausgeld Februar 2026", "03.02.2026", "350,00 EUR"],
            ["Hausgeld März 2026", "03.03.2026", "350,00 EUR"],
            ["Summe", "", "700,00 EUR"],
          ],
        },
        standard_request: "Bitte überweisen Sie den Gesamtbetrag von {gesamtbetrag} {frist} {bankverbindung}.",
        placeholders: { frist: "", bankverbindung: "" },
        hinweis: "Entwurf, kein Versand",
      }),
    );
    renderIntl(<DunningSettingsForm initial={EMPTY} canUpdate />);
    await userEvent.click(screen.getByText("Vorschau"));
    expect(await screen.findByRole("heading", { name: "Vorschau Stufe 1 mit Beispielposten" })).toBeInTheDocument();
    expect(screen.getByText("Hausgeld Februar 2026")).toBeInTheDocument();
    expect(screen.getByText("700,00 EUR")).toBeInTheDocument();
    expect(screen.getByText("Bitte überweisen Sie den Gesamtbetrag von 700,00 EUR auf das Ihnen bekannte Konto.")).toBeInTheDocument();
    expect(screen.getByText("Entwurf, kein Versand")).toBeInTheDocument();
    const body = JSON.parse(String((fetchSpy.mock.calls[0]?.[1] as RequestInit).body));
    expect(body).toEqual({ level: 1, text: "Erinnerung", letter_text: null, fee_amount: null, payment_days: null });
    // The hint names the placeholders; the preview panel can be closed again.
    expect(screen.getByText(/Platzhalter: \{frist\}, \{bankverbindung\}/)).toBeInTheDocument();
    await userEvent.click(screen.getByText("Vorschau schließen"));
    expect(screen.queryByText("Hausgeld Februar 2026")).not.toBeInTheDocument();
  });

  it("shows the API problem when a letter text has an unknown placeholder", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ code: "MHVP-VAL-0001", detail: "Unbekannte Platzhalter im Brieftext: frsit." }, 422),
    );
    renderIntl(<DunningSettingsForm initial={EMPTY} canUpdate />);
    await userEvent.click(screen.getByText("Vorschau"));
    expect(await screen.findByRole("alert")).toHaveTextContent("frsit");
  });

  it("blocks saving a fee on the payment reminder (level 1) with a German message", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    renderIntl(<DunningSettingsForm initial={EMPTY} canUpdate />);
    await userEvent.type(screen.getByLabelText("Gebühr ab Stufe"), "1");
    await userEvent.click(screen.getByText("Speichern"));
    expect(
      await screen.findByText(/Die Zahlungserinnerung \(Stufe 1\) ist immer ohne Gebühr und ohne Zinsen/),
    ).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("detects reminder fee violations", () => {
    const lv = { level: 1, min_days_overdue: 7, text: "E", fee_amount: null };
    expect(reminderFeeViolation("1", [lv])).toBe(true);
    expect(reminderFeeViolation("2", [{ ...lv, fee_amount: "2,50" }])).toBe(true);
    expect(reminderFeeViolation("2", [{ ...lv, fee_amount: "0.00" }])).toBe(false);
    expect(reminderFeeViolation("", [lv])).toBe(false);
  });

  it("prefills the default payment deadline for a new level and shows the hint", async () => {
    renderIntl(<DunningSettingsForm initial={EMPTY} canUpdate />);
    await userEvent.click(screen.getByText("Stufe hinzufügen"));
    expect(screen.getByDisplayValue("10")).toBeInTheDocument();
    expect(screen.getByText(/berechnet das Zahlungsdatum aus Briefdatum/)).toBeInTheDocument();
  });
});
