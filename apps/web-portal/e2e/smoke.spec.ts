import { expect, test } from "@playwright/test";

test("home renders the German product name", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("MH Verwaltungsplattform");
  await expect(page.getByRole("status")).toBeVisible();
});

test("/api/health returns ok", async ({ request }) => {
  const response = await request.get("/api/health");
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body).toMatchObject({ status: "ok", service: "web-portal" });
  expect(typeof body.version).toBe("string");
});

test("web manifest is served", async ({ request }) => {
  const response = await request.get("/manifest.webmanifest");
  expect(response.status()).toBe(200);
  expect((await response.json()).lang).toBe("de");
});
