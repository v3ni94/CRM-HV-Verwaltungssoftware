import { expect, test } from "@playwright/test";

// Installable shell of the CRM (M31 WP5, operator decision M30-08): manifest, icons, service
// worker registration and the static offline page, all reachable without a session. No API
// needed. The session lock of every page and API path stays covered by smoke.spec.ts and
// src/middleware.test.ts.
test("manifest and icons are served without a session and describe MHVP", async ({ page, request }) => {
  await page.goto("/anmelden");
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", "/manifest.webmanifest");
  const response = await request.get("/manifest.webmanifest");
  expect(response.status()).toBe(200);
  const manifest = (await response.json()) as {
    name: string;
    short_name: string;
    start_url: string;
    display: string;
    icons: { src: string; purpose?: string }[];
  };
  expect(manifest.name).toBe("MH Verwaltungsplattform");
  expect(manifest.short_name).toBe("MHVP");
  expect(manifest.start_url).toBe("/start");
  expect(manifest.display).toBe("standalone");
  expect(manifest.icons.map((i) => i.src)).toEqual(["/icons/icon-192.png", "/icons/icon-512.png", "/icons/icon-512-maskable.png"]);
  for (const icon of manifest.icons) {
    const file = await request.get(icon.src, { maxRedirects: 0 });
    expect(file.status(), icon.src).toBe(200);
    expect(file.headers()["content-type"], icon.src).toContain("image/png");
  }
});

test("service worker registers and the offline page is served, pages stay behind the login", async ({ page, request }) => {
  await page.goto("/anmelden");
  // PwaRegister lives in the signed in app shell ((app)/layout.tsx), which needs a backend;
  // registering here proves that the worker file is served and parses with the root scope.
  const scope = await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    await navigator.serviceWorker.ready;
    return registration.scope;
  });
  expect(scope).toMatch(/\/$/);
  const worker = await request.get("/sw.js", { maxRedirects: 0 });
  expect(worker.status()).toBe(200);
  expect(await worker.text()).toContain("mhvp-crm-shell");
  const offline = await request.get("/offline.html", { maxRedirects: 0 });
  expect(offline.status()).toBe(200);
  expect(await offline.text()).toContain("Eingaben werden nicht auf dem Gerät gespeichert");
  // The shell files are the only new exceptions: a page and the BFF still require a session.
  const start = await request.get("/start", { maxRedirects: 0 });
  expect(start.status()).toBe(307);
  expect(start.headers()["location"]).toContain("/anmelden");
  expect((await request.get("/api/bff/auth/me", { maxRedirects: 0 })).status()).toBe(401);
  expect((await request.get("/icons/x.svg", { maxRedirects: 0 })).status()).toBe(307);
});
