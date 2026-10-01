"use client";

import { useFormatter, useTranslations } from "next-intl";

import type { PortalRepresentation } from "@/components/portal/types";
import { ui } from "@/lib/ui";

const STATES = new Set(["active", "pending", "expired", "revoked"]);

/** Vertretungen des Zugangs (M21-05): Vertretener, Zeitraum und Ablauf. Abgelaufene und
 *  widerrufene Vollmachten werden nur angezeigt, sie gewähren keinen Zugriff mehr; die
 *  Prüfung erfolgt in der API. */
export function RepresentationList({ rows }: { rows: PortalRepresentation[] }) {
  const t = useTranslations("Representation");
  const format = useFormatter();
  if (rows.length === 0) return <p className={ui.notice}>{t("empty")}</p>;
  const day = (value: string) =>
    format.dateTime(new Date(`${value}T12:00:00`), { day: "2-digit", month: "2-digit", year: "numeric" });
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((row) => (
        <li key={row.id} className={`${ui.card} flex flex-col gap-1`} data-testid="portal-representation">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-medium break-words">{row.principal_name ?? t("unknownPrincipal")}</span>
            <span className={ui.badge}>{STATES.has(row.state) ? t(`state.${row.state}`) : row.state}</span>
          </div>
          <p className="text-sm text-muted">
            {row.valid_to
              ? t("period", { from: day(row.valid_from), to: day(row.valid_to) })
              : t("periodOpen", { from: day(row.valid_from) })}
          </p>
          {row.state === "active" && row.expires_in_days !== null ? (
            <p className="text-xs text-subtle" data-testid="expires-in">
              {t("expiresIn", { days: row.expires_in_days })}
            </p>
          ) : null}
          {row.state === "expired" || row.state === "revoked" ? (
            <p className="text-xs text-subtle">{t("noAccess")}</p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
