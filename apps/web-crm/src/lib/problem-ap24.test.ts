import { SERVER_ERROR_MESSAGE, problemDetailLine, problemMessage } from "./problem";

describe("problem texts (GAM-716)", () => {
  it("gives 5xx without text a retry hint and keeps API texts", () => {
    expect(problemMessage(null, 500)).toBe(SERVER_ERROR_MESSAGE);
    expect(problemMessage({ title: "x" }, 503)).toBe("x");
    expect(problemMessage(null, 0)).toContain("später erneut");
    expect(SERVER_ERROR_MESSAGE).not.toMatch(/[–—]/);
  });
  it("appends code, status and the correlation id as reference", () => {
    const line = problemDetailLine({ status: 500, problem: { code: "MHVP-CORE-0001", correlation_id: "abc-123" }, message: "Fehler" });
    expect(line).toBe("Fehler (Code MHVP-CORE-0001, HTTP 500, Referenz abc-123)");
    expect(problemDetailLine({ status: 0, problem: null, message: "Offline" })).toBe("Offline");
  });
});
