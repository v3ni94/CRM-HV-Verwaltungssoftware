import { createRequire } from "node:module";

import { expect, test } from "@playwright/test";

// GAI-619 / AJ31: axe run on the public login page of the smoke set. @axe-core/playwright is not
// installed (offline), so axe-core (already a devDependency) is injected directly. bypassCSP is
// needed because the app sets a nonce CSP and Playwright injects the script from outside.
// Only serious and critical violations fail the run; the result is listed for the report.
test.use({ bypassCSP: true });

const axePath = createRequire(import.meta.url).resolve("axe-core/axe.min.js");

test("login page has no serious or critical axe violations", async ({ page }) => {
  await page.goto("/anmelden");
  await page.addScriptTag({ path: axePath });
  const violations = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: () => Promise<{ violations: { id: string; impact: string | null; nodes: unknown[] }[] }> } }).axe;
    const result = await axe.run();
    return result.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length }));
  });
  const blocking = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(blocking, JSON.stringify(violations)).toEqual([]);
});
