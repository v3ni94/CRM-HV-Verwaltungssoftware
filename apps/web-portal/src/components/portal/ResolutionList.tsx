"use client";

import { useFormatter, useTranslations } from "next-intl";

import { RESOLUTION_STATUS, type PortalResolution } from "@/components/portal/types";
import { ui } from "@/lib/ui";

const KNOWN_STATUS = new Set<string>(RESOLUTION_STATUS);

/** Beschluss-Sammlung der eigenen Gemeinschaft (A51): nur verkündete Beschlüsse, Datum in
 *  TT.MM.JJJJ, Abstimmungsergebnis und Wirksamkeitsstatus. Rein lesend. */
export function ResolutionList({ rows }: { rows: PortalResolution[] }) {
  const t = useTranslations("Resolutions");
  const format = useFormatter();
  if (rows.length === 0) return <p className={ui.notice}>{t("empty")}</p>;
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((row) => (
        <li key={row.id} className={`${ui.card} flex flex-col gap-2`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium">
              {t("number")} {row.number}: {row.subject}
            </span>
            <span className={row.status === "positive" || row.status === "final" || row.status === "legally_binding" ? ui.badgeSuccess : ui.badge}>
              {KNOWN_STATUS.has(row.status) ? t(`status.${row.status}`) : row.status}
            </span>
          </div>
          <p className="text-sm text-fg whitespace-pre-line">{row.wording}</p>
          <p className="text-xs text-subtle">
            {t("decidedOn")}{" "}
            {format.dateTime(new Date(row.decided_on), { day: "2-digit", month: "2-digit", year: "numeric" })}
            {" · "}
            {t(`kind.${row.kind}`)}
            {row.votes ? ` · ${t("votes", { yes: row.votes.yes, no: row.votes.no, abstain: row.votes.abstain })}` : ""}
            {row.majority_basis ? ` · ${row.majority_basis}` : ""}
          </p>
        </li>
      ))}
    </ul>
  );
}
