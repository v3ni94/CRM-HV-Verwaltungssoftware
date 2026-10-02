import { render, screen } from "@testing-library/react";

import { Skeleton, TileSkeleton } from "./Skeleton";

describe("Skeleton", () => {
  it("renders a decorative pulsing block with the given classes", () => {
    const { container } = render(<Skeleton className="h-3 w-20" />);
    const block = container.firstElementChild!;
    expect(block).toHaveAttribute("aria-hidden", "true");
    expect(block).toHaveClass("animate-pulse", "h-3", "w-20");
  });

  it("renders the KPI tile skeleton with three placeholders and no text", () => {
    const { container } = render(<TileSkeleton />);
    expect(container.querySelectorAll("[aria-hidden='true']")).toHaveLength(3);
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
    expect(container).toHaveTextContent("");
  });
});
