import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { KpiStrip, TILE_LINKS } from "./KpiStrip";

describe("KpiStrip (GAI-615)", () => {
  it("links tiles with an own screen and keeps others plain", () => {
    renderIntl(<KpiStrip tiles={{ contacts: 1234, unknown_tile: 2 }} analyticsHref="/auswertung/tickets" />);
    expect(screen.getByTestId("tile-contacts").querySelector("a")).toHaveAttribute("href", TILE_LINKS.contacts);
    expect(screen.getByTestId("tile-contacts")).toHaveTextContent("1.234");
    expect(screen.getByTestId("tile-unknown_tile").querySelector("a")).toBeNull();
    expect(screen.getByTestId("tile-unknown_tile")).toHaveTextContent("unknown_tile");
    expect(screen.getByRole("link", { name: /Auswertung/ })).toHaveAttribute("href", "/auswertung/tickets");
  });

  it("shows the empty text without tiles and no analytics link without a target", () => {
    renderIntl(<KpiStrip tiles={{}} />);
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
