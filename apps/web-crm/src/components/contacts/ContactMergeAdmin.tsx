"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type ContactMerge = {
  id: string;
  source_id: string;
  target_id: string;
  source_name: string | null;
  target_name: string | null;
  status: string;
  reason: string | null;
  check_result: {
    blockers?: { code: string; detail: string }[];
    warnings?: { code: string; detail: string }[];
    references?: Record<string, number>;
  };
  result: { moved?: Record<string, number>; conflicts?: Record<string, number> } | null;
  created_at: string;
};
type Hit = { id: string; display_name: string };

function ContactPicker({ label, value, onChange }: { label: string; value: string; onChange: (id: string) => void }) {
  const t = useTranslations("ContactMerge");
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  async function search() {
    if (q.trim().length < 2) return;
    const res = await bff<{ items: Hit[] }>(`/api/bff/contacts?q=${encodeURIComponent(q.trim())}&page_size=8`);
    if (res.ok) setHits(res.data?.items ?? []);
  }
  return (
    <div className="flex flex-col gap-1">
      <label className={ui.label} htmlFor={`merge-${label}`}>
        {label}
      </label>
      <div className="flex gap-2">
        <input
          id={`merge-${label}`}
          className={ui.input}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void search();
            }
          }}
        />
        <button type="button" className={ui.button} onClick={() => void search()}>
          {t("search")}
        </button>
      </div>
      {hits.length > 0 ? (
        <select className={ui.input} aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">{t("choose")}</option>
          {hits.map((h) => (
            <option key={h.id} value={h.id}>
              {h.display_name}
            </option>
          ))}
        </select>
      ) : null}
    </div>
  );
}

/**
 * Kontakt-Zusammenführung (M3-03): Vorschlag mit Prüfung, Freigabe und Ausführung durch eine
 * zweite Person. Die Quelle bleibt als zusammengeführt erhalten, nichts wird gelöscht. Das
 * Backend prüft Rechte, Sperren und Vier-Augen; die Schaltflächen blenden nur aus.
 */
export function ContactMergeAdmin({ canPropose, canApprove }: { canPropose: boolean; canApprove: boolean }) {
  const t = useTranslations("ContactMerge");
  const [rows, setRows] = useState<ContactMerge[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    const res = await bff<ContactMerge[]>("/api/bff/contact-merges");
    if (res.ok) setRows(res.data ?? []);
    else setError(res.message);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(call: () => Promise<{ ok: boolean; message?: string }>) {
    setBusy(true);
    setError(null);
    const res = await call();
    setBusy(false);
    if (!res.ok) setError(res.message ?? t("error"));
    await load();
    return res.ok;
  }

  async function propose(e: React.FormEvent) {
    e.preventDefault();
    if (!source || !target || source === target) {
      setError(t("pickTwo"));
      return;
    }
    const ok = await run(() =>
      bff("/api/bff/contact-merges", { method: "POST", body: JSON.stringify({ source_id: source, target_id: target, reason: reason.trim() || null }) }),
    );
    if (ok) {
      setSource("");
      setTarget("");
      setReason("");
    }
  }

  async function decide(row: ContactMerge, action: "execute" | "reject") {
    if (action === "execute" && !window.confirm(t("executeConfirm", { source: row.source_name ?? "", target: row.target_name ?? "" }))) return;
    await run(() => bff(`/api/bff/contact-merges/${row.id}/${action}`, { method: "POST", body: JSON.stringify({}) }));
  }

  return (
    <div className="flex min-w-0 flex-col gap-6" data-testid="contact-merge-admin">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {canPropose ? (
        <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="merge-propose-title">
          <h2 id="merge-propose-title" className={ui.h2}>
            {t("propose.title")}
          </h2>
          <p className={ui.help}>{t("propose.intro")}</p>
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => void propose(e)} aria-label={t("proposeFormLabel")}>
            <ContactPicker label={t("propose.source")} value={source} onChange={setSource} />
            <ContactPicker label={t("propose.target")} value={target} onChange={setTarget} />
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className={ui.label}>{t("propose.reason")}</span>
              <input className={ui.input} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} />
            </label>
            <div className="sm:col-span-2">
              <button type="submit" className={ui.primary} disabled={busy}>
                {t("propose.submit")}
              </button>
            </div>
          </form>
        </section>
      ) : null}
      <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="merge-list-title">
        <h2 id="merge-list-title" className={ui.h2}>
          {t("list.title")}
        </h2>
        {rows === null ? (
          <p className="text-sm text-muted">{t("loading")}</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted">{t("list.empty")}</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {rows.map((r) => {
              const blockers = r.check_result.blockers ?? [];
              const warnings = r.check_result.warnings ?? [];
              const refs = Object.entries(r.check_result.references ?? {});
              return (
                <li key={r.id} className="rounded-md border border-border p-3" data-testid="contact-merge-row">
                  <p className="font-medium">
                    {r.source_name ?? r.source_id} {t("list.into")} {r.target_name ?? r.target_id}{" "}
                    <span className={ui.badge}>{t(`status.${r.status}`)}</span>
                  </p>
                  {r.reason ? <p className="text-sm text-muted">{r.reason}</p> : null}
                  {blockers.length > 0 ? (
                    <ul className="mt-2 list-disc pl-4 text-sm text-danger-fg">
                      {blockers.map((b) => (
                        <li key={b.code}>{b.detail}</li>
                      ))}
                    </ul>
                  ) : null}
                  {warnings.length > 0 ? (
                    <ul className="mt-2 list-disc pl-4 text-sm">
                      {warnings.map((w) => (
                        <li key={w.code}>{w.detail}</li>
                      ))}
                    </ul>
                  ) : null}
                  {refs.length > 0 ? (
                    <p className="mt-2 text-xs text-muted">
                      {t("list.references")}: {refs.map(([k, n]) => `${k} (${n})`).join(", ")}
                    </p>
                  ) : null}
                  {r.result?.conflicts && Object.keys(r.result.conflicts).length > 0 ? (
                    <p className="mt-2 text-xs text-muted">
                      {t("list.conflicts")}: {Object.entries(r.result.conflicts).map(([k, n]) => `${k} (${n})`).join(", ")}
                    </p>
                  ) : null}
                  {r.status === "proposed" && canApprove ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      <button type="button" className={ui.buttonSm} disabled={busy || blockers.length > 0} onClick={() => void decide(r, "execute")}>
                        {t("list.execute")}
                      </button>
                      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void decide(r, "reject")}>
                        {t("list.reject")}
                      </button>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
