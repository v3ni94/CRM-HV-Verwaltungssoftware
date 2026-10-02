"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ui } from "@/lib/ui";

/** Object filter of the journal (Q15-01): reloads the page with ?property=<id>. */
export function JournalPropertyFilter({ ledgerId, current, properties }: { ledgerId: string; current: string; properties: { id: string; label: string }[] }) {
  const t = useTranslations("LedgerExtras.journalFilter");
  const router = useRouter();
  const [value, setValue] = useState(current);
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        router.push(value ? `/buchhaltung/${ledgerId}?property=${encodeURIComponent(value)}` : `/buchhaltung/${ledgerId}`);
      }}
    >
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("property")}</span>
        <select className={ui.input} value={value} onChange={(e) => setValue(e.target.value)}>
          <option value="">{t("all")}</option>
          {properties.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      <button type="submit" className={ui.button}>
        {t("apply")}
      </button>
    </form>
  );
}
