import { readdirSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { chapterBySlug, HANDBOOK, searchHandbook } from "./handbook";

describe("handbook", () => {
  it("has one chapter per docs/handbuch markdown file (run scripts/build_handbook.py when this fails)", () => {
    const dir = path.resolve(import.meta.dirname, "..", "..", "..", "..", "docs", "handbuch");
    const files = readdirSync(dir).filter((f) => f.endsWith(".md"));
    expect(HANDBOOK.length).toBe(files.length);
  });

  it("finds chapters and sections by full text", () => {
    expect(chapterBySlug("banking")?.title).toBe("Banking");
    const hits = searchHandbook("Bankabstimmung");
    expect(hits.length).toBeGreaterThan(0);
    expect(hits[0]!.slug).toBeTruthy();
    expect(searchHandbook("x")).toEqual([]);
  });
});
