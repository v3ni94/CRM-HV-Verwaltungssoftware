import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { CalendarLegend } from "./CalendarLegend";

describe("CalendarLegend", () => {
  it("lists only available sources with their checked state", () => {
    renderIntl(
      <CalendarLegend
        visible={{ internal: true, default: false, own: true }}
        available={{ internal: true, default: true, own: false }}
        onToggle={vi.fn()}
      />,
    );
    expect(screen.getByRole("group", { name: "Kalenderfarben" })).toBeInTheDocument();
    expect(screen.getByLabelText("Interner Termin")).toBeChecked();
    expect(screen.getByLabelText("Standardkalender")).not.toBeChecked();
    expect(screen.queryByLabelText("Eigener Kalender")).not.toBeInTheDocument();
  });

  it("reports the toggled source", async () => {
    const onToggle = vi.fn();
    renderIntl(
      <CalendarLegend
        visible={{ internal: true, default: true, own: true }}
        available={{ internal: true, default: true, own: true }}
        onToggle={onToggle}
      />,
    );
    await userEvent.click(screen.getByLabelText("Eigener Kalender"));
    expect(onToggle).toHaveBeenCalledWith("own");
  });
});
