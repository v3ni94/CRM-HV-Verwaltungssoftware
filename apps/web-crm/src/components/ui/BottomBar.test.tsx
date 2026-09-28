import { render, screen } from "@testing-library/react";

import { BOTTOM_BAR_SPACE, BottomBar } from "./BottomBar";

describe("BottomBar", () => {
  it("is fixed to the viewport bottom with safe area padding, rail offsets and a free AI corner", () => {
    render(
      <BottomBar testId="bar" label="Aktionen">
        <button type="button">Weiter</button>
      </BottomBar>,
    );
    const bar = screen.getByTestId("bar");
    expect(bar).toHaveAttribute("role", "toolbar");
    expect(bar).toHaveClass("fixed", "inset-x-0", "bottom-0", "z-30", "pr-[5.5rem]", "lg:left-[4.5rem]", "xl:left-64", "mhvp-bottom-bar");
    expect(bar.style.paddingBottom).toBe("max(0.5rem, env(safe-area-inset-bottom))");
    expect(screen.getByRole("button", { name: "Weiter" })).toBeInTheDocument();
  });

  it("exports the page spacing below the bar", () => {
    expect(BOTTOM_BAR_SPACE).toBe("pb-24");
  });
});
