import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { EntityLinksBar } from "./EntityLinksBar";

describe("EntityLinksBar", () => {
  it("renders the jump paths and skips links without id or route", () => {
    renderIntl(
      <EntityLinksBar
        links={[
          { type: "property", id: "p1", label: "0815 Rheinpromenade" },
          { type: "building", id: "b1", parentId: "p1" },
          { type: "building", id: "b2" },
          { type: "unit", id: null },
          { type: "contract", id: "c1", count: 3 },
          { type: "posting", id: "j1", parentId: "l1" },
        ]}
      />,
    );
    const nav = screen.getByRole("navigation", { name: "Verknüpfungen" });
    const links = nav.querySelectorAll("a");
    expect(Array.from(links).map((a) => a.getAttribute("href"))).toEqual([
      "/objekte/p1",
      "/objekte/p1/gebaeude/b1",
      "/vertraege/c1",
      "/buchhaltung/l1",
    ]);
    expect(screen.getByText("0815 Rheinpromenade")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("renders nothing without usable links", () => {
    const { container } = renderIntl(<EntityLinksBar links={[{ type: "unit" }, { type: "building", id: "b" }]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
