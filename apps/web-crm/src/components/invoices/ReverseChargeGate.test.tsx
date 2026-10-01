import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { ReverseChargeGate } from "./ReverseChargeGate";

describe("ReverseChargeGate", () => {
  it("shows the release point without any action control", () => {
    renderIntl(<ReverseChargeGate reverseCharge />);
    const gate = screen.getByTestId("reverse-charge-gate");
    expect(gate.textContent).toMatch(/Freigabepunkt § 13b UStG/);
    expect(gate.textContent).toMatch(/keine automatische Buchung oder Steuerfolge/);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders nothing without reverse charge", () => {
    renderIntl(<ReverseChargeGate reverseCharge={false} />);
    expect(screen.queryByTestId("reverse-charge-gate")).toBeNull();
  });
});
