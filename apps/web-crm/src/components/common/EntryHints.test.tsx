import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { IntlTestProvider, renderIntl } from "@/test/intl";

import { EntryHints } from "./EntryHints";

describe("EntryHints", () => {
  it("renders nothing without findings", () => {
    const { container } = renderIntl(<EntryHints findings={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows errors as alert and warnings as status with the report link", () => {
    renderIntl(
      <EntryHints
        testId="hints"
        findings={[
          { rule: "ES-01", field: "postal_code", severity: "error" },
          { rule: "ES-03", field: "street", severity: "warning" },
        ]}
      />,
    );
    expect(screen.getByTestId("hints")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("genau fünf Ziffern");
    expect(screen.getByRole("status")).toHaveTextContent("Hausnummer steht im Feld Straße");
    expect(screen.getByRole("link", { name: "Zum Bericht Datenqualität" })).toHaveAttribute("href", "/einstellungen/datenqualitaet");
  });

  it("offers the name suggestion only when a handler exists and passes the value on", async () => {
    const finding = { rule: "ES-04", field: "name", severity: "warning" as const, params: { suggestion: "Musterstraße 1, 12345 Berlin" } };
    const { rerender } = renderIntl(<EntryHints findings={[finding]} />);
    expect(screen.queryByRole("button", { name: "Vorschlag übernehmen" })).not.toBeInTheDocument();
    const onApply = vi.fn();
    rerender(<IntlTestProvider><EntryHints findings={[finding]} onApplySuggestion={onApply} /></IntlTestProvider>);
    await userEvent.click(screen.getByRole("button", { name: "Vorschlag übernehmen" }));
    expect(onApply).toHaveBeenCalledWith("Musterstraße 1, 12345 Berlin");
  });
});
