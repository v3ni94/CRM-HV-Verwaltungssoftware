"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

export type UserMappingRow = {
  source_id: string;
  email: string;
  display_name: string | null;
  objektakte_role: string | null;
  objektakte_status: string;
  proposed_role: string | null;
  crm_user_id: string | null;
  crm_member_roles: string[] | null;
  action: "already_member" | "add_membership" | "invite" | "manual" | "skip";
};

/** Link into the member administration with prefilled e-mail and role (query parameters read
 * by `/einstellungen/benutzer`). Nothing is created here (docs/rules/M35-03.md). */
export function membersHref(row: UserMappingRow): string {
  const params = new URLSearchParams();
  if (row.email) params.set("email", row.email);
  if (row.proposed_role) params.set("role", row.proposed_role);
  const query = params.toString();
  return query ? `/einstellungen/benutzer?${query}` : "/einstellungen/benutzer";
}

const ACTION_CLASS: Record<UserMappingRow["action"], string> = {
  already_member: ui.badgeSuccess,
  add_membership: ui.badgeGold,
  invite: ui.badgeGold,
  manual: ui.badgeWarning,
  skip: ui.badge,
};

/** M35 Stufe 4: the `user_mapping` report of an objektakte import run, one row per source
 * user with the proposed CRM role and the action the administrator has to take by hand. */
export function UserMappingTable({ rows }: { rows: UserMappingRow[] }) {
  const t = useTranslations("Objektakte.userMapping");
  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("title")}>
      <div className="flex flex-col gap-1">
        <h2 className={ui.h2}>{t("title")}</h2>
        <p className={ui.help}>{t("intro")}</p>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className={ui.table} data-testid="user-mapping">
            <thead>
              <tr>
                <th scope="col">{t("colEmail")}</th>
                <th scope="col">{t("colName")}</th>
                <th scope="col">{t("colSourceRole")}</th>
                <th scope="col">{t("colProposedRole")}</th>
                <th scope="col">{t("colCrmRoles")}</th>
                <th scope="col">{t("colAction")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.source_id}>
                  <td>{row.email}</td>
                  <td>
                    {row.display_name ?? ""}
                    {row.objektakte_status !== "active" ? (
                      <span className="ml-2 text-xs text-muted">({row.objektakte_status})</span>
                    ) : null}
                  </td>
                  <td>{row.objektakte_role ?? ""}</td>
                  <td>{row.proposed_role ?? <span className="text-muted">{t("noProposal")}</span>}</td>
                  <td>{row.crm_member_roles ? row.crm_member_roles.join(", ") : ""}</td>
                  <td>
                    <div className="flex flex-col gap-1">
                      <span className={ACTION_CLASS[row.action] ?? ui.badge}>
                        {t.has(`action.${row.action}`) ? t(`action.${row.action}`) : row.action}
                      </span>
                      {row.action === "skip" ? null : (
                        <Link href={membersHref(row)} className="text-xs underline">
                          {row.action === "invite" || row.action === "add_membership" ? t("inviteLink") : t("openMembers")}
                        </Link>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
