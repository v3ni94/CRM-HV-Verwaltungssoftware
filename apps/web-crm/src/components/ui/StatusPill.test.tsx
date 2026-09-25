import { render, screen } from "@testing-library/react";

import { StatusPill } from "./StatusPill";

describe("StatusPill", () => {
  it("renders the label with a leading dot", () => {
    render(<StatusPill label="Offen" variant="warning" />);
    const pill = screen.getByText("Offen");
    expect(pill).toBeInTheDocument();
    expect(pill.closest("span")).toHaveClass("bg-warning-bg");
  });

  it("defaults to the neutral variant", () => {
    render(<StatusPill label="Unbekannt" />);
    expect(screen.getByText("Unbekannt").closest("span")).toHaveClass("bg-surface");
  });
});
