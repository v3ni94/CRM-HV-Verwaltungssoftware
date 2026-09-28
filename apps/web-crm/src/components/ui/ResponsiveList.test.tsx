import { render, screen } from "@testing-library/react";

import { ui } from "@/lib/ui";

import { ResponsiveList } from "./ResponsiveList";

type Row = { id: string; name: string; status: string };

const rows: Row[] = [
  { id: "a", name: "Haus A", status: "active" },
  { id: "b", name: "Haus B", status: "terminated" },
];

function table(list: Row[]) {
  return (
    <table className={ui.table}>
      <tbody>
        {list.map((r) => (
          <tr key={r.id}>
            <td>{r.name}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

describe("ResponsiveList", () => {
  it("renders cards with test ids below sm and the table wrapper from sm", () => {
    render(
      <ResponsiveList
        rows={rows}
        keyOf={(r) => r.id}
        card={(r) => <a href={`/objekte/${r.id}`}>{r.name}</a>}
        cardClassName={(r) => (r.status === "terminated" ? "opacity-60" : "")}
        cardData={(r) => ({ "data-status": r.status })}
        table={table(rows)}
        testId="units"
      />,
    );
    const cards = screen.getByTestId("units-cards");
    expect(cards.tagName).toBe("UL");
    expect(cards).toHaveClass("sm:hidden");
    const items = screen.getAllByTestId("units-card");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveClass("mhvp-lift");
    expect(items[1]).toHaveClass("opacity-60");
    expect(items[1]).toHaveAttribute("data-status", "terminated");
    expect(screen.getAllByRole("link", { name: "Haus A" })).toHaveLength(1);
    const wrapper = screen.getByTestId("units");
    expect(wrapper).toHaveClass("hidden", "sm:block", "overflow-x-auto");
    expect(wrapper.querySelector("table")).not.toBeNull();
  });

  it("renders an empty list without error and the empty node when given", () => {
    const { rerender } = render(<ResponsiveList rows={[]} keyOf={(r: Row) => r.id} card={(r) => r.name} table={table([])} testId="units" />);
    expect(screen.getByTestId("units-cards")).toBeEmptyDOMElement();
    expect(screen.getByTestId("units")).toBeInTheDocument();
    rerender(<ResponsiveList rows={[]} keyOf={(r: Row) => r.id} card={(r) => r.name} table={table([])} testId="units" empty={<p>Keine Einheiten.</p>} />);
    expect(screen.getByText("Keine Einheiten.")).toBeInTheDocument();
    expect(screen.queryByTestId("units")).not.toBeInTheDocument();
  });
});
