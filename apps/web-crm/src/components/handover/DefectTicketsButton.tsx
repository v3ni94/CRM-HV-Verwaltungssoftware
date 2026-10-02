"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Mängel eines Übergabeprotokolls als Tickets anlegen (GAF-18). Legt Tickets an, bucht nichts. */
export function DefectTicketsButton({ protocolId, defectCount }: { protocolId: string; defectCount: number }) {
  const t = useTranslations("Af20.defectTickets");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (defectCount === 0) return null;
  const create = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ created: unknown[] }>(`/api/bff/handover/protocols/${protocolId}/defects/tickets`, { method: "POST", body: JSON.stringify({}) });
    setBusy(false);
    if (res.ok) setMessage(t("created", { count: res.data.created.length }));
    else setError(res.message);
  };
  return (
    <div className="flex flex-col gap-1" data-testid="defect-tickets">
      <button type="button" className={ui.button} disabled={busy} onClick={() => void create()}>
        {t("create", { count: defectCount })}
      </button>
      {message ? <p role="status" className={ui.notice}>{message}</p> : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}
