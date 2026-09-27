import { useTranslations } from "next-intl";
import Link from "next/link";

import { ui } from "@/lib/ui";

/** Keys of GET /api/v1/workspace/approvals; a key is present only when the caller may decide. */
export type ApprovalKind = "mail" | "bank_accounts" | "release_gates" | "dunning_runs" | "direct_debits" | "metering_transmissions";
export type ApprovalCounts = Partial<Record<ApprovalKind, number>>;

export const APPROVAL_ORDER: ApprovalKind[] = ["mail", "bank_accounts", "release_gates", "dunning_runs", "direct_debits", "metering_transmissions"];

/** Where each approval is decided. Bank accounts are released on the contact; the list of
 *  contacts marks pending IBANs. Gate requests are decided on the platform page. */
export const APPROVAL_LINKS: Record<ApprovalKind, string> = {
  mail: "/mail",
  bank_accounts: "/kontakte",
  release_gates: "/plattform",
  dunning_runs: "/buchhaltung/mahnwesen",
  direct_debits: "/bank/lastschriften",
  metering_transmissions: "/einstellungen/schnittstellen/messdienstleister",
};

/** Column "Freigaben" (operator 27.09.2026): everything waiting for my approval, each as an
 *  action tile with count and link. Kinds the caller may not decide are not shown; when no
 *  kind is pending the column says so. Pure presentation. */
export function ApprovalsColumn({ counts }: { counts: ApprovalCounts }) {
  const s = useTranslations("StartPage");
  const kinds = APPROVAL_ORDER.filter((k) => typeof counts[k] === "number");
  const pending = kinds.filter((k) => (counts[k] ?? 0) > 0);
  return (
    <section className={ui.card} aria-labelledby="approvals-title" data-testid="approvals-column">
      <h2 id="approvals-title" className={ui.h2}>
        {s("approvals.title")}
      </h2>
      <p className="mt-1 text-xs text-subtle">{s("approvals.description")}</p>
      {kinds.length === 0 ? (
        <p className="mt-4 text-sm text-muted">{s("approvals.noRights")}</p>
      ) : pending.length === 0 ? (
        <p className="mt-4 text-sm text-muted">{s("approvals.empty")}</p>
      ) : (
        <ul className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-1">
          {pending.map((kind) => (
            <li key={kind} data-testid={`approval-${kind}`}>
              <Link href={APPROVAL_LINKS[kind]} className={`${ui.cardLink} flex items-center justify-between gap-3 !p-3`}>
                <span className="min-w-0">
                  <span className="block text-sm font-medium">{s(`approvals.kind.${kind}`)}</span>
                  <span className="block text-xs text-gold">{s("approvals.open")} →</span>
                </span>
                <span className={`${ui.badgeWarning} tabular-nums`}>{(counts[kind] ?? 0).toLocaleString("de-DE")}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
