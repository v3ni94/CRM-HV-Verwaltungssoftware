import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { VirtualDeadlines } from "./VirtualDeadlines";

const base = {
  decided_on: "2026-01-15",
  term_limit: "2028-01-15",
  valid_until: "2028-01-15",
  days_until_valid_until: 500,
  transition_date: null,
  transition_notice: null,
};

describe("VirtualDeadlines", () => {
  it("shows the dates in TT.MM.JJJJ", () => {
    renderIntl(<VirtualDeadlines data={base} />);
    const el = screen.getByTestId("virtual-deadlines");
    expect(el.textContent).toContain("15.01.2026");
    expect(el.textContent).toContain("15.01.2028");
    expect(el.textContent).toContain("500");
  });

  it("shows notices and the transition date only when present", () => {
    renderIntl(
      <VirtualDeadlines
        data={{ ...base, valid_until: null, days_until_valid_until: null, transition_date: "2026-12-31", transition_notice: "Übergangshinweis" }}
        termNotice="Laufzeithinweis"
      />,
    );
    const el = screen.getByTestId("virtual-deadlines");
    expect(el.textContent).toContain("31.12.2026");
    expect(el.textContent).toContain("Übergangshinweis");
    expect(el.textContent).toContain("Laufzeithinweis");
  });
});
