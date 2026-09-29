import { render } from "@testing-library/react";
import { axe } from "vitest-axe";

import { renderIntl } from "@/test/intl";

import { HandoverFill } from "@/components/handover/HandoverFill";
import { protocol } from "@/components/handover/HandoverFill.test.fixture";
import { PhotoLightbox } from "@/components/handover/PhotoLightbox";
import { SignaturePad } from "@/components/handover/SignaturePad";

import { HoaAccountTable } from "./HoaAccountTable";
import { NewTicket } from "./NewTicket";
import { NoticeList } from "./NoticeList";
import { StartTiles } from "./StartTiles";
import type { HoaAccount, Me } from "./types";

import { PortalNav } from "@/components/shell/PortalNav";
import { ThemeSwitch } from "@/components/shell/ThemeToggle";
import { portalThemeStore } from "@/lib/theme";

/** V13 (Barrierefreiheit): axe-core checks the rendered DOM of the portal's core pages for
 *  WCAG 2.1 AA violations (structure, forms, contrast where computable in jsdom, tables).
 *  Server components (RSC pages under app/(portal)) cannot be rendered directly in Vitest, so
 *  this covers the client components that carry their markup: navigation, start tiles, notice
 *  board (Übersicht), the new ticket form (Meldungen) and the account table (Kontoauszug /
 *  Hausgeldkonto), plus the accessibility statement's static markup and the theme switch.
 *  Every case runs in both modes (data-theme day and evening). jsdom loads no stylesheet, so
 *  colour contrast per mode is covered by scripts/token_contrast.py and the axe run in the
 *  browser (Playwright), not here. */

vi.mock("next/navigation", () => ({
  usePathname: () => "/start",
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

/** vitest-axe's custom matcher typings target an older Vitest `Assertion` shape and do not
 *  align with this project's Vitest 5; asserting the violations array directly keeps full
 *  type safety while checking exactly the same axe-core result. */
async function expectNoViolations(container: Element) {
  const results = await axe(container);
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
}

function me(overrides: Partial<Me> = {}): Me {
  return { contact_id: "c1", roles: ["tenant", "owner"], contracts: [], ...overrides };
}

function hoaAccount(): HoaAccount {
  return {
    note: "Nur gebuchte Einträge.",
    legacy_note: null,
    contracts: [
      {
        contract_number: "V-1",
        note: null,
        balance: "12.50",
        charges: "100.00",
        credits: "87.50",
        entries: [
          {
            booking_date: "2026-01-05",
            due_date: "2026-01-15",
            text: "Hausgeld Januar",
            kind: "charge",
            amount: "100.00",
            direction: "charge",
            reversed: false,
          },
          {
            booking_date: "2026-01-20",
            due_date: null,
            text: "Zahlung",
            kind: "payment",
            amount: "87.50",
            direction: "credit",
            reversed: false,
          },
        ],
      },
    ],
  };
}

describe.each(["day", "evening"] as const)("Barrierefreiheit (axe), Modus %s", (mode) => {
  beforeEach(() => {
    localStorage.clear();
    portalThemeStore.reset();
    document.documentElement.setAttribute("data-theme", mode);
  });

  afterEach(() => {
    document.documentElement.removeAttribute("data-theme");
  });

  it("ThemeSwitch (Darstellung) has no violations", async () => {
    portalThemeStore.set(mode);
    const { container } = renderIntl(<ThemeSwitch />);
    await expectNoViolations(container);
  });

  it("PortalNav has no violations", async () => {
    const { container } = render(
      <PortalNav
        links={[
          { href: "/start", label: "Übersicht" },
          { href: "/dokumente", label: "Dokumente" },
        ]}
        label="Hauptnavigation"
        openLabel="Menü öffnen"
        closeLabel="Menü schließen"
      />,
    );
    await expectNoViolations(container);
  });

  it("StartTiles (Übersicht) has no violations", async () => {
    const { container } = renderIntl(<StartTiles me={me()} newNotices={2} />);
    await expectNoViolations(container);
  });

  it("NoticeList has no violations", async () => {
    const { container } = renderIntl(
      <NoticeList
        notices={[
          {
            id: "n1",
            property_id: "p1",
            property_number: "10",
            property_name: "Musterstraße 1",
            title: "Wasserabsperrung",
            body: "Am Dienstag wird das Wasser kurzzeitig abgestellt.",
            valid_from: "2026-01-01",
            valid_to: null,
            has_document: false,
            is_new: true,
            created_at: "2026-01-01T08:00:00Z",
          },
        ]}
      />,
    );
    await expectNoViolations(container);
  });

  it("NewTicket form (Meldungen) has no violations", async () => {
    const { container } = renderIntl(<NewTicket />);
    await expectNoViolations(container);
  });

  it("HoaAccountTable (Kontoauszug/Vertrag) has no violations", async () => {
    const { container } = renderIntl(<HoaAccountTable account={hoaAccount()} />);
    await expectNoViolations(container);
  });

  // M31 WP5: the handover protocol on the participant's own phone.
  it("HandoverFill section tabs have no violations", async () => {
    const { container } = renderIntl(<HandoverFill initial={protocol({ current_step: "rooms" })} />);
    await expectNoViolations(container);
  });

  it("PhotoLightbox has no violations", async () => {
    const { container } = renderIntl(
      <PhotoLightbox
        photos={[{ id: "a", src: "/api/portal-files/portal/handover/x/documents/a/content", title: "Küche" }]}
        index={0}
        onClose={() => undefined}
        onIndex={() => undefined}
      />,
    );
    await expectNoViolations(container);
  });

  it("SignaturePad has no violations", async () => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    const { container } = renderIntl(
      <SignaturePad base="/api/bff/portal/handover/x" kind="rental" participants={[]} signatures={[]} disabled={false} onSaved={() => undefined} />,
    );
    await expectNoViolations(container);
    vi.restoreAllMocks();
  });
});
