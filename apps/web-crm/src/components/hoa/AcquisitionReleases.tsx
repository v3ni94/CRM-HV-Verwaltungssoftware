"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** GA07-03 (W07): special acquisitions of the statement year need a request and a release by a
 *  second person. The allocation text is a proposal for review, not a legal rule. */

export type AcquisitionItem = {
  contract_id: string;
  unit_number: string;
  acquisition_kind: string | null;
  special_succession_liability: boolean;
  allocation_proposal: string;
  status: "open" | "requested" | "released";
};

export function AcquisitionReleases({ statementId, items, note }: { statementId: string; items: AcquisitionItem[]; note: string }) {
  const t = useTranslations("HoaAcquisition");
  const router = useRouter();
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (items.length === 0) return null;
  const act = async (item: AcquisitionItem, action: "request" | "release") => {
    setBusy(true);
    setError(null);
    const text = (notes[`${item.contract_id}:${action}`] ?? "").trim();
    const res = await bff(`/api/bff/hoa/statements/${statementId}/acquisitions/${item.contract_id}/${action}`, {
      method: "POST",
      body: JSON.stringify(action === "release" ? { note: text } : { note: text || null }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    router.refresh();
  };
  return (
    <section className={ui.card} data-testid="acquisition-releases">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      <p className="text-xs text-subtle">{note}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <ul className="mt-2 flex flex-col gap-3">
        {items.map((item) => (
          <li key={item.contract_id} className="flex flex-col gap-2 rounded border border-border p-3">
            <span className="font-medium">
              {t("unit", { unit: item.unit_number })}
              {item.acquisition_kind ? ` · ${t("kind", { kind: t(`kinds.${item.acquisition_kind}`) })}` : ""}
              {item.special_succession_liability ? ` · ${t("succession")}` : ""}
            </span>
            <span className="text-sm text-muted">
              {t("proposal")}: {item.allocation_proposal}
            </span>
            <span className="text-sm">{t(`status.${item.status}`)}</span>
            {item.status !== "released" ? (
              <div className="flex flex-wrap items-end gap-2">
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{item.status === "open" ? t("requestNote") : t("releaseNote")}</span>
                  <input
                    className={ui.input}
                    value={notes[`${item.contract_id}:${item.status === "open" ? "request" : "release"}`] ?? ""}
                    onChange={(e) => setNotes({ ...notes, [`${item.contract_id}:${item.status === "open" ? "request" : "release"}`]: e.target.value })}
                  />
                </label>
                {item.status === "open" ? (
                  <button type="button" className={ui.secondary} disabled={busy} onClick={() => void act(item, "request")}>
                    {t("request")}
                  </button>
                ) : (
                  <button
                    type="button"
                    className={ui.primary}
                    disabled={busy || (notes[`${item.contract_id}:release`] ?? "").trim().length < 3}
                    onClick={() => void act(item, "release")}
                  >
                    {t("release")}
                  </button>
                )}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
