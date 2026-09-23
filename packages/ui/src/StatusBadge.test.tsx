import { render, screen } from "@testing-library/react";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders the label with the ok state", () => {
    render(<StatusBadge state="ok" label="API bereit" />);
    const badge = screen.getByRole("status");
    expect(badge).toHaveTextContent("API bereit");
    expect(badge).toHaveAttribute("data-state", "ok");
  });

  it("renders the fail state", () => {
    render(<StatusBadge state="fail" label="API nicht erreichbar" />);
    expect(screen.getByRole("status")).toHaveAttribute("data-state", "fail");
  });
});
