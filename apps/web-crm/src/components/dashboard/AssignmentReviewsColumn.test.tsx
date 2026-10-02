import { screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AssignmentReviewsColumn } from "./AssignmentReviewsColumn";

describe("AssignmentReviewsColumn", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("lists open reviews of tickets and mails with links", async () => {
    fetchMock.mockImplementation(async (input) =>
      String(input).includes("tickets/assignment")
        ? jsonResponse([{ id: "r1", entity_type: "ticket", entity_id: "t1", dimension: "property", status: "open", reason: "Zwei Objekte passen" }])
        : jsonResponse([{ id: "r2", entity_type: "message", entity_id: "m1", dimension: "contact", status: "open", reason: null }]),
    );
    renderIntl(<AssignmentReviewsColumn />);
    expect(await screen.findByText("Zwei Objekte passen")).toBeInTheDocument();
    const links = screen.getAllByRole("link");
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/tickets/t1", "/mail"]);
  });

  it("shows the empty state, also when a list is not readable", async () => {
    fetchMock.mockImplementation(async (input) =>
      String(input).includes("tickets/assignment") ? jsonResponse([]) : jsonResponse({ code: "x", detail: "no" }, 403),
    );
    renderIntl(<AssignmentReviewsColumn />);
    expect(await screen.findByText("Keine offene Zuordnungsprüfung.")).toBeInTheDocument();
  });
});
