import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { renderIntl } from "@/test/intl";
import type { EntryLine } from "@/lib/invoice-lines";

import { EMPTY_LINE, InvoiceLinesEditor } from "./InvoiceLinesEditor";

function Harness({ initial, gross }: { initial: EntryLine[]; gross: string }) {
  const [lines, setLines] = useState(initial);
  const [g, setG] = useState(gross);
  return <InvoiceLinesEditor accounts={[{ id: "a", label: "Konto" }]} lines={lines} documentGross={g} onLines={setLines} onDocumentGross={setG} />;
}

const lines: EntryLine[] = [
  { account_id: "a", net: "300,00", vat_percent: "19", text: "umlagefähig" },
  { account_id: "a", net: "300,00", vat_percent: "19", text: "Verwaltung" },
];

describe("InvoiceLinesEditor (GAM-106, D22)", () => {
  it("shows the sum and no mismatch when lines equal the document gross", () => {
    renderIntl(<Harness initial={lines} gross="714,00" />);
    expect(screen.getByTestId("split-sum")).toHaveTextContent("Netto 600,00 EUR, Steuer 114,00 EUR, Brutto 714,00 EUR");
    expect(screen.queryByTestId("split-mismatch")).toBeNull();
  });

  it("reports the difference to the document gross", () => {
    renderIntl(<Harness initial={lines} gross="713,99" />);
    expect(screen.getByTestId("split-mismatch")).toHaveTextContent("0,01 EUR");
  });

  it("adds and removes lines but keeps at least two", async () => {
    renderIntl(<Harness initial={[{ ...EMPTY_LINE }, { ...EMPTY_LINE }]} gross="" />);
    expect(screen.getAllByText("Zeile entfernen")[0]).toBeDisabled();
    await userEvent.click(screen.getByText("Zeile hinzufügen"));
    expect(screen.getAllByText("Zeile entfernen")).toHaveLength(3);
    await userEvent.click(screen.getAllByText("Zeile entfernen")[0]!);
    expect(screen.getAllByText("Zeile entfernen")).toHaveLength(2);
  });
});
