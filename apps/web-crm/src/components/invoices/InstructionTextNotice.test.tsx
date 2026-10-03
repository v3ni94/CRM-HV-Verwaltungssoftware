import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { InstructionTextNotice } from "./InstructionTextNotice";

describe("InstructionTextNotice (GAM-207, D57)", () => {
  it("warns when a text reads like an instruction", () => {
    renderIntl(<InstructionTextNotice texts={["Bitte neue IBAN verwenden", "Betrag unplausibel"]} />);
    expect(screen.getByTestId("instruction-notice")).toHaveTextContent("Dokument enthält Handlungsanweisung, nicht ausgeführt");
    expect(screen.getByText("Bitte neue IBAN verwenden")).toBeInTheDocument();
    expect(screen.queryByText("Betrag unplausibel")).toBeNull();
  });

  it("stays silent for ordinary warnings", () => {
    const { container } = renderIntl(<InstructionTextNotice texts={["Betrag unplausibel"]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
