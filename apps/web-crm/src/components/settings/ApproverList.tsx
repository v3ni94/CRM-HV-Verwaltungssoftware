"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import {
  approvers,
  IDENTITY_CRITERIA,
  identityHints,
  type ApproverMember,
  type ApproverRole,
  type IdentityCriterion,
} from "@/lib/approver-identity";
import { ui } from "@/lib/ui";

const REASON_KEY = { contact: "reasonContact", name: "reasonName", emailVariant: "reasonEmail" } as const;

/** GAM-205: Liste der Konten mit Zahlungsfreigabe (Zahlungsaufträge: banking:approve, Lastschriftläufe:
 *  accounting:approve) mit Kennzeichnung möglicher Doppelidentitäten. Anzeige ohne Wirkung: die
 *  Vier-Augen-Prüfung bleibt auf Benutzer-ID; die Definition unabhängiger Freigeber ist offen. */
export function ApproverList({ members, roles }: { members: ApproverMember[]; roles: ApproverRole[] }) {
  const t = useTranslations("ApproverList");
  const [enabled, setEnabled] = useState<IdentityCriterion[]>(["contact", "name"]);
  const rows = useMemo(() => approvers(members, roles), [members, roles]);
  // Hints are computed among the approvers only: the question is whether two approvals come from one person.
  const hints = useMemo(
    () => identityHints(rows.map((r) => r.member), enabled),
    [rows, enabled],
  );
  const flagged = rows.filter((r) => (hints.get(r.member.membership_id) ?? []).length > 0).length;

  return (
    <section className={`${ui.card} flex flex-col gap-3`} data-testid="approver-list">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.help}>{t("notice")}</p>
      <fieldset className="flex flex-col gap-1">
        <legend className={ui.label}>{t("criteriaTitle")}</legend>
        {IDENTITY_CRITERIA.map((c) => (
          <label key={c} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={enabled.includes(c)}
              onChange={(e) => setEnabled((prev) => (e.target.checked ? [...prev, c] : prev.filter((x) => x !== c)))}
            />
            {t(`criteria.${c}`)}
          </label>
        ))}
      </fieldset>
      <p role="status" className={flagged > 0 ? ui.alert : ui.small} data-testid="approver-summary">
        {t("summary", { count: flagged })}
      </p>
      <p className={ui.small}>{t("stateOnlyActive")}</p>
      <div className={ui.tableCard}>
        <table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("member")}</th>
              <th>{t("email")}</th>
              <th>{t("rights")}</th>
              <th>{t("hint")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={99} className="text-muted">
                  {t("none")}
                </td>
              </tr>
            ) : null}
            {rows.map(({ member, payments, directDebits }) => {
              const list = hints.get(member.membership_id) ?? [];
              return (
                <tr key={member.membership_id} data-testid={`approver-${member.membership_id}`}>
                  <td>{member.display_name}</td>
                  <td>{member.email}</td>
                  <td>
                    {[payments ? t("payments") : null, directDebits ? t("directDebits") : null].filter(Boolean).join(", ")}
                  </td>
                  <td>
                    {list.length === 0 ? (
                      <span className="text-muted">{t("noHint")}</span>
                    ) : (
                      <span className="text-sm" data-testid="approver-hint">
                        {t("possibleSame", {
                          names: list.map((h) => h.with.display_name).join(", "),
                          reasons: [...new Set(list.flatMap((h) => h.reasons))].map((r) => t(REASON_KEY[r])).join(", "),
                        })}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
