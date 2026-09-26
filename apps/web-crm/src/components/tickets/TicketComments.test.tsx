import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { TicketComments } from "./TicketComments";

describe("TicketComments", () => {
  it("shows author, visibility and document count per comment", () => {
    renderIntl(
      <TicketComments
        comments={[
          { id: "c1", body: "Rückruf erledigt", internal: true, created_at: "2026-09-26T08:00:00Z", author_name: "Timo", document_ids: ["d1", "d2"] },
          { id: "c2", body: "Danke", internal: false, created_at: "2026-09-26T09:00:00Z", author_contact_id: "k1" },
        ]}
      />,
    );
    const items = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(items[0]).toContain("Timo · intern · 2 Dokumente");
    expect(items[0]).toContain("Rückruf erledigt");
    expect(items[1]).toContain("Portal · für Beteiligte sichtbar");
    expect(items[1]).not.toContain("Dokument");
  });

  it("renders a hint without comments", () => {
    renderIntl(<TicketComments comments={[]} />);
    expect(screen.getByText("Keine Kommentare.")).toBeInTheDocument();
  });
});
