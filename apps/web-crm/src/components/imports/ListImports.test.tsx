import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AdressenCard, KontakteCard, ListImports, ObjektdatenCard, OpenAssignments, roleFromFileName, ZUORDNUNG_STORAGE_KEY, ZuordnungCard, type OpenAssignment } from "./ListImports";

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
    expect(screen.queryByTestId("objektdaten-report-file-notes")).toBeNull();
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
        counts: { created: 2, invalid: 1, duplicate: 1 },
        datei_hinweise: ["mieter.csv: Datei als Windows-1252 (ANSI) gelesen, nicht als UTF-8", "mieter.csv: Trennzeichen Komma erkannt"],
        kontakte: [
          { datei: "mieter.csv", zeile: 4, id: "1", name: "Max Muster", rolle: "mieter", status: "duplicate", hinweise: ["id 1 bereits in Zeile 2, nicht erneut angelegt"] },
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
    expect(table).toHaveTextContent("Duplikat");
    expect(table).toHaveTextContent("id 1 bereits in Zeile 2, nicht erneut angelegt");
    expect(table).not.toHaveTextContent("Erika");
    const notes = screen.getByTestId("kontakte-report-file-notes");
    expect(notes).toHaveTextContent("Windows-1252");
    expect(notes).toHaveTextContent("Trennzeichen Komma erkannt");
    expect(screen.getByText("Duplikate in der Datei")).toBeInTheDocument();
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
  it("renders the order hint and the sections in order", () => {
    renderIntl(<ListImports />);
    expect(screen.getByTestId("immoware-lists-order")).toHaveTextContent("erst Testlauf, dann Übernehmen");
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(["1. Objekte und Einheiten",
      "1a. Adressen nachtragen", "2. Kontakte", "3. Zuordnung Eigentümer und Mieter"]);
  });
});

describe("AdressenCard", () => {
  it("derives addresses from names without a body and uploads an address list", async () => {
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        jsonResponse({
          mode: url.includes("mode=apply") ? "apply" : "preview",
          apply: url.includes("mode=apply"),
          counts: {
            filled: 1,
            skipped: 0,
            unrecognised: 1,
            conflicts: 0,
            unknown: 0,
          },
          filled: [
            {
              number: "082",
              name: "Shalomweg 3",
              street: "Shalomweg",
              house_number: "3",
            },
          ],
          unrecognised: [{ number: "084", name: "Garagenhof Nord" }],
          conflicts: url.includes("adressen?")
            ? [
                {
                  line: 3,
                  number: "083",
                  field: "Straße",
                  current: "Am Panke Park",
                  list: "Andere Straße",
                },
              ]
            : [],
          unknown: [],
          problems: [],
        }),
      ),
    );
    renderIntl(<AdressenCard />);
    expect(screen.getByTestId("adressen-derive-apply")).toBeDisabled();
    await userEvent.click(screen.getByTestId("adressen-derive-test"));
    expect(await screen.findByTestId("adressen-report-mode")).toHaveTextContent(
      "Testlauf",
    );
    expect(fetchMock.mock.calls[0]![0]).toBe(
      "/api/bff/imports/immoware24/lists/adressen-ableiten?mode=preview",
    );
    expect(fetchMock.mock.calls[0]![1].body).toBeUndefined();
    expect(screen.getByTestId("adressen-filled")).toHaveTextContent(
      "Shalomweg",
    );
    expect(screen.getByTestId("adressen-unrecognised")).toHaveTextContent(
      "Garagenhof Nord",
    );
    await userEvent.click(screen.getByTestId("adressen-derive-apply"));
    await waitFor(() =>
      expect(fetchMock.mock.calls.at(-1)![0]).toContain(
        "adressen-ableiten?mode=apply",
      ),
    );

    expect(screen.getByTestId("adressen-list-apply")).toBeDisabled();
    await userEvent.upload(
      screen.getByLabelText("Adressliste (csv oder xlsx)"),
      csv("adressen.csv"),
    );
    await userEvent.click(screen.getByTestId("adressen-list-test"));
    await waitFor(() =>
      expect(fetchMock.mock.calls.at(-1)![0]).toBe(
        "/api/bff/imports/immoware24/lists/adressen?mode=preview",
      ),
    );
    expect(
      ((fetchMock.mock.calls.at(-1)![1].body as FormData).get("file") as File)
        .name,
    ).toBe("adressen.csv");
    expect(await screen.findByTestId("adressen-conflicts")).toHaveTextContent(
      "Andere Straße",
    );
    expect(screen.getByTestId("adressen-list-apply")).toBeEnabled();
  });
});

const OPEN: OpenAssignment[] = [
  {
    objekt: "83",
    ve: "1",
    zeile: 2,
    rolle: "Eigentümer",
    name: "Doppel, Dora",
    unit_id: "01920000-0000-7000-8000-000000000001",
    role: "eigentuemer",
    grund: "mehrdeutig",
    zahlbetrag: "275,50",
    amount_cents: 27550,
    kandidaten: [
      { contact_id: "01920000-0000-7000-8000-0000000000c1", display_name: "Doppel, Dora", address: "Ahornweg 1, 52062 Aachen" },
      { contact_id: "01920000-0000-7000-8000-0000000000c2", display_name: "Doppel, Dora", address: "Birkenweg 2, 53111 Bonn" },
    ],
  },
  {
    objekt: "84",
    ve: "1",
    zeile: 3,
    rolle: "Mieter",
    name: "Tom Offen",
    unit_id: "01920000-0000-7000-8000-000000000002",
    role: "mieter",
    grund: "vermieter_fehlt",
    zahlbetrag: "710,00",
    amount_cents: 71000,
    kandidaten: [],
    contact_id: "01920000-0000-7000-8000-0000000000c3",
  },
];

describe("OpenAssignments", () => {
  it("assigns a candidate and a tenant with landlord, rows disappear and the counter rises", async () => {
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        url.startsWith("/api/bff/contacts")
          ? jsonResponse({ items: [{ id: "01920000-0000-7000-8000-0000000000d1", display_name: "Vermieter, Lena" }], total: 1, page: 1, page_size: 10 })
          : jsonResponse({ mode: "apply", apply: true, counts: { vertraege_angelegt: 1 } }),
      ),
    );
    function Host() {
      const [state, setState] = useState({ items: OPEN, assigned: 0 });
      return <OpenAssignments items={state.items} assigned={state.assigned} startDate="2026-01-01" onChange={(items, assigned) => setState({ items, assigned })} />;
    }
    renderIntl(<Host />);
    expect(screen.getAllByTestId("zuordnung-open-row")).toHaveLength(2);
    expect(screen.getByTestId("zuordnung-open-table")).toHaveTextContent("275,50 EUR");
    expect(screen.getByTestId("zuordnung-open-table")).toHaveTextContent("Vermieter nicht eindeutig");

    const [first] = screen.getAllByTestId("zuordnung-open-row");
    const buttons = () => screen.getAllByRole("button", { name: "Zuordnen" });
    expect(buttons()[0]).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Kandidat wählen"), "01920000-0000-7000-8000-0000000000c2");
    expect(first).toHaveTextContent("Birkenweg 2, 53111 Bonn");
    await userEvent.click(buttons()[0]!);
    await waitFor(() => expect(screen.getAllByTestId("zuordnung-open-row")).toHaveLength(1));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/bff/imports/immoware24/lists/zuordnung/manuell");
    expect(JSON.parse(init.body as string)).toEqual({
      unit_id: "01920000-0000-7000-8000-000000000001",
      role: "eigentuemer",
      contact_id: "01920000-0000-7000-8000-0000000000c2",
      amount_cents: 27550,
      start_date: "2026-01-01",
    });
    expect(screen.getByTestId("zuordnung-open-assigned")).toHaveTextContent("zugeordnet: 1");

    expect(buttons()[0]).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Vermieter\) suchen/), "Vermieter");
    await userEvent.click(screen.getByRole("button", { name: /Suchen/i }));
    await userEvent.click(await screen.findByRole("button", { name: "Vermieter, Lena" }));
    await userEvent.click(buttons()[0]!);
    await waitFor(() => expect(screen.queryByTestId("zuordnung-open-row")).toBeNull());
    const tenantBody = JSON.parse(fetchMock.mock.calls.at(-1)![1].body as string);
    expect(tenantBody.contact_id).toBe("01920000-0000-7000-8000-0000000000c3");
    expect(tenantBody.landlord_contact_id).toBe("01920000-0000-7000-8000-0000000000d1");
    expect(screen.getByTestId("zuordnung-open-assigned")).toHaveTextContent("zugeordnet: 2");
    expect(screen.getByText("Keine offenen Zuordnungen.")).toBeInTheDocument();
  });

  it("shows an API error in the row and keeps it", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ type: "about:blank", title: "Fehler", status: 422, detail: "Der Vermieter ist nicht eindeutig." }, 422));
    const onChange = vi.fn();
    renderIntl(<OpenAssignments items={[OPEN[0]!]} assigned={0} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByLabelText("Kandidat wählen"), "01920000-0000-7000-8000-0000000000c1");
    await userEvent.click(screen.getByRole("button", { name: "Zuordnen" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Der Vermieter ist nicht eindeutig.");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("restores the last applied report after a reload", async () => {
    window.localStorage.setItem(
      ZUORDNUNG_STORAGE_KEY,
      JSON.stringify({ mode: "apply", apply: true, counts: { manuell_zugeordnet: 3 }, offen: [OPEN[0]], start_date: "2026-01-01" }),
    );
    renderIntl(<ZuordnungCard />);
    expect(await screen.findByTestId("zuordnung-open-table")).toHaveTextContent("Doppel, Dora");
    expect(screen.getByTestId("zuordnung-open-assigned")).toHaveTextContent("zugeordnet: 3");
    expect(screen.getByText("Letzter Bericht wiederhergestellt.")).toBeInTheDocument();
    window.localStorage.removeItem(ZUORDNUNG_STORAGE_KEY);
  });
});
