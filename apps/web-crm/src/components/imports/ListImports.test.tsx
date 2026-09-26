import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { KontakteCard, ObjektdatenCard } from "./ListImports";

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("confirm", vi.fn(() => true));
});
afterEach(() => vi.unstubAllGlobals());

const csv = (name: string) => new File(["Objekt-Nummer;Objekt\n"], name, { type: "text/csv" });

describe("ObjektdatenCard", () => {
  it("runs a test run, shows skipped objects and notes, then enables apply with confirmation", async () => {
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        jsonResponse(
          url.includes("mode=apply")
            ? { mode: "apply", apply: true, import_run_id: "01920000-0000-7000-8000-0000000000aa", counts: { property_created: 1, unit_created: 2 }, objekte: [] }
            : {
                mode: "preview",
                apply: false,
                counts: { property_created: 1, property_skipped: 1, unit_created: 2 },
                objekte: [
                  { objekt: "10012", nummer: null, bezeichnung: "Testweg 1", status: "übersprungen", hinweise: [], probleme: ["Objektnummer '10012' ist nicht dreistellig"], einheiten: {} },
                  { objekt: "81", nummer: "081", bezeichnung: "Musterstraße 2", status: "created", hinweise: ["Objektnummer 81 mit führenden Nullen als 081 angelegt"], einheiten: { created: 2 } },
                ],
              },
        ),
      ),
    );
    renderIntl(<ObjektdatenCard />);
    const apply = screen.getByTestId("objektdaten-apply");
    expect(apply).toBeDisabled();
    await userEvent.upload(screen.getByLabelText("Objektliste (csv)"), csv("objektdaten.csv"));
    await userEvent.type(screen.getByLabelText(/Nummernzuordnung/), "10012=012");
    await userEvent.click(screen.getByLabelText(/Abgegebene Objekte/));
    await userEvent.click(screen.getByTestId("objektdaten-test"));

    expect(await screen.findByTestId("objektdaten-report-mode")).toHaveTextContent("Testlauf, es wurde nichts gespeichert.");
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/bff/imports/immoware24/lists/objektdaten?mode=preview");
    const body = fetchMock.mock.calls[0]![1].body as FormData;
    expect(body.get("number_map")).toBe("10012=012");
    expect(body.get("skip_handed_over")).toBe("true");
    expect((body.get("file") as File).name).toBe("objektdaten.csv");
    expect(screen.getByTestId("objektdaten-skipped")).toHaveTextContent("10012");
    expect(screen.getByTestId("objektdaten-skipped")).toHaveTextContent("nicht dreistellig");
    expect(screen.getByTestId("objektdaten-notes")).toHaveTextContent("führenden Nullen");
    expect(screen.getByText("Objekte übersprungen")).toBeInTheDocument();

    expect(apply).toBeEnabled();
    await userEvent.click(apply);
    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() => expect(fetchMock.mock.calls.at(-1)![0]).toContain("mode=apply"));
    expect(await screen.findByText("Übernommen. Der Lauf ist unter Importe aufgeführt.")).toBeInTheDocument();
    expect(screen.getByText("Importlauf öffnen")).toHaveAttribute("href", "/importe/01920000-0000-7000-8000-0000000000aa");
    // After apply the button waits for a new test run.
    expect(apply).toBeDisabled();
  });

  it("locks apply again when the input changes after the test run", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ mode: "preview", apply: false, counts: {}, objekte: [] }));
    renderIntl(<ObjektdatenCard />);
    await userEvent.upload(screen.getByLabelText("Objektliste (csv)"), csv("a.csv"));
    await userEvent.click(screen.getByTestId("objektdaten-test"));
    await screen.findByTestId("objektdaten-report-mode");
    expect(screen.getByTestId("objektdaten-apply")).toBeEnabled();
    await userEvent.type(screen.getByLabelText(/Nummernzuordnung/), "1=001");
    expect(screen.getByTestId("objektdaten-apply")).toBeDisabled();
  });
});

describe("KontakteCard", () => {
  it("sends one role per file and lists rows with notes", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        mode: "preview",
        apply: false,
        counts: { created: 2, invalid: 1 },
        kontakte: [
          { datei: "eigentuemer.csv", zeile: 2, id: "1", name: "Max Muster", rolle: "eigentuemer", status: "created", hinweise: ["Reihenfolge Vorname Nachname angenommen"] },
          { datei: "mieter.csv", zeile: 3, id: "9", name: "Erika", rolle: "mieter", status: "created", hinweise: [] },
        ],
      }),
    );
    renderIntl(<KontakteCard />);
    expect(screen.getByTestId("kontakte-apply")).toBeDisabled();
    await userEvent.upload(screen.getByLabelText("Datei 1 (csv)"), csv("eigentuemer.csv"));
    await userEvent.upload(screen.getByLabelText("Datei 2 (csv)"), csv("mieter.csv"));
    await userEvent.selectOptions(screen.getByLabelText("Rolle für Datei 2"), "mieter");
    await userEvent.click(screen.getByTestId("kontakte-test"));
    await screen.findByTestId("kontakte-report-mode");
    const body = fetchMock.mock.calls[0]![1].body as FormData;
    expect(body.getAll("roles")).toEqual(["eigentuemer", "mieter"]);
    expect(body.getAll("files").map((f) => (f as File).name)).toEqual(["eigentuemer.csv", "mieter.csv"]);
    const table = screen.getByTestId("kontakte-notes");
    expect(table).toHaveTextContent("Max Muster");
    expect(table).not.toHaveTextContent("Erika");
    expect(screen.getByTestId("kontakte-apply")).toBeEnabled();
  });
});
