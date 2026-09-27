import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { FullImport, kindFromFileName, type RunReport } from "./FullImport";

const API = "/api/bff/imports/immoware24/vollimport";
const precheck = {
  datei: "objektdaten.csv",
  art: "objektdaten",
  ok: true,
  sha256: "ab".repeat(32),
  bytes: 120,
  zeichensatz: "UTF-8",
  trennzeichen: "Semikolon",
  kopfzeile: ["Objekt-Nummer"],
  pflichtspalten_fehlend: [],
  optionale_spalten_fehlend: ["VE-Lage"],
  unbekannte_spalten: ["Extra"],
  zeilen: 869,
  dubletten: [],
  pflichtfelder_fehlend: [],
  hinweise: [],
};
const report: RunReport = {
  apply: false,
  id: null,
  mode: "preview",
  stichtag: "2026-12-31",
  abgebrochen: false,
  dateien: [],
  vorpruefung: [precheck],
  counts: {},
  vorschau: { objekte: { created: 67 }, einheiten: { created: 869 } },
  abgleich: [
    { entitaet: "objekte", soll: 67, ist: 67, uebereinstimmend: 66, differenzen: 1, fehlend: [], doppelt: [], abweichend: [{ schluessel: "100", felder: [{ feld: "name", soll: "A", ist: "B" }] }], zusaetzlich: [], hinweise: [] },
    {
      entitaet: "mietvertraege",
      soll: 2,
      ist: 2,
      uebereinstimmend: 2,
      differenzen: 0,
      fehlend: [],
      doppelt: [],
      abweichend: [],
      zusaetzlich: [],
      hinweise: [],
      je_objekt: [
        { objekt: "100", soll_anzahl: 1, ist_anzahl: 1, soll_summe: "650.00", ist_summe: "650.00", abweichung: false },
        { objekt: "101", soll_anzahl: 1, ist_anzahl: 1, soll_summe: "700.00", ist_summe: "1.00", abweichung: true },
      ],
    },
  ],
  differenzen: 1,
  aktualisiert: [],
  eroeffnungssalden: { status: "entwurf", hinweis: "Entwurf hinter G1", anzahl: { offen: 3, zugeordnet: 5 } },
  dauer_ms: 1234,
};

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("confirm", vi.fn(() => true));
});
afterEach(() => vi.unstubAllGlobals());

describe("kindFromFileName", () => {
  it("guesses the export type from the file name", () => {
    expect(kindFromFileName("Objektdaten_2026.csv")).toBe("objektdaten");
    expect(kindFromFileName("Kontakte Eigentümer.csv")).toBe("eigentuemer");
    expect(kindFromFileName("bankumsaetze.csv")).toBe("bankumsaetze");
    expect(kindFromFileName("Banken.csv")).toBe("bank");
    expect(kindFromFileName("Saldenliste.csv")).toBe("salden");
    expect(kindFromFileName("Mietvertraege_2026.csv")).toBe("mietvertraege");
    expect(kindFromFileName("Eigentümerverträge.csv")).toBe("eigentuemervertraege");
  });
});

describe("FullImport", () => {
  it("runs the pre-check and a dry run and shows preview, reconciliation and balances", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url === API) return Promise.resolve(jsonResponse([]));
      if (url === `${API}/vorpruefung`) return Promise.resolve(jsonResponse({ ok: true, vorpruefung: [precheck] }));
      return Promise.resolve(jsonResponse(report));
    });
    renderIntl(<FullImport />);
    await screen.findByText("Noch kein Vollimport oder Abgleich gespeichert.");
    const input = screen.getByTestId("fullimport-files") as HTMLInputElement;
    await userEvent.upload(input, new File(["Objekt-Nummer;Objekt\n"], "objektdaten.csv", { type: "text/csv" }));
    expect(screen.getByTestId("fullimport-picked")).toHaveTextContent("objektdaten.csv");
    expect((screen.getByLabelText("Exporttyp für objektdaten.csv") as HTMLSelectElement).value).toBe("objektdaten");
    await userEvent.click(screen.getByTestId("fullimport-precheck-button"));
    await waitFor(() => expect(screen.getByTestId("fullimport-precheck")).toHaveTextContent("869"));
    expect(screen.getByTestId("fullimport-precheck")).toHaveTextContent("Unbekannte Spalten: Extra");

    expect(screen.getByTestId("fullimport-preview-button")).toBeDisabled();
    await userEvent.type(screen.getByTestId("fullimport-cutoff"), "2026-12-31");
    await userEvent.click(screen.getByTestId("fullimport-preview-button"));
    await waitFor(() => expect(screen.getByTestId("fullimport-result")).toBeInTheDocument());
    expect(screen.getByTestId("fullimport-preview")).toHaveTextContent("created 67");
    expect(screen.getByTestId("fullimport-reconciliation")).toHaveTextContent("objekte");
    expect(screen.getByRole("status")).toHaveTextContent("1 Differenzen");
    expect(screen.getByTestId("fullimport-balances")).toHaveTextContent("5 Einträge einem Vertrag zugeordnet, 3 offene Einträge");
    expect(screen.getByTestId("fullimport-per-object-mietvertraege")).toHaveTextContent("Verträge je Objekt");
    expect(screen.getByTestId("fullimport-per-object-mietvertraege")).toHaveTextContent("(1)");
    const previewCall = fetchMock.mock.calls.find((c) => String(c[0]).includes("mode=preview"));
    expect(previewCall).toBeDefined();
    expect(screen.getByTestId("fullimport-apply-button")).toBeEnabled();
  });

  it("lists stored runs with differences badge", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse([
          { id: "01920000-0000-7000-8000-0000000000aa", created_at: "2026-09-27T10:00:00Z", status: "applied", cutoff_date: "2026-12-31", files: [{ datei: "o.csv", art: "objektdaten", zeilen: 869 }], differences: 0, duration_ms: 5000 },
        ]),
      ),
    );
    renderIntl(<FullImport />);
    await waitFor(() => expect(screen.getByTestId("fullimport-runs")).toHaveTextContent("objektdaten (869)"));
    expect(screen.getByTestId("fullimport-runs")).toHaveTextContent("übernommen");
  });
});
