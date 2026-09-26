import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { KontakteCard, ListImports, ObjektdatenCard, roleFromFileName, ZuordnungCard } from "./ListImports";

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
    expect(screen.getByTestId("objektdaten-report-counts")).toHaveTextContent("Objekte übersprungen");
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
  it("prefills the role from the file name, sends one role per file and lists rows with notes", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        mode: "preview",
        apply: false,
        counts: { created: 2, invalid: 1 },
        kontakte: [
          { datei: "eigentuemer.csv", zeile: 2, id: "1", name: "Max Muster", rolle: "eigentuemer", status: "created", hinweise: ["Reihenfolge Vorname Nachname angenommen"] },
          { datei: "Mieter.csv", zeile: 3, id: "9", name: "Erika", rolle: "mieter", status: "created", hinweise: [] },
        ],
      }),
    );
    renderIntl(<KontakteCard />);
    expect(screen.getByTestId("kontakte-apply")).toBeDisabled();
    await userEvent.upload(screen.getByLabelText(/Kontaktlisten/), [csv("eigentuemer.csv"), csv("Mieter.csv"), csv("export.csv")]);
    expect(screen.getByLabelText("Rolle für Mieter.csv")).toHaveValue("mieter");
    expect(screen.getByLabelText("Rolle für export.csv")).toHaveValue("sonstige");
    await userEvent.selectOptions(screen.getByLabelText("Rolle für export.csv"), "dienstleister");
    await userEvent.click(screen.getByTestId("kontakte-test"));
    await screen.findByTestId("kontakte-report-mode");
    const body = fetchMock.mock.calls[0]![1].body as FormData;
    expect(body.getAll("roles")).toEqual(["eigentuemer", "mieter", "dienstleister"]);
    expect(body.getAll("files").map((f) => (f as File).name)).toEqual(["eigentuemer.csv", "Mieter.csv", "export.csv"]);
    const table = screen.getByTestId("kontakte-notes");
    expect(table).toHaveTextContent("Max Muster");
    expect(table).not.toHaveTextContent("Erika");
    expect(screen.getByTestId("kontakte-apply")).toBeEnabled();
  });

  it("maps file names to roles", () => {
    expect(roleFromFileName("Eigentümer 2026.csv")).toBe("eigentuemer");
    expect(roleFromFileName("banken.csv")).toBe("bank");
    expect(roleFromFileName("Dienstleister.csv")).toBe("dienstleister");
  });
});

describe("ZuordnungCard", () => {
  it("sends file, start date and flag as FormData and shows counts and collapsible lists", async () => {
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        url.includes("mode=apply")
          ? jsonResponse({ type: "about:blank", title: "Fehler", status: 422, detail: "Datei unlesbar." }, 422)
          : jsonResponse({
              mode: "preview",
              apply: false,
              start_date: "2026-01-01",
              start_date_assumed: false,
              einheiten_gesamt: 3,
              eigentuemer_zugeordnet: 1,
              mieter_zugeordnet: 0,
              leerstand: 0,
              counts: { vertraege_angelegt: 1, zahlungen_cent_hoa_fee: 25000 },
              nicht_gefunden: [{ objekt: "81", ve: "2", zeile: 3, rolle: "Eigentümer", name: "Niemand, Nora" }],
              mehrdeutig: [{ objekt: "81", ve: "3", zeile: 4, rolle: "Eigentümer", name: "Meier, Hans", kandidaten: ["12 Meier, Hans", "13 Meier, Hans"] }],
              konflikte: [{ objekt: "82", ve: "1", zeile: 5, rolle: "Mieter", name: "Mieter, Erika", grund: "Der Vermieter ist nicht eindeutig." }],
              hinweise: [],
            }),
      ),
    );
    renderIntl(<ZuordnungCard />);
    const date = screen.getByLabelText(/^Vertragsbeginn/);
    expect(date).toHaveValue(`${new Date().getFullYear()}-01-01`);
    await userEvent.upload(screen.getByLabelText(/Objektliste \(csv\) für die Zuordnung/), csv("objektdaten.csv"));
    await userEvent.clear(date);
    await userEvent.type(date, "2026-01-01");
    await userEvent.click(screen.getByTestId("zuordnung-test"));
    await screen.findByTestId("zuordnung-report-mode");
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/bff/imports/immoware24/lists/zuordnung?mode=preview");
    const body = fetchMock.mock.calls[0]![1].body as FormData;
    expect(body.get("start_date")).toBe("2026-01-01");
    expect(body.get("skip_handed_over")).toBe("false");
    expect((body.get("file") as File).name).toBe("objektdaten.csv");
    const counts = screen.getByTestId("zuordnung-report-counts");
    expect(counts).toHaveTextContent("Eigentümer zugeordnet");
    expect(counts).toHaveTextContent("Verträge angelegt");
    expect(counts).toHaveTextContent("250,00 EUR");
    expect(screen.getByTestId("zuordnung-start")).toHaveTextContent("01.01.2026");
    expect(screen.getByTestId("zuordnung-not-found-details")).not.toHaveAttribute("open");
    expect(screen.getByTestId("zuordnung-not-found")).toHaveTextContent("Niemand, Nora");
    expect(screen.getByTestId("zuordnung-ambiguous")).toHaveTextContent("12 Meier, Hans, 13 Meier, Hans");
    expect(screen.getByTestId("zuordnung-conflicts")).toHaveTextContent("Vermieter ist nicht eindeutig");

    await userEvent.click(screen.getByTestId("zuordnung-apply"));
    expect(window.confirm).toHaveBeenCalledWith("Daten werden geschrieben. Fortfahren?");
    expect(await screen.findByRole("alert")).toHaveTextContent("Datei unlesbar.");
  });
});

describe("ListImports", () => {
  it("renders the order hint and the three sections in order", () => {
    renderIntl(<ListImports />);
    expect(screen.getByTestId("immoware-lists-order")).toHaveTextContent("erst Testlauf, dann Übernehmen");
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(["1. Objekte und Einheiten", "2. Kontakte", "3. Zuordnung Eigentümer und Mieter"]);
  });
});
