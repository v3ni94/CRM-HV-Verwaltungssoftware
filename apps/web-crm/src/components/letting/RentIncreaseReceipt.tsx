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
  receivedOn: string | null;
  /** contracts:approve, the permission of every process step of the case. */
  canRecord: boolean;
};

/** Zugangsdatum of the rent increase letter (handbook Mieterhöhung gap "Zugangsdatum nur
 *  über die Schnittstelle"): POST /letting/rent-increases/{id}/actions with action
 *  ``receipt``. The status of the case does not change; deadlines derived from it are
 *  orientation and appear only with released rent law rules. */
export function RentIncreaseReceipt({ caseId, status, receivedOn, canRecord }: Props) {
  const t = useTranslations("RentIncrease");
  const router = useRouter();
  const [value, setValue] = useState(receivedOn ?? "");
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const editable = canRecord && ["draft", "approved", "sent"].includes(status);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setState("saving");
    setMessage(null);
    const res = await bff(`/api/bff/letting/rent-increases/${caseId}/actions`, {
      method: "POST",
      body: JSON.stringify({ action: "receipt", received_on: value }),
    });
    if (res.ok) {
      setState("saved");
      router.refresh();
    } else {
      setState("error");
      setMessage(res.message);
    }
  }

  return (
    <section className={`${ui.card} flex flex-col gap-2`} data-testid="rent-increase-receipt" aria-labelledby="receipt-title">
      <h2 id="receipt-title" className="font-medium">
        {t("receipt.title")}
      </h2>
      <p className="text-sm">{receivedOn ? t("receipt.current", { date: formatDate(receivedOn) }) : t("receipt.none")}</p>
      <p className={ui.help}>{t("receipt.hint")}</p>
      {editable ? (
        <form onSubmit={save} className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("receipt.label")}</span>
            <input className={ui.input} type="date" value={value} onChange={(e) => setValue(e.target.value)} required data-testid="receipt-date" />
          </label>
          <button type="submit" className={ui.primary} disabled={state === "saving" || !value}>
            {t("receipt.save")}
          </button>
        </form>
      ) : null}
      {state === "saved" ? <p className={ui.success}>{t("receipt.saved")}</p> : null}
      {state === "error" ? (
        <p role="alert" className={ui.alert}>
          {message ?? t("receipt.error")}
        </p>
      ) : null}
    </section>
  );
}
