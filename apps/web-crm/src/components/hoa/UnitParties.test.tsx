import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { UnitParties } from "./UnitParties";

const p = (id: string, from: string, to: string) => ({ contract_id: id, party_id: "x", from, to, days: 10 });

describe("UnitParties", () => {
  it("shows one period without change note", () => {
    renderIntl(<UnitParties periods={[p("c1", "2026-01-01", "2026-12-31")]} />);
    expect(screen.getByTestId("unit-parties")).toHaveTextContent("01.01.2026 bis 31.12.2026");
    expect(screen.queryByTestId("unit-parties-change")).toBeNull();
  });

  it("flags a change of ownership as information (P01 open)", () => {
    renderIntl(<UnitParties periods={[p("c1", "2026-01-01", "2026-06-30"), p("c2", "2026-07-01", "2026-12-31")]} />);
    expect(screen.getByTestId("unit-parties-change")).toHaveTextContent("P01");
  });

  it("shows the empty state", () => {
    renderIntl(<UnitParties periods={undefined} />);
    expect(screen.getByText("kein Eigentumsverhältnis")).toBeInTheDocument();
  });
});
