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

// PWA (A57): manifest link in the document, manifest content, service worker registration and
// the static offline shell. No API needed.
test("PWA manifest is linked and describes MH Portal", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", "/manifest.webmanifest");
  const response = await request.get("/manifest.webmanifest");
  const manifest = (await response.json()) as { name: string; icons: { src: string }[]; display: string };
  expect(manifest.name).toBe("MH Portal");
  expect(manifest.display).toBe("standalone");
  expect(manifest.icons.map((i) => i.src)).toEqual(["/icons/icon-192.png", "/icons/icon-512.png"]);
  for (const icon of manifest.icons) expect((await request.get(icon.src)).status()).toBe(200);
});

test("service worker registers and the offline page is served", async ({ page, request }) => {
  await page.goto("/");
  const scope = await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready;
    return registration.scope;
  });
  expect(scope).toMatch(/\/$/);
  const offline = await request.get("/offline.html");
  expect(offline.status()).toBe(200);
  expect(await offline.text()).toContain("Keine Verbindung");
});
