"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { GatedAction } from "@/components/gated/GatedAction";
import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import type { OpenItem } from "./OpenItemsTable";

export type WriteOff = {
  id: string;
  open_item_id: string;
  status: "proposed" | "approved" | "rejected";
  effective_on: string;
  amount: string;
  reason: string;
  decision_note: string | null;
  approval_enabled: boolean;
  revocation_status: "locked" | "awaiting_decision";
};
type Preview = {
  amount: string;
  posting_allowed: boolean;
  blockers: string[];
  lines: { side: "debit" | "credit"; account_number: string | null; amount: string; note: string | null }[];
};

/** AO01 (GAK-104): Ausbuchungsvorschläge offener Forderungen dieses Buchungskreises. Vorschlag
 *  ohne Wirkung; Freigabe nur mit Mandantenschalter, zweiter Person und G1 (GatedAction).
 *  Die Buchungsvorschau zeigt nur an, gebucht wird nichts (Gegenkonto offen, AN15-02). */
export function WriteOffPanel({
  items,
  today,
  canPropose,
  canApprove,
}: {
  items: OpenItem[];
  today: string;
  canPropose: boolean;
  canApprove: boolean;
}) {
  const t = useTranslations("WriteOffs");
  const receivables = items.filter((i) => i.kind === "receivable" && Number(i.remaining) > 0);
  const ids = new Set(items.map((i) => i.id));
  const [rows, setRows] = useState<WriteOff[] | null>(null);
  const [form, setForm] = useState({ open_item_id: "", effective_on: today, reason: "" });
  const [preview, setPreview] = useState<Record<string, Preview>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await bff<WriteOff[]>("/api/bff/accounting/open-item-write-offs");
    if (res.ok) setRows(res.data);
    else setError(res.message);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const propose = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    const res = await bff<WriteOff>("/api/bff/accounting/open-item-write-offs", {
      method: "POST",
      body: JSON.stringify({ ...form, reason: form.reason.trim() }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setForm({ open_item_id: "", effective_on: today, reason: "" });
    await load();
  };
  const reject = async (id: string) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    const res = await bff<WriteOff>(`/api/bff/accounting/open-item-write-offs/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ decision: "reject" }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    await load();
  };
  const showPreview = async (id: string) => {
    const res = await bff<Preview>(`/api/bff/accounting/open-item-write-offs/${id}/posting-preview`);
    if (res.ok) setPreview((p) => ({ ...p, [id]: res.data }));
    else setError(res.message);
  };

  const label = (id: string) => {
    const item = items.find((i) => i.id === id);
    return item ? `${item.account_number} ${formatDate(item.due_date)} ${formatEur(item.remaining)}` : id;
  };
  const mine = (rows ?? []).filter((r) => ids.has(r.open_item_id));
  const valid = form.open_item_id !== "" && form.reason.trim().length >= 10 && form.effective_on !== "" && form.effective_on <= today;

  return (
    <section className="flex flex-col gap-2" data-testid="write-off-panel">
      <h3 className={ui.h3}>{t("title")}</h3>
      <p className={ui.help}>{t("hint")}</p>
      {canPropose ? (
        <div className="flex flex-wrap items-end gap-2" data-testid="write-off-form">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("item")}</span>
            <select className={ui.input} value={form.open_item_id} onChange={(e) => setForm((f) => ({ ...f, open_item_id: e.target.value }))}>
              <option value="">{t("choose")}</option>
              {receivables.map((i) => (
                <option key={i.id} value={i.id}>{label(i.id)}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("effectiveOn")}</span>
            <input type="date" className={ui.input} max={today} value={form.effective_on} onChange={(e) => setForm((f) => ({ ...f, effective_on: e.target.value }))} />
          </label>
          <label className="flex flex-1 flex-col gap-1">
            <span className={ui.label}>{t("reason")}</span>
            <input className={ui.input} minLength={10} maxLength={500} value={form.reason} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} />
          </label>
          <button type="button" className={ui.button} disabled={!valid || busy} aria-busy={busy} onClick={() => void propose()}>
            {t("propose")}
          </button>
        </div>
      ) : null}
      {rows === null ? null : mine.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {mine.map((r) => (
            <li key={r.id} className="rounded border border-border p-2 text-sm" data-testid={`write-off-${r.id}`}>
              <p>
                <strong>{t(`status.${r.status}`)}</strong> {label(r.open_item_id)}, {t("asOf", { date: formatDate(r.effective_on) })}, {formatEur(r.amount)}
              </p>
              <p className="text-muted">{r.reason}</p>
              {r.decision_note ? <p className="text-muted">{r.decision_note}</p> : null}
              {r.status === "approved" ? <p className="text-xs text-muted">{t(`revocation.${r.revocation_status}`)}</p> : null}
              <div className="mt-1 flex flex-wrap items-start gap-2">
                <button type="button" className={ui.buttonSm} onClick={() => void showPreview(r.id)}>
                  {t("preview")}
                </button>
                {r.status === "proposed" && canApprove ? (
                  <>
                    <GatedAction<WriteOff>
                      gate="G1"
                      url={`/api/bff/accounting/open-item-write-offs/${r.id}/decision`}
                      body={{ decision: "approve" }}
                      label={t("approve")}
                      lockedText={t("lockedG1")}
                      blocked={!r.approval_enabled}
                      hint={r.approval_enabled ? t("fourEyes") : t("switchOff")}
                      onDone={() => void load()}
                      testId={`write-off-approve-${r.id}`}
                    />
                    <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void reject(r.id)}>
                      {t("reject")}
                    </button>
                  </>
                ) : null}
              </div>
              {preview[r.id] ? (
                <div className="mt-1" data-testid={`write-off-preview-${r.id}`}>
                  <ul className="text-xs">
                    {(preview[r.id]?.lines ?? []).map((l) => (
                      <li key={l.side}>
                        {t(`side.${l.side}`)}: {l.account_number ?? t("noAccount")} {formatEur(l.amount)}
                        {l.note ? ` (${l.note})` : ""}
                      </li>
                    ))}
                  </ul>
                  <p className="text-xs text-warning-fg">
                    {t("notPostable")}: {(preview[r.id]?.blockers ?? []).map((b) => t(`blocker.${b}`)).join(", ")}
                  </p>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}
