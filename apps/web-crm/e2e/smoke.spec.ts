import { expect, test } from "@playwright/test";

test("root redirects to the login page when signed out", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/anmelden/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Willkommen zurück");
});

test("/api/health returns ok", async ({ request }) => {
  const response = await request.get("/api/health");
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body).toMatchObject({ status: "ok", service: "web-crm" });
  expect(typeof body.version).toBe("string");
});
