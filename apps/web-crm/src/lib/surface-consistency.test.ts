import { readFileSync } from "node:fs";
import path from "node:path";

import de from "../../messages/de.json";
import en from "../../messages/en.json";

const SRC = path.resolve(import.meta.dirname, "..");
const read = (rel: string) => readFileSync(path.join(SRC, rel), "utf8");
const ROOT = path.resolve(SRC, "..", "..", "..");

/** R15 consistency of the wave 2 and 3 surfaces: reachability, error states, form labels. */
describe("surface consistency", () => {
  it("lists work orders in the main menu and the help index", () => {
    expect(read("app/(app)/layout.tsx")).toContain('href: "/auftraege"');
    expect(readFileSync(path.join(ROOT, "scripts/build_help_index.py"), "utf8")).toContain('"/auftraege"');
  });

  it("links the notification settings from the settings overview", () => {
    expect(read("app/(app)/einstellungen/page.tsx")).toContain("/einstellungen/benachrichtigungen");
  });

  it.each([
    ["app/(app)/buchhaltung/verwalterhonorar/page.tsx", "AdminFees"],
    ["app/(app)/rechnungen/kreditoren/page.tsx", "Creditors"],
    ["app/(app)/rechnungen/plaene/page.tsx", "RecurringPlans"],
  ])("%s shows a visible error state when the load fails", (file, ns) => {
    const source = read(file);
    expect(source).toMatch(/role="alert"/);
    expect(source).toContain('t("loadError")');
    for (const catalogue of [de, en] as Record<string, Record<string, unknown>>[]) {
      expect(typeof catalogue[ns]?.loadError).toBe("string");
    }
  });

  it.each([
    "components/contacts/ContactMergeAdmin.tsx",
    "components/documents/CategoryTree.tsx",
    "components/documents/LetterTemplates.tsx",
    "components/hoa/ReserveForms.tsx",
    "components/letting/RentIndexAdmin.tsx",
    "components/letting/RentIndexAdopt.tsx",
    "components/hoa/AuditReportsPanel.tsx",
    "components/workspace/SavedFilters.tsx",
    "components/privacy/PrivacyAdmin.tsx",
    "app/(app)/auftraege/page.tsx",
    "app/(app)/buchhaltung/[id]/konten/[accountId]/page.tsx",
  ])("%s labels every form with aria-label", (file) => {
    const source = read(file);
    const forms = source.match(/<form\b/g)?.length ?? 0;
    const labelled = source.match(/<form\b[^]*?aria-label=/g)?.length ?? 0;
    expect(forms).toBeGreaterThan(0);
    expect(labelled).toBeGreaterThanOrEqual(forms);
  });

  it("has no hard coded column header in the finAPI account table", () => {
    expect(read("components/banking/FinApiConnections.tsx")).not.toContain(">Saldo<");
  });
});
