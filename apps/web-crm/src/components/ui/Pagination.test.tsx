import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Pagination, type PaginationLabels } from "./Pagination";

const labels: PaginationLabels = {
  label: "Seitennavigation",
  range: (from, to, total) => `${from} bis ${to} von ${total}`,
  page: (page, pages) => `Seite ${page} von ${pages}`,
  prev: "Zurück",
  next: "Weiter",
};

describe("Pagination", () => {
  it("shows range and page, and only the next control on the first page", () => {
    render(<Pagination page={1} pageSize={25} total={60} shown={25} control={{ kind: "link", buildHref: (p) => `/x?page=${p}` }} labels={labels} testId="pg" />);
    expect(screen.getByTestId("pg")).toHaveAccessibleName("Seitennavigation");
    expect(screen.getByText("1 bis 25 von 60")).toBeInTheDocument();
    expect(screen.getByText("Seite 1 von 3")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Zurück" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Weiter" })).toHaveAttribute("href", "/x?page=2");
  });

  it("shows both controls on a middle page and only the previous control on the last", () => {
    const { rerender } = render(<Pagination page={2} pageSize={25} total={60} shown={25} control={{ kind: "link", buildHref: (p) => `/x?page=${p}` }} labels={labels} />);
    expect(screen.getByRole("link", { name: "Zurück" })).toHaveAttribute("href", "/x?page=1");
    expect(screen.getByRole("link", { name: "Weiter" })).toHaveAttribute("href", "/x?page=3");
    rerender(<Pagination page={3} pageSize={25} total={60} shown={10} control={{ kind: "link", buildHref: (p) => `/x?page=${p}` }} labels={labels} />);
    expect(screen.getByText("51 bis 60 von 60")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Weiter" })).not.toBeInTheDocument();
  });

  it("handles an empty result with range 0 and a single page", () => {
    render(<Pagination page={1} pageSize={25} total={0} shown={0} control={{ kind: "link", buildHref: () => "/" }} labels={labels} />);
    expect(screen.getByText("0 bis 0 von 0")).toBeInTheDocument();
    expect(screen.getByText("Seite 1 von 1")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("calls back with the target page in button mode and respects disabled", async () => {
    const onChange = vi.fn();
    const { rerender } = render(<Pagination page={2} pageSize={10} total={30} shown={10} control={{ kind: "button", onChange }} labels={labels} />);
    await userEvent.click(screen.getByRole("button", { name: "Weiter" }));
    await userEvent.click(screen.getByRole("button", { name: "Zurück" }));
    expect(onChange.mock.calls).toEqual([[3], [1]]);
    rerender(<Pagination page={2} pageSize={10} total={30} shown={10} control={{ kind: "button", onChange, disabled: true }} labels={labels} />);
    expect(screen.getByRole("button", { name: "Weiter" })).toBeDisabled();
  });
});
