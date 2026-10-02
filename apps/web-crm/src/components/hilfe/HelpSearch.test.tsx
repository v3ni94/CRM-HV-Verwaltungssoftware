import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { HANDBOOK } from "@/lib/handbook";

import { HelpSearch } from "./HelpSearch";

describe("HelpSearch (GAI-615)", () => {
  it("lists the chapters without a query, without the README", () => {
    render(<HelpSearch placeholder="Suchen" empty="Nichts gefunden" />);
    const chapters = HANDBOOK.filter((c) => c.slug !== "README");
    expect(chapters.length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: chapters[0]!.title })).toHaveAttribute("href", `/hilfe/${chapters[0]!.slug}`);
    expect(screen.queryByRole("link", { name: "README" })).not.toBeInTheDocument();
  });

  it("shows the empty text for a query without hits and ignores one character", async () => {
    render(<HelpSearch placeholder="Suchen" empty="Nichts gefunden" />);
    const input = screen.getByRole("searchbox", { name: "Suchen" });
    await userEvent.type(input, "x");
    expect(screen.queryByText("Nichts gefunden")).not.toBeInTheDocument();
    await userEvent.clear(input);
    await userEvent.type(input, "qqqzzzxxxyyy");
    expect(screen.getByText("Nichts gefunden")).toBeInTheDocument();
  });

  it("links a hit to its chapter", async () => {
    render(<HelpSearch placeholder="Suchen" empty="Nichts gefunden" />);
    const chapter = HANDBOOK.find((c) => c.slug !== "README")!;
    await userEvent.type(screen.getByRole("searchbox"), chapter.title.slice(0, 6));
    const links = await screen.findAllByRole("link");
    expect(links.some((a) => a.getAttribute("href")?.startsWith("/hilfe/"))).toBe(true);
  });
});
