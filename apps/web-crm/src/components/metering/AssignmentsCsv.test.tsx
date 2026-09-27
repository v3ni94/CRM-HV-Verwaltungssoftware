import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AssignmentsCsv } from "./AssignmentsCsv";

describe("AssignmentsCsv", () => {
  afterEach(() => vi.restoreAllMocks());

  it("previews a CSV with a validation report and applies only after the second step", async () => {
    const preview = {
      ok_count: 1,
      error_count: 1,
      duplicate_count: 1,
      rows: [
        { line: 2, status: "ok", messages: [], values: { hvm_nummer: "007", externe_nummer: "0004711" } },
        { line: 3, status: "error", messages: ["Objekt 999 nicht gefunden"], values: { hvm_nummer: "999" } },
        { line: 4, status: "duplicate", messages: ["Zeile 2 wiederholt"], values: { hvm_nummer: "007", externe_nummer: "0004711" } },
      ],
      created_ids: [],
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/assignments-import/preview")) return jsonResponse(preview);
      if (url.endsWith("/assignments-import/apply")) return jsonResponse({ ...preview, created_ids: ["aaaaaaaa-1111-4111-8111-111111111111"] });
      return jsonResponse({ detail: "unexpected" }, 500);
    });
    const onApplied = vi.fn();
    renderIntl(<AssignmentsCsv canUpdate onApplied={onApplied} />);
    expect(screen.getByRole("link", { name: "Vorlage herunterladen" })).toHaveAttribute("href", "/api/bff/metering/assignments-import/template");
    expect(screen.getByTestId("csv-apply")).toBeDisabled();

    const user = userEvent.setup();
    const file = new File(["hvm_nummer;externe_nummer\n007;0004711\n"], "zuordnungen.csv", { type: "text/csv" });
    await user.upload(screen.getByLabelText("CSV-Datei"), file);
    await user.click(screen.getByTestId("csv-preview"));
    const report = await screen.findByTestId("csv-report");
    expect(report).toHaveTextContent("1 in Ordnung, 1 Fehler, 1 Dubletten");
    expect(within(screen.getByTestId("csv-row-2")).getByText("in Ordnung")).toBeInTheDocument();
    expect(within(screen.getByTestId("csv-row-2")).getByText(/externe_nummer=0004711/)).toBeInTheDocument();
    expect(within(screen.getByTestId("csv-row-3")).getByText("Objekt 999 nicht gefunden")).toBeInTheDocument();
    expect(within(screen.getByTestId("csv-row-4")).getByText("Dublette")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some((c) => String(c[0]).endsWith("/apply"))).toBe(false);
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBeInstanceOf(FormData);

    await user.click(screen.getByTestId("csv-apply"));
    expect(await screen.findByText("1 Zuordnungen übernommen.")).toBeInTheDocument();
    expect(onApplied).toHaveBeenCalled();
  });
});
