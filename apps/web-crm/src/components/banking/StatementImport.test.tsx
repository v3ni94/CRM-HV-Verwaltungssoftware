import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ACCEPT, fileKind, StatementImport, uploadBlob } from "./StatementImport";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const DOC = "0192abcd-0000-7000-8000-000000000071";
const PBA = "0192abcd-0000-7000-8000-000000000031";
const MAPPING = "0192abcd-0000-7000-8000-000000000081";

const accounts = [
  { id: PBA, property_id: "p1", property_number: "0001", property_name: "Haus", legal_entity_id: "le1", legal_entity_name: "WEG Haus", kind: "hoa", iban_masked: "DE12****1234", bank_name: "Sparkasse", holder: "WEG" },
];

describe("file helpers", () => {
  it("detects CAMT, MT940 and CSV by suffix and wraps the upload with an accepted type", () => {
    expect(fileKind("auszug.xml")).toBe("camt");
    expect(fileKind("AUSZUG.STA")).toBe("mt940");
    expect(fileKind("umsatz.mt940")).toBe("mt940");
    expect(fileKind("export.csv")).toBe("csv");
    expect(ACCEPT).toContain(".sta");
    expect(ACCEPT).toContain(".csv");
    const sta = new File([":20:START"], "a.sta", { type: "" });
    expect(uploadBlob(sta, "mt940").type).toBe("text/plain");
    const csv = new File(["a;b"], "a.csv", { type: "application/vnd.ms-excel" });
    expect(uploadBlob(csv, "csv").type).toBe("text/csv");
    const xml = new File(["<x/>"], "a.xml", { type: "text/xml" });
    expect(uploadBlob(xml, "camt")).toBe(xml);
  });
});

describe("StatementImport", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("uploads an MT940 file as document and imports it through the statement import", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url.endsWith("/api/bff/documents")) return jsonResponse({ id: DOC }, 201);
      if (url.endsWith("/banking/imports")) return jsonResponse({ id: "run", status: "done", counts: { new: 3, duplicates: 1 }, errors: [] }, 201);
      return jsonResponse({}, 404);
    });
    renderIntl(<StatementImport />);
    const input = screen.getByLabelText("Kontoauszug (CAMT.053)") as HTMLInputElement;
    expect(input.accept).toBe(ACCEPT);
    await userEvent.upload(input, new File([":20:STARTUMSE"], "konto.sta", { type: "" }));
    await userEvent.click(screen.getByRole("button", { name: "Importieren" }));
    await waitFor(() => expect(screen.getByTestId("import-result")).toHaveTextContent("neu: 3 · bereits vorhanden: 1"));
    const upload = calls.find((c) => c.url.endsWith("/api/bff/documents"))!;
    const form = upload.init!.body as FormData;
    const file = form.get("file") as File;
    expect(file.name).toBe("konto.sta");
    expect(file.type).toBe("text/plain");
    expect(JSON.parse(calls.find((c) => c.url.endsWith("/banking/imports"))!.init!.body as string)).toEqual({ document_id: DOC });
    expect(refresh).toHaveBeenCalled();
  });

  it("previews a CSV, maps columns for an unknown format, saves the mapping and imports", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    let previews = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url.endsWith("/api/bff/documents")) return jsonResponse({ id: DOC }, 201);
      if (url.includes("/banking/accounts")) return jsonResponse(accounts);
      if (url.includes("/banking/csv-mappings?")) return jsonResponse([]);
      if (url.endsWith("/banking/csv-mappings")) return jsonResponse({ id: MAPPING, property_bank_account_id: PBA, label: "Hausbank", mapping: {} }, 201);
      if (url.endsWith("/banking/imports/csv/preview")) {
        previews += 1;
        const body = JSON.parse(init!.body as string);
        return jsonResponse({
          format_id: body.mapping ? "generic" : "unknown",
          label: body.mapping ? "Eigenes Mapping" : "Unbekannt",
          confidence: body.mapping ? "high" : "none",
          encoding: "utf-8",
          delimiter: ";",
          headers: ["Datum", "Betrag", "Text"],
          row_count: 2,
          sample_rows: [{ Datum: "01.09.2026", Betrag: "-12,00", Text: "Gebühr" }],
          errors: body.mapping ? [] : [{ line: 2, message: "Kein Buchungstag" }],
          ready_to_import: Boolean(body.mapping),
        });
      }
      if (url.endsWith("/banking/imports/csv")) return jsonResponse({ id: "run", status: "done", counts: { new: 2 }, errors: [] }, 201);
      return jsonResponse({}, 404);
    });
    renderIntl(<StatementImport />);
    await userEvent.upload(screen.getByLabelText("Kontoauszug (CAMT.053)"), new File(["Datum;Betrag;Text\n01.09.2026;-12,00;Gebühr"], "export.csv", { type: "text/csv" }));
    await userEvent.click(screen.getByRole("button", { name: "CSV prüfen" }));
    const preview = await screen.findByTestId("csv-preview");
    expect(preview).toHaveTextContent("Erkannt: Unbekannt");
    expect(screen.getByTestId("csv-errors")).toHaveTextContent("Zeile 2: Kein Buchungstag");
    expect(screen.getByRole("button", { name: "CSV importieren" })).toBeDisabled();
    // Unknown format opens the mapping automatically.
    expect(screen.getByTestId("csv-mapping")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Buchungstag"), "Datum");
    await userEvent.selectOptions(screen.getByLabelText("Betrag"), "Betrag");
    await userEvent.selectOptions(screen.getByLabelText("Verwendungszweck"), "Text");
    await userEvent.click(screen.getByRole("button", { name: "Vorschau mit Zuordnung prüfen" }));
    await waitFor(() => expect(previews).toBe(2));
    const second = calls.filter((c) => c.url.endsWith("/banking/imports/csv/preview")).at(-1)!;
    expect(JSON.parse(second.init!.body as string)).toEqual({ document_id: DOC, mapping: { booking_date: "Datum", amount: "Betrag", purpose: "Text" } });
    await waitFor(() => expect(screen.getByTestId("csv-preview")).toHaveTextContent("Erkannt: Eigenes Mapping"));
    await userEvent.selectOptions(screen.getByLabelText("Bankkonto (für eigene IBAN und gespeicherte Zuordnungen)"), PBA);
    await userEvent.type(screen.getByLabelText("Name der Zuordnung"), "Hausbank");
    await userEvent.click(screen.getByRole("button", { name: "Zuordnung speichern" }));
    await waitFor(() => expect(screen.getByText("Zuordnung „Hausbank“ gespeichert.")).toBeInTheDocument());
    const saved = calls.find((c) => c.url.endsWith("/banking/csv-mappings") && c.init?.method === "POST")!;
    expect(JSON.parse(saved.init!.body as string)).toEqual({ property_bank_account_id: PBA, label: "Hausbank", mapping: { booking_date: "Datum", amount: "Betrag", purpose: "Text" } });
    await userEvent.click(screen.getByRole("button", { name: "CSV importieren" }));
    await waitFor(() => expect(screen.getByTestId("import-result")).toHaveTextContent("neu: 2"));
    const imported = calls.find((c) => c.url.endsWith("/banking/imports/csv"))!;
    expect(JSON.parse(imported.init!.body as string)).toEqual({ document_id: DOC, property_bank_account_id: PBA, mapping_id: MAPPING });
    expect(refresh).toHaveBeenCalled();
  });
});
