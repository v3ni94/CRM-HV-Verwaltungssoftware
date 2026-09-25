import { GET } from "./route";

describe("session return landing", () => {
  it("navigates to a relative target", async () => {
    const res = await GET(
      new Request(
        "https://crm.example/api/session/return?next=%2Feinstellungen%2Fdms%3Fconnected%3Ddrive",
      ),
    );
    const html = await res.text();
    expect(res.status).toBe(200);
    expect(html).toContain(
      'location.replace("/einstellungen/dms?connected=drive")',
    );
  });
  it("refuses absolute or protocol relative targets", async () => {
    for (const next of ["https://evil.example", "//evil.example", ""]) {
      const res = await GET(
        new Request(
          `https://crm.example/api/session/return?next=${encodeURIComponent(next)}`,
        ),
      );
      expect(await res.text()).toContain('location.replace("/start")');
    }
  });
  it("refuses a path carrying a scheme before the query", async () => {
    for (const next of [
      "/\tevil.example",
      "/\t/evil.example",
      "javascript:alert(1)",
      "/redirect:evil",
      "/a\nb",
    ]) {
      const res = await GET(
        new Request(
          `https://crm.example/api/session/return?next=${encodeURIComponent(next)}`,
        ),
      );
      expect(await res.text()).toContain('location.replace("/start")');
    }
  });
  it("allows a colon in the query string but not in the path", async () => {
    const res = await GET(
      new Request(
        `https://crm.example/api/session/return?next=${encodeURIComponent("/start?redirect=http://x")}`,
      ),
    );
    expect(await res.text()).toContain(
      'location.replace("/start?redirect=http://x")',
    );
  });
});
