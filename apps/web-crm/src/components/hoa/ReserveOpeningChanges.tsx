"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type OpeningChange = {
  id: string;
  status: "pending" | "applied" | "rejected";
  reason: string | null;
  changes: Record<string, { old: string | null; new: string | null }>;
  requested_at: string;
};

/** GAF-16: Änderungen des Anfangsbestands einer Rücklage freigeben oder ablehnen (zweite Person). */
export function ReserveOpeningChanges({ name, rows }: { name: string; rows: OpeningChange[] }) {
  const t = useTranslations("HoaAF09.opening");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const decide = async (id: string, action: "approve" | "reject") => {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/hoa/reserve-opening-changes/${id}/${action}`, { method: "POST", body: JSON.stringify({}) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    router.refresh();
  };
  return (
    <section className="flex flex-col gap-2" data-testid="reserve-opening-changes">
      <h3 className="font-medium">
        {t("title")}: {name}
      </h3>
      <p className="text-sm text-muted">{t("hint")}</p>
      {rows.length === 0 ? <p className="text-sm text-muted">{t("none")}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <ul className="flex flex-col gap-2 text-sm">
        {rows.map((c) => (
          <li key={c.id} className="rounded border border-border p-2">
            <div>
              {formatDateTime(c.requested_at)} · {t(`status.${c.status}`)}
              {c.reason ? ` · ${t("reason")}: ${c.reason}` : ""}
            </div>
            <ul className="text-muted">
              {Object.entries(c.changes).map(([field, v]) => (
                <li key={field}>
                  {field}: {t("from")} {v.old ?? "-"} → {t("to")} {v.new ?? "-"}
                </li>
              ))}
            </ul>
            {c.status === "pending" ? (
              <div className="mt-1 flex gap-2">
                <button type="button" className={ui.secondary} disabled={busy} onClick={() => void decide(c.id, "approve")}>
                  {t("approve")}
                </button>
                <button type="button" className={ui.secondary} disabled={busy} onClick={() => void decide(c.id, "reject")}>
                  {t("reject")}
                </button>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
