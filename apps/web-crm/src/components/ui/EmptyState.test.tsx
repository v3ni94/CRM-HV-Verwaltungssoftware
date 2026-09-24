import { render, screen } from "@testing-library/react";

import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("renders title and hint", () => {
    render(<EmptyState title="Keine Einträge" hint="Es liegen noch keine Daten vor." />);
    expect(screen.getByText("Keine Einträge")).toBeInTheDocument();
    expect(screen.getByText("Es liegen noch keine Daten vor.")).toBeInTheDocument();
  });

  it("renders an optional action", () => {
    render(<EmptyState title="Keine Einträge" action={<button>Neu anlegen</button>} />);
    expect(screen.getByRole("button", { name: "Neu anlegen" })).toBeInTheDocument();
  });
});
