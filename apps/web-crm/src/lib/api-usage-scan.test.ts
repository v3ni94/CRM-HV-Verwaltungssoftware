import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { calledPaths } from "./api-usage-scan";

function withSource(files: Record<string, string>): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "api-usage-"));
  for (const [name, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(dir, name)), { recursive: true });
    fs.writeFileSync(path.join(dir, name), text);
  }
  return dir;
}

describe("calledPaths (GAL-301 reverse check)", () => {
  it("recognises a literal call with a template parameter", () => {
    const dir = withSource({ "A.tsx": 'bff(`/api/bff/notices/${id}/reads`);' });
    expect(calledPaths(["/api/v1/notices/{notice_id}/reads"], [dir])).toEqual(["/api/v1/notices/{notice_id}/reads"]);
  });

  it("recognises a base constant without slash (GAL-301)", () => {
    const dir = withSource({ "B.tsx": 'const BASE = "payment-orders";\nfetch(`${BASE}/${id}/approve`);' });
    expect(calledPaths(["/api/v1/banking/payment-orders/{order_id}/approve"], [dir])).toEqual(["/api/v1/banking/payment-orders/{order_id}/approve"]);
  });

  it("does not match another resource with the same last segment", () => {
    const dir = withSource({ "C.tsx": 'bff(`/api/bff/tickets/${id}/status`);' });
    expect(calledPaths(["/api/v1/properties/{property_id}/status"], [dir])).toEqual([]);
  });

  it("ignores test files, the BFF allowlist and the changelog", () => {
    const dir = withSource({
      "D.test.tsx": 'bff("/api/bff/postal/jobs/x/refresh")',
      "app/api/bff/[...path]/route.ts": "pattern: /^postal\\/jobs\\/x\\/refresh$/ // postal/jobs/${ID}/refresh",
      "lib/changelog.ts": '"POST /postal/jobs/{id}/refresh"',
    });
    expect(calledPaths(["/api/v1/postal/jobs/{job_id}/refresh"], [dir])).toEqual([]);
  });

  it("needs a leading slash for a lone segment", () => {
    const dir = withSource({ "E.tsx": '<div data-testid="auto-post" />' });
    expect(calledPaths(["/api/v1/banking/auto-post"], [dir])).toEqual([]);
  });
});
