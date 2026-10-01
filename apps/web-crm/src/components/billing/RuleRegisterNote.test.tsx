import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { RuleRegisterNote } from "./RuleRegisterNote";

describe("RuleRegisterNote", () => {
  it("shows rule, version, status and effective date of the pinned entry", () => {
    renderIntl(<RuleRegisterNote rule={{ rule_id: "A07", version: 3, status: "released", effective_from: "2025-01-01" }} />);
    const text = screen.getByTestId("rule-register").textContent ?? "";
    expect(text).toMatch(/A07 Version 3 \(released\), wirksam ab 01\.01\.2025/);
    expect(text).toMatch(/ändert diese Abrechnung nicht/);
  });

  it("states that no rule version was recorded", () => {
    renderIntl(<RuleRegisterNote rule={null} />);
    expect(screen.getByTestId("rule-register").textContent).toMatch(/Keine Regelversion im Register/);
  });
});
