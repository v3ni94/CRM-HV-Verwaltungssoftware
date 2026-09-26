import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { DigestCard, type Digest } from "./DigestCard";

const base: Digest = { date: "2026-09-26", total: 0, sections: {} };

describe("DigestCard", () => {
  it("shows the empty state when nothing is due", () => {
    renderIntl(<DigestCard digest={base} />);
    expect(screen.getByText("Für heute liegt nichts an.")).toBeInTheDocument();
    expect(screen.getByText("26.09.2026")).toBeInTheDocument();
  });

  it("lists sections with counts, German dates and hidden empty sections", () => {
    const digest: Digest = {
      date: "2026-09-26",
      total: 3,
      sections: {
        tickets_due_today: { count: 0, items: [] },
        tickets_overdue: {
          count: 2,
          items: [{ id: "01920000-0000-7000-8000-0000000000aa", number: 12, title: "Heizung" }],
        },
        deadlines: {
          count: 1,
          items: [{ id: "01920000-0000-7000-8000-0000000000bb", reference: "Zähler 4711", due_on: "2026-09-26" }],
        },
      },
    };
    renderIntl(<DigestCard digest={digest} />);
    expect(screen.getByText("3 offene Punkte")).toBeInTheDocument();
    expect(screen.queryByTestId("digest-tickets_due_today")).toBeNull();
    expect(screen.getByText("Überfällige Tickets")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "#12 Heizung" })).toHaveAttribute("href", "/tickets/01920000-0000-7000-8000-0000000000aa");
    expect(screen.getByText("und 1 weitere")).toBeInTheDocument();
    expect(screen.getByText("Fristen des Tages (zu prüfen)")).toBeInTheDocument();
    expect(screen.getAllByText("26.09.2026").length).toBeGreaterThanOrEqual(2);
  });
});
