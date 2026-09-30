import { axe } from "vitest-axe";

import { renderIntl } from "@/test/intl";

import { LoginForm } from "@/components/auth/LoginForm";
import { MfaForm } from "@/components/auth/MfaForm";
import { TenantPicker } from "@/components/auth/TenantPicker";
import { ProfileSettings } from "@/components/settings/ProfileSettings";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), back: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/einstellungen/profil",
  useSearchParams: () => new URLSearchParams(),
}));

/** S16-09 (Barrierefreiheit, Abschnitt 16): axe-core checks the rendered DOM of the CRM's
 *  core client components for WCAG 2.1 AA violations, like the portal test
 *  (apps/web-portal/src/components/portal/Accessibility.axe.test.tsx). Covered: sign in,
 *  second factor, tenant choice and the profile page (password, sessions, devices). jsdom
 *  loads no stylesheet, so colour contrast stays with scripts/token_contrast.py. The keyboard
 *  checklist is docs/handbuch/barrierefreiheit.md (Abschnitt CRM). */
async function expectNoViolations(container: HTMLElement) {
  const results = await axe(container);
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
}

describe("CRM accessibility (axe)", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200 }))));
  afterEach(() => vi.unstubAllGlobals());

  it("LoginForm has no violations", async () => {
    const { container } = renderIntl(<LoginForm />);
    await expectNoViolations(container);
  });

  it("MfaForm has no violations", async () => {
    const { container } = renderIntl(<MfaForm />);
    await expectNoViolations(container);
  });

  it("TenantPicker has no violations", async () => {
    const { container } = renderIntl(
      <TenantPicker tenants={[{ id: "t1", name: "Hausverwaltung Müller GmbH" }, { id: "t2", name: "Timo Müller" }]} next="/" />,
    );
    await expectNoViolations(container);
  });

  it("ProfileSettings has no violations", async () => {
    const { container } = renderIntl(
      <ProfileSettings
        displayName="Timo Müller"
        email="admin@example.org"
        roles={["tenant_admin"]}
        tenantName="Hausverwaltung Müller GmbH"
        initialSessions={[]}
        initialDevices={[]}
        totpEnabled={false}
      />,
    );
    await expectNoViolations(container);
  });
});
