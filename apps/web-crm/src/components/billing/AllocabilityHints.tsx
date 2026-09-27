"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type AllocabilityHint = { code: string; level: "info" | "warning"; position: string; message: string };
type Check = { statement_id: string; source: string; hints: AllocabilityHint[]; warnings: number };

/** Review hints on the allocability of the cost positions (M17-01, BetrKV catalogue): a list
 *  of proposals for a person, never a lock. Reads the preview endpoint; when a snapshot
 *  already carries `allocability_hints`, the server page passes them as `initial`. */
export function AllocabilityHints({ id, initial }: { id: string; initial?: AllocabilityHint[] | null }) {
  const t = useTranslations("Billing.allocability");
  const [hints, setHints] = useState<AllocabilityHint[] | null>(initial ?? null);
  const [source, setSource] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void bff<Check>(`/api/bff/statements/${id}/allocability-check`).then((res) => {
      if (!active) return;
      if (res.ok) {
        setHints(res.data.hints);
        setSource(res.data.source);
      } else setError(res.message);
    });
    return () => {
      active = false;
    };
  }, [id]);

  return (
    <section className={ui.card} aria-label={t("title")}>
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className={ui.help}>{t("notice")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {hints && hints.length === 0 ? <p className={`${ui.help} mt-2`}>{t("none")}</p> : null}
      {hints && hints.length > 0 ? (
        <ul className="mt-2 flex flex-col gap-1">
          {hints.map((h, i) => (
            <li key={`${h.code}-${i}`} className="flex items-start gap-2 text-sm">
              <span className={h.level === "warning" ? ui.badgeWarning : ui.badge}>{t(`level.${h.level}`)}</span>
              <span>{h.message}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {source ? <p className={`${ui.help} mt-2`}>{t("source", { source })}</p> : null}
    </section>
  );
}
