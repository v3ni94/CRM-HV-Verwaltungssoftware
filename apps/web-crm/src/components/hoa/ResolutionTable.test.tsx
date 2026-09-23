import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { ResolutionTable } from "./ResolutionTable";

describe("ResolutionTable", () => {
  it("lists resolutions with German date and status labels", () => {
    renderIntl(
      <ResolutionTable
        rows={[
          { id: "a", number: 1, decided_on: "2026-05-10", subject: "Abrechnung 2025", status: "positive", kind: "meeting" },
          { id: "b", number: 2, decided_on: "2026-07-01", subject: "Hausordnung", status: "negative", kind: "circular" },
        ]}
      />,
    );
    expect(screen.getByText("10.05.2026")).toBeInTheDocument();
    expect(screen.getByText("positiv gefasst")).toBeInTheDocument();
    expect(screen.getByText("Umlaufbeschluss")).toBeInTheDocument();
  });

  it("shows an empty state", () => {
    renderIntl(<ResolutionTable rows={[]} />);
    expect(screen.getByText("Noch keine Beschlüsse erfasst.")).toBeInTheDocument();
  });
});
