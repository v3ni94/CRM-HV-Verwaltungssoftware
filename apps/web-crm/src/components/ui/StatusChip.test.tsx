import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { StatusChip } from "./StatusChip";

describe("StatusChip", () => {
  it("renders the German label with an icon and tone class", () => {
    render(<StatusChip domain="ticket" status="in_progress" />);
    const chip = screen.getByText("In Bearbeitung");
    expect(chip).toHaveClass("bg-warning-bg");
    expect(chip.querySelector("svg")).not.toBeNull();
  });

  it("opens the explanation popover on click and closes on Escape", async () => {
    render(<StatusChip domain="directDebitRun" status="approved" />);
    const button = screen.getByRole("button", { name: "Wartet auf Freigabe" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    const hint = screen.getByRole("tooltip");
    expect(hint).toHaveTextContent("G2 geschlossen: Freigabe durch zweite Person nötig");
    expect(hint).toHaveClass("sr-only");
    expect(button).toHaveAttribute("aria-describedby", hint.id);
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(hint).not.toHaveClass("sr-only");
    await userEvent.keyboard("{Escape}");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("flips the explanation to the right edge when it would leave the viewport (M31)", async () => {
    render(<StatusChip domain="directDebitRun" status="approved" />);
    const hint = screen.getByRole("tooltip");
    expect(hint).toHaveClass("left-0", "max-w-[calc(100vw-2rem)]");
    vi.spyOn(hint, "getBoundingClientRect").mockReturnValue({ right: window.innerWidth + 40 } as DOMRect);
    await userEvent.click(screen.getByRole("button", { name: "Wartet auf Freigabe" }));
    expect(hint).toHaveClass("right-0");
    expect(hint).not.toHaveClass("left-0");
    expect(hint).toHaveAttribute("data-flip", "right");
  });

  it("falls back to a neutral chip with the raw value and accepts overrides", () => {
    render(<StatusChip domain="mail" status="weird" />);
    expect(screen.getByText("weird")).toHaveClass("bg-muted-bg");
    render(<StatusChip domain="gate" status="closed" label="G2: geschlossen" />);
    expect(screen.getByRole("button", { name: "G2: geschlossen" })).toBeInTheDocument();
  });
});
