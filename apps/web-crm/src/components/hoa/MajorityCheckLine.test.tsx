import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { MajorityCheckLine } from "./MajorityCheckLine";

describe("MajorityCheckLine", () => {
  it("shows rule text and reason", () => {
    renderIntl(<MajorityCheckLine check={{ result: "erreicht", rule_text: "Einfache Mehrheit", reason: "8 von 10" }} />);
    const el = screen.getByTestId("majority-check");
    expect(el.textContent).toContain("Einfache Mehrheit");
    expect(el.textContent).toContain("8 von 10");
  });

  it("renders without reason and for every result value", () => {
    for (const result of ["erreicht", "nicht erreicht", "nicht prüfbar"] as const) {
      const { unmount } = renderIntl(<MajorityCheckLine check={{ result, rule_text: "Regel" }} />);
      expect(screen.getByTestId("majority-check").textContent).not.toContain("undefined");
      unmount();
    }
  });
});
