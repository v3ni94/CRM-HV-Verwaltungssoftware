import { expect, type Locator, type Page } from "@playwright/test";

/**
 * Layout assertions for the phone and tablet projects (M31 WP4, playwright.config.ts). Every
 * failure names the element and the measured value, so a reviewer sees what overflowed or
 * which target is too small without opening the trace.
 */

type Box = { tag: string; id: string; testid: string; cls: string; left: number; right: number };

/** No visible element ends right of the viewport or starts left of it. The check is element
 *  wise on purpose: `main` clips horizontal overflow (`overflow-x-clip`), so the document width
 *  and `scrollWidth` stay blind to a table or a chip row that is wider than the screen. */
export async function expectNoHorizontalOverflow(page: Page, tolerance = 1): Promise<void> {
  const offenders = await page.evaluate((tol) => {
    // In mobile emulation `innerWidth` grows with overflowing content (the layout viewport
    // widens), while `visualViewport.width` keeps the device width; the smaller one is the
    // screen the user sees.
    const width = Math.min(window.innerWidth, window.visualViewport?.width ?? Infinity);
    const out: Box[] = [];
    const docWidth = document.documentElement.scrollWidth;
    if (docWidth > width + tol) {
      out.push({ tag: "html", id: "", testid: "", cls: `document scrollWidth ${docWidth}`, left: 0, right: docWidth });
    }
    for (const el of Array.from(document.body.querySelectorAll<HTMLElement>("*"))) {
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") continue;
      if (style.position === "fixed" && el.getAttribute("aria-hidden") === "true") continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) continue;
      // Content inside a horizontal scroll wrapper (overflow-x auto or scroll) may be wider
      // than the screen by design; `hidden` and `clip` (the `main` clip) do not count, they
      // would hide exactly the overflow this check is for.
      let scroller: HTMLElement | null = el.parentElement;
      let scrolls = false;
      while (scroller && scroller !== document.body) {
        const ov = getComputedStyle(scroller).overflowX;
        if (ov === "auto" || ov === "scroll") {
          scrolls = scroller.getBoundingClientRect().right <= width + tol;
          break;
        }
        scroller = scroller.parentElement;
      }
      if (scrolls) continue;
      if (rect.right > width + tol || rect.left < -tol) {
        out.push({
          tag: el.tagName.toLowerCase(),
          id: el.id,
          testid: el.getAttribute("data-testid") ?? "",
          cls: el.className && typeof el.className === "string" ? el.className.slice(0, 80) : "",
          left: Math.round(rect.left),
          right: Math.round(rect.right),
        });
      }
    }
    return { width, out };
  }, tolerance);
  const lines = offenders.out.map((o) => `${o.tag}${o.id ? `#${o.id}` : ""}${o.testid ? `[data-testid=${o.testid}]` : ""} left=${o.left} right=${o.right} (${o.cls})`);
  expect(lines, `elements outside the ${offenders.width} px viewport:\n${lines.join("\n")}`).toEqual([]);
}

/** Touch target of at least 44 x 44 px (docs/design/README.md, pointer-coarse variants). */
export async function expectTouchTarget(locator: Locator, min = 44): Promise<void> {
  await expect(locator).toBeVisible();
  const box = await locator.boundingBox();
  const label = await describe(locator);
  expect(box, `${label}: no bounding box`).not.toBeNull();
  expect(box!.width, `${label}: width ${box!.width} px is below ${min} px`).toBeGreaterThanOrEqual(min);
  expect(box!.height, `${label}: height ${box!.height} px is below ${min} px`).toBeGreaterThanOrEqual(min);
}

/** The app header stays one row: at most 72 px (56 px plus safe area on phones, 64 px from
 *  sm). Pass a locator when the page has more than one `header`. */
export async function expectHeaderOneRow(page: Page, header: Locator = page.locator("header").first()): Promise<void> {
  await expect(header, "no header on this page").toBeVisible();
  const box = await header.boundingBox();
  expect(box, "header: no bounding box").not.toBeNull();
  expect(box!.height, `header is ${box!.height} px high, more than one row`).toBeLessThanOrEqual(72);
}

/** The project emulates a coarse pointer (isMobile and hasTouch). All 44 px assertions rest on
 *  the `pointer-coarse` variants, so a run in the desktop project would pass them for the
 *  wrong reason; this check fails there with a hint. */
export async function expectCoarsePointer(page: Page): Promise<void> {
  const coarse = await page.evaluate(() => window.matchMedia("(pointer: coarse)").matches);
  expect(coarse, "the project does not emulate a coarse pointer: run with --project phone, tablet or tablet-landscape").toBe(true);
}

/** Computed font size of at least `min` px (16 px on phones prevents the iOS focus zoom). */
export async function expectFontSizeAtLeast(locator: Locator, min = 16): Promise<void> {
  const size = await locator.evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  expect(size, `${await describe(locator)}: font size ${size} px is below ${min} px`).toBeGreaterThanOrEqual(min);
}

async function describe(locator: Locator): Promise<string> {
  try {
    return await locator.evaluate((el) => {
      const testid = el.getAttribute("data-testid");
      const label = el.getAttribute("aria-label") ?? (el.textContent ?? "").trim().slice(0, 40);
      return `${el.tagName.toLowerCase()}${el.id ? `#${el.id}` : ""}${testid ? `[data-testid=${testid}]` : ""}${label ? ` "${label}"` : ""}`;
    });
  } catch {
    return String(locator);
  }
}
