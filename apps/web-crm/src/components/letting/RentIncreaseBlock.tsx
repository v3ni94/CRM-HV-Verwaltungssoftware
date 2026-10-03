"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Props = {
  caseId: string;
  status: string;
  /** Proposal from the tenant switch (null without a configured duration, AN18-01). */
  proposal: string | null;
  blockSet: string | null;
  canRecord: boolean;
};

/** Mieterhöhungssperre nach Anwendung (GAK-202): zeigt den Vorschlag aus dem Mandantenschalter
 *  und setzt das Datum am Vertrag erst nach Bestätigung (Aktion ``set_block``). Die Plattform
 *  legt keine Sperrdauer fest; ohne Schalterwert gibt es keinen Vorschlag. */
export function RentIncreaseBlock({ caseId, status, proposal, blockSet, canRecord }: Props) {
  const t = useTranslations("RentIncreaseBlock");
  const router = useRouter();
  const [value, setValue] = useState(blockSet ?? proposal ?? "");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  if (status !== "applied") return null;

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    const res = await bff(`/api/bff/letting/rent-increases/${caseId}/actions`, {
      method: "POST",
      body: JSON.stringify({ action: "set_block", block_until: value }),
    });
    setBusy(false);
    if (res.ok) router.refresh();
    else setMessage(res.message);
  }

  return (
    <section className={`${ui.card} flex flex-col gap-2`} data-testid="rent-increase-block" aria-labelledby="block-title">
      <h2 id="block-title" className="font-medium">
        {t("title")}
      </h2>
      <p className="text-sm">{proposal ? t("proposal", { date: formatDate(proposal) }) : t("noProposal")}</p>
      {blockSet ? <p className={ui.success}>{t("set", { date: formatDate(blockSet) })}</p> : null}
      <p className={ui.help}>{t("hint")}</p>
      {canRecord ? (
        <form onSubmit={save} className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("label")}</span>
            <input className={ui.input} type="date" value={value} onChange={(e) => setValue(e.target.value)} required data-testid="block-date" />
          </label>
          <button type="submit" className={ui.primary} disabled={busy || !value}>
            {t("confirm")}
          </button>
        </form>
      ) : null}
      {message ? (
        <p role="alert" className={ui.alert}>
          {message}
        </p>
      ) : null}
    </section>
  );
}
