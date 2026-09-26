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

  it("shows the majority check with the applied rule", () => {
    renderIntl(
      <ResolutionTable
        rows={[
          {
            id: "c",
            number: 3,
            decided_on: "2026-08-01",
            subject: "Wirtschaftsplan 2027",
            status: "positive",
            kind: "meeting",
            majority_check: { result: "nicht prüfbar", rule_text: "Wirtschaftsplan: einfache Mehrheit", reason: "Keine Auszählung erfasst." },
          },
        ]}
      />,
    );
    expect(screen.getByTestId("majority-check")).toHaveTextContent("Mehrheitsprüfung: nicht prüfbar");
    expect(screen.getByTestId("majority-check")).toHaveTextContent("Keine Auszählung erfasst.");
  });

  it("shows an empty state", () => {
    renderIntl(<ResolutionTable rows={[]} />);
    expect(screen.getByText("Noch keine Beschlüsse erfasst.")).toBeInTheDocument();
  });
});
