"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Lock = { id: string; period_from: string; period_to: string; source: string; reason: string | null; active: boolean };

/** GAF-13: read only display of the active period locks of the property of a statement
 *  (GET accounting/period-locks). Setting or releasing a lock stays in the accounting module. */
export function PeriodLocksPanel({ propertyId }: { propertyId: string }) {
  const t = useTranslations("BillingExtra.periodLocks");
  const [locks, setLocks] = useState<Lock[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    void bff<Lock[]>(`/api/bff/accounting/period-locks?property_id=${propertyId}&active=true`).then((res) => {
      if (!live) return;
      if (res.ok) setLocks(res.data ?? []);
      else setError(res.message);
    });
    return () => {
      live = false;
    };
  }, [propertyId]);
  return (
    <section className="flex flex-col gap-2" data-testid="period-locks">
      <h3 className={ui.h2}>{t("title")}</h3>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {locks && locks.length === 0 ? <p className={ui.help}>{t("none")}</p> : null}
      {locks && locks.length > 0 ? (
        <ul className="flex flex-col gap-1 text-sm">
          {locks.map((l) => (
            <li key={l.id}>
              {formatDate(l.period_from)} bis {formatDate(l.period_to)}{l.reason ? `, ${l.reason}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
