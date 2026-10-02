import { screen, within } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { type TodayItem, TodayColumn } from "./TodayColumn";

const item = (over: Partial<TodayItem>): TodayItem => ({ id: "1", date: "2026-10-02", title: "Termin", kind: "other_kind", source: "calendar", href: null, ...over });

describe("TodayColumn (GAI-615)", () => {
  it("shows the empty text", () => {
    renderIntl(<TodayColumn items={[]} today="2026-10-02" />);
    expect(screen.getByText("Für heute und die nächsten sieben Tage liegt nichts an.")).toBeInTheDocument();
  });

  it("groups today before the coming days, sorted by date and title, with links only where given", () => {
    renderIntl(
      <TodayColumn
        today="2026-10-02"
        items={[
          item({ id: "3", date: "2026-10-05", title: "Später", source: "deadline", href: "/fristen/3" }),
          item({ id: "2", title: "Beta" }),
          item({ id: "1", title: "Alpha", href: "/kalender/1" }),
        ]}
      />,
    );
    const rows = screen.getAllByTestId(/^today-/).filter((e) => e.tagName === "LI");
    expect(rows.map((r) => within(r).getByText(/Alpha|Beta|Später/).textContent)).toEqual(["Alpha", "Beta", "Später"]);
    expect(rows[0]!.querySelector("a")).toHaveAttribute("href", "/kalender/1");
    expect(rows[1]!.querySelector("a")).toBeNull();
    expect(rows[2]).toHaveAttribute("data-testid", "today-deadline");
    expect(screen.getByText("05.10.2026")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Kalender/ })).toHaveAttribute("href", "/kalender");
  });
});
