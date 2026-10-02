import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HandbookBlocks } from "./HandbookBlocks";

describe("HandbookBlocks", () => {
  it("renders headings, inline markup, chapter links and tables", () => {
    render(
      <HandbookBlocks
        blocks={[
          { t: "h", level: 2, text: "Zweck", id: "zweck" },
          { t: "p", text: "Siehe [Banking](banking.md) und **wichtig** `code`." },
          { t: "table", head: ["A"], rows: [["b"]] },
        ]}
      />,
    );
    expect(screen.getByRole("heading", { name: "Zweck" })).toHaveAttribute("id", "zweck");
    expect(screen.getByRole("link", { name: "Banking" })).toHaveAttribute("href", "/hilfe/banking");
    expect(screen.getByText("wichtig").tagName).toBe("STRONG");
    expect(screen.getByRole("table")).toBeTruthy();
  });
});
