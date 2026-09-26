"use client";

import { useFormatter, useTranslations } from "next-intl";
import Link from "next/link";

import type { Status } from "@/components/handover/types";
import { ui } from "@/lib/ui";

/** Shape of /api/v1/portal/handover-protocols (Mitarbeiter, M2-08 Rest). */
export type StaffProtocol = {
  id: string;
  number: string;
  version: number;
  kind: string;
  status: Status;
  handover_date: string | null;
  address: string;
  property: { id: string; number: string; name: string } | null;
  unit: { id: string; number: string; label: string | null } | null;
  unit_number: string | null;
  unit_label: string | null;
  floor: string | null;
  external_object_number: string | null;
  finalized: boolean;
  pdf_url: string;
};

const LOCKED: Status[] = ["completed", "sent", "archived", "cancelled"];

/** PDF via the file proxy of the portal (session cookie, allowlist in /api/portal-files). */
export function pdfHref(row: StaffProtocol): string {
  return `/api/portal-files${row.pdf_url.replace(/^\/api\/v1/, "")}`;
}

export function StaffProtocolList({ rows }: { rows: StaffProtocol[] }) {
  const t = useTranslations("HandoverStaff");
  const status = useTranslations("Handover.statusLabel");
  const format = useFormatter();
  if (rows.length === 0) return <p className={ui.notice}>{t("empty")}</p>;
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((row) => {
        const objectLine = row.property
          ? `${row.property.number} ${row.property.name}`
          : row.external_object_number
            ? `${t("manualObject")} ${row.external_object_number}`
            : row.address
              ? t("manualObject")
              : t("noObject");
        const unitLine = row.unit
          ? [row.unit.number, row.unit.label].filter(Boolean).join(" ")
          : [row.unit_number, row.unit_label].filter(Boolean).join(" ");
        return (
          <li key={row.id} className={`${ui.card} flex flex-col gap-2`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-medium">
                {row.number}
                {row.version > 1 ? ` ${t("version")} ${row.version}` : ""}
              </span>
              <span className={LOCKED.includes(row.status) ? ui.badge : ui.badgeGold}>
                {status(row.status)}
              </span>
            </div>
            <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
              <div>
                <dt className={ui.label}>{t("object")}</dt>
                <dd>
                  {objectLine}
                  {row.address ? <span className="block text-muted">{row.address}</span> : null}
                </dd>
              </div>
              <div>
                <dt className={ui.label}>{t("unit")}</dt>
                <dd>{unitLine || t("notSet")}</dd>
              </div>
              <div>
                <dt className={ui.label}>{t("date")}</dt>
                <dd>
                  {row.handover_date
                    ? format.dateTime(new Date(row.handover_date), {
                        day: "2-digit",
                        month: "2-digit",
                        year: "numeric",
                      })
                    : t("notSet")}
                </dd>
              </div>
            </dl>
            <div className="flex flex-wrap gap-2">
              <Link href={`/uebergabe/${row.id}`} className={ui.buttonSm}>
                {t("detail")}
              </Link>
              <a href={pdfHref(row)} target="_blank" rel="noreferrer" className={ui.buttonSm}>
                {t("pdf")}
              </a>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
