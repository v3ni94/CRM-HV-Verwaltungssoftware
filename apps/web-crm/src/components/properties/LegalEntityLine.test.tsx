import { render, screen } from "@testing-library/react";

import { LegalEntityLine } from "./LegalEntityLine";

const ENTITIES = [
  { id: "e1", name: "WEG Musterstraße 1", kindLabel: "GdWE" },
  { id: "e2", name: "Hausverwaltung Müller GmbH", kindLabel: "Verwalter" },
];

describe("LegalEntityLine", () => {
  it("shows all legal entities in one line with links", () => {
    render(<LegalEntityLine label="Rechtsträger" entities={ENTITIES} ledgerHref="/buchhaltung/l1" />);
    const line = screen.getByTestId("legal-entity-line");
    expect(line.textContent).toContain("Rechtsträger: ");
    expect(screen.getByRole("link", { name: "WEG Musterstraße 1" }).getAttribute("href")).toBe("/buchhaltung/l1");
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });

  it("shows plain names without a ledger and nothing without entities", () => {
    const { rerender } = render(<LegalEntityLine label="Rechtsträger" entities={ENTITIES} ledgerHref={null} />);
    expect(screen.queryByRole("link")).toBeNull();
    rerender(<LegalEntityLine label="Rechtsträger" entities={[]} ledgerHref={null} />);
    expect(screen.queryByTestId("legal-entity-line")).toBeNull();
  });
});
