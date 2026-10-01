"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Case = { id: string; status: string; effective_date: string; target_rent: string };

/** Link between the contract form and the rent increase cases (M5-08): lists the cases of the
 *  contract and warns when an open case takes effect before the end of the lock date
 *  (``rent_increase_block_until``). The lock itself is checked by the case check of the API. */
export function RentIncreaseLinks({ contractId, blockUntil }: { contractId: string; blockUntil: string }) {
  const t = useTranslations("RentIncreaseLinks");
  const [cases, setCases] = useState<Case[] | null>(null);
  useEffect(() => {
    let alive = true;
    void bff<Case[]>(`/api/bff/letting/rent-increases?contract_id=${contractId}`).then((res) => {
      if (alive) setCases(res.ok ? res.data : []);
    });
    return () => {
      alive = false;
    };
  }, [contractId]);
  if (!cases || cases.length === 0) return null;
  const open = cases.filter((c) => !["applied", "cancelled", "rejected"].includes(c.status));
  const conflicts = blockUntil ? open.filter((c) => c.effective_date <= blockUntil) : [];
  return (
    <div className="flex flex-col gap-1 text-sm sm:col-span-full" data-testid="rent-increase-links">
      <span className={ui.label}>{t("title")}</span>
      <ul className="list-inside list-disc">
        {cases.map((c) => (
          <li key={c.id}>
            <Link href={`/vermietung/mieterhoehung/${c.id}`} className="underline">
              {t("case", { date: formatDate(c.effective_date) })}
            </Link>{" "}
            ({c.status})
          </li>
        ))}
      </ul>
      {conflicts.length ? (
        <p role="alert" className={ui.error}>
          {t("conflict", { date: formatDate(blockUntil) })}
        </p>
      ) : null}
    </div>
  );
}
