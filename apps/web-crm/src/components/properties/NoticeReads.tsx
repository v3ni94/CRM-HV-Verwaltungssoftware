"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

type Reads = {
  recipient_count: number;
  read_count: number;
  reads: { account_id: string; contact_id: string | null; read_at: string }[];
  note: string;
};

/** Lesestatus eines Aushangs (GAL-307, D34): zeigt, welche Portalkonten den Aushang bestätigt haben.
 *  Nur ein Indiz für die Kenntnisnahme, kein Zugangsnachweis und keine Rechtsfolge. */
export function NoticeReads({ noticeId }: { noticeId: string }) {
  const t = useTranslations("Notices");
  const [data, setData] = useState<Reads | null>(null);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    setError(null);
    const res = await bff<Reads>(`/api/bff/notices/${noticeId}/reads`);
    if (res.ok) setData(res.data);
    else setError(res.message);
  }

  return (
    <div className="flex flex-col gap-2">
      <button type="button" className={ui.buttonSm} aria-expanded={open} onClick={() => void toggle()}>
        {open ? t("readsHide") : t("readsShow")}
      </button>
      {open ? (
        <div className="text-sm" data-testid="notice-reads">
          {error ? (
            <p role="alert" className={ui.alert}>
              {error}
            </p>
          ) : data === null ? (
            <p className="text-muted">{t("loading")}</p>
          ) : (
            <>
              <p>{t("readsSummary", { read: data.read_count, total: data.recipient_count })}</p>
              {data.reads.length === 0 ? (
                <p className="text-muted">{t("readsNone")}</p>
              ) : (
                <ul className="flex flex-col gap-1">
                  {data.reads.map((r) => (
                    <li key={r.account_id} className="text-xs text-muted">
                      {formatDateTime(r.read_at)} · {t("readsContact")} {r.contact_id ? r.contact_id.slice(0, 8) : t("readsUnknown")}
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-xs text-muted">{t("readsNote")}</p>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
