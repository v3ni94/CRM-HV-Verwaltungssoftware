import { groupOf, parseRestoreReport } from "./restore-report";

const report = {
  apply: true,
  counts: {},
  results: [
    { tenant_id: "t", event_id: "e1", document_id: "d1", outcome: "deleted", reason: null },
    { tenant_id: "t", event_id: "e2", document_id: "d2", outcome: "kept_hold", reason: "Löschungssperre" },
  ],
};

describe("restore report", () => {
  it("parses a replay report and counts the outcomes itself", () => {
    const parsed = parseRestoreReport(JSON.stringify(report));
    expect(parsed?.apply).toBe(true);
    expect(parsed?.counts).toEqual({ deleted: 1, kept_hold: 1 });
    expect(parsed?.results[1]).toEqual({ document_id: "d2", outcome: "kept_hold", reason: "Löschungssperre" });
  });

  it.each(["", "kein json", "[]", '{"apply":"ja","results":[]}', '{"apply":true,"results":[1]}', '{"apply":true,"results":[{"x":1}]}'])(
    "rejects %s",
    (text) => expect(parseRestoreReport(text)).toBeNull(),
  );

  it("groups known outcomes and sends unknown ones to manual review", () => {
    expect(groupOf("would_delete")).toBe("replayed");
    expect(groupOf("kept_blocked")).toBe("kept");
    expect(groupOf("absent")).toBe("review");
    expect(groupOf("neu_unbekannt")).toBe("review");
  });
});
