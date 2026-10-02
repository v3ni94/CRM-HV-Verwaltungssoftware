import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";
import type { CalendarItem } from "@/components/workspace/CalendarView";

import { WeekView, weekRange } from "./WeekView";

describe("WeekView (GAI-615)", () => {
  it("builds Monday to Sunday around the anchor, also across a month change", () => {
    const week = weekRange(new Date(2026, 9, 1)); // Thursday 01.10.2026
    expect(week.start).toBe("2026-09-28");
    expect(week.end).toBe("2026-10-04");
    expect(week.days).toHaveLength(7);
    expect(weekRange(new Date(2026, 9, 4)).start).toBe("2026-09-28");
    expect(weekRange(new Date(2026, 9, 5)).start).toBe("2026-10-05");
  });

  it("shows entries on their day, selects and removes only editable ones", async () => {
    const { days } = weekRange(new Date(2026, 9, 1));
    const base = { date: "2026-09-29", source: "internal", kind: "appointment" } as unknown as CalendarItem;
    const editable = { ...base, title: "Begehung", entity_id: "e1", editable: true } as CalendarItem;
    const readonly = { ...base, title: "Frist", entity_id: "e2", editable: false } as CalendarItem;
    const onRemove = vi.fn();
    const onSelect = vi.fn();
    renderIntl(<WeekView days={days} items={[editable, readonly]} onRemove={onRemove} onSelect={onSelect} />);
    expect(screen.getAllByText("Keine Einträge.")).toHaveLength(6);
    await userEvent.click(screen.getByRole("button", { name: "Begehung" }));
    expect(onSelect).toHaveBeenCalledWith(editable);
    expect(screen.getAllByRole("button", { name: "Löschen" })).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Löschen" }));
    expect(onRemove).toHaveBeenCalledWith(editable);
  });
});
