"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { WriteOffRequestButton } from "./WriteOffRequestButton";

export type DunningProof = {
  id: string;
  kind: string;
  proof_date: string;
  reference: string | null;
  note: string | null;
};
export type DunningInterestPeriod = {
  from: string;
  to: string;
  days: number;
  base_rate: string;
  spread: string;
  rate: string;
  amount: string;
};
export type DunningCaseInfo = {
  id: string;
  status: string;
  check_hints?: string[];
  interest_amount?: string | null;
  interest_entry_id?: string | null;
  interest_detail?: DunningInterestPeriod[] | null;
  interest_spread_suggestion?: { profile: string | null; spread: string | null; hinweis: string } | null;
  delivery_proofs?: DunningProof[];
  open_items?: { open_item_id: string; due_date: string; remaining: string }[] | null;
};
type Block = {
  id: string;
  open_item_id: string;
  reason_code: string;
  reason_label: string | null;
  note: string | null;
  active: boolean;
  created_at: string;
};

const PROOF_KINDS = ["registered_mail", "postal_receipt", "email_receipt", "portal_receipt", "other"] as const;
const BLOCK_REASONS = ["installment_plan", "disputed", "set_off", "litigation", "insolvency"] as const;

/** M16-01: Zustellnachweise am Mahnfall (Einschreiben, Post, E-Mail, Portal). */
export function DunningDeliveryProofs({ caseId, initial }: { caseId: string; initial: DunningProof[] }) {
  const t = useTranslations("DunningDetails");
  const [rows, setRows] = useState<DunningProof[]>(initial);
  const [f, setF] = useState({ kind: "registered_mail", proof_date: "", reference: "", note: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const add = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<DunningProof>(`/api/bff/accounting/dunning-cases/${caseId}/delivery-proofs`, {
      method: "POST",
      body: JSON.stringify({
        kind: f.kind,
        proof_date: f.proof_date,
        reference: f.reference.trim() || null,
        note: f.note.trim() || null,
      }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setRows((r) => [...r, res.data]);
    setF({ kind: "registered_mail", proof_date: "", reference: "", note: "" });
  };
  return (
    <section className="flex flex-col gap-2" data-testid="dunning-proofs">
      <h3 className={ui.h2}>{t("proofsTitle")}</h3>
      {rows.length === 0 ? (
        <p className={ui.help}>{t("proofsEmpty")}</p>
      ) : (
        <ul className="flex flex-col gap-1 text-sm">
          {rows.map((p) => (
            <li key={p.id}>
              {t(`proofKind.${p.kind}`)}, {formatDate(p.proof_date)}
              {p.reference ? `, ${p.reference}` : ""}
              {p.note ? <span className="text-muted"> ({p.note})</span> : null}
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("proofKindLabel")}</span>
          <select className={ui.input} value={f.kind} onChange={(e) => setF((v) => ({ ...v, kind: e.target.value }))}>
            {PROOF_KINDS.map((k) => (
              <option key={k} value={k}>{t(`proofKind.${k}`)}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("proofDate")}</span>
          <input className={ui.input} type="date" value={f.proof_date} onChange={(e) => setF((v) => ({ ...v, proof_date: e.target.value }))} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("proofReference")}</span>
          <input className={ui.input} value={f.reference} onChange={(e) => setF((v) => ({ ...v, reference: e.target.value }))} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("proofNote")}</span>
          <input className={ui.input} value={f.note} onChange={(e) => setF((v) => ({ ...v, note: e.target.value }))} />
        </label>
        <button type="button" className={ui.buttonSm} onClick={add} disabled={busy || !f.proof_date}>
          {t("proofAdd")}
        </button>
      </div>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}

/** M16-03: Mahnsperren je Posten mit strukturiertem Grund, setzen und aufheben. */
export function DunningItemBlocks({ items }: { items: { open_item_id: string; due_date: string; remaining: string }[] }) {
  const t = useTranslations("DunningDetails");
  const [blocks, setBlocks] = useState<Block[] | null>(null);
  const [reason, setReason] = useState<Record<string, string>>({});
  const [note, setNote] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    const all: Block[] = [];
    for (const i of items) {
      const res = await bff<Block[]>(`/api/bff/accounting/dunning-blocks?open_item_id=${i.open_item_id}&active=true`);
      if (!res.ok) return setError(res.message);
      all.push(...res.data);
    }
    setBlocks(all);
  }, [items]);
  useEffect(() => {
    void load();
  }, [load]);
  const set = async (id: string) => {
    setError(null);
    const res = await bff(`/api/bff/accounting/open-items/${id}/dunning-blocks`, {
      method: "POST",
      body: JSON.stringify({ reason_code: reason[id] || "installment_plan", note: (note[id] ?? "").trim() || null }),
    });
    if (!res.ok) return setError(res.message);
    await load();
  };
  const release = async (blockId: string) => {
    setError(null);
    const res = await bff(`/api/bff/accounting/dunning-blocks/${blockId}/release`, { method: "POST" });
    if (!res.ok) return setError(res.message);
    await load();
  };
  return (
    <section className="flex flex-col gap-2" data-testid="dunning-blocks">
      <h3 className={ui.h2}>{t("blocksTitle")}</h3>
      <p className={ui.help}>{t("blocksHint")}</p>
      {items.map((i) => {
        const active = (blocks ?? []).filter((b) => b.open_item_id === i.open_item_id);
        return (
          <div key={i.open_item_id} className="flex flex-wrap items-center gap-2 text-sm">
            <span>
              {formatDate(i.due_date)}, {formatEur(i.remaining)}
            </span>
            {active.map((b) => (
              <span key={b.id} className="inline-flex items-center gap-1">
                <span className={ui.badge}>{t(`blockReason.${b.reason_code}`)}</span>
                <button type="button" className={ui.buttonSm} onClick={() => void release(b.id)}>
                  {t("blockRelease")}
                </button>
              </span>
            ))}
            <select
              className={`${ui.input} w-44`}
              aria-label={t("blockReasonLabel")}
              value={reason[i.open_item_id] ?? "installment_plan"}
              onChange={(e) => setReason((v) => ({ ...v, [i.open_item_id]: e.target.value }))}
            >
              {BLOCK_REASONS.map((r) => (
                <option key={r} value={r}>{t(`blockReason.${r}`)}</option>
              ))}
            </select>
            <input
              className={`${ui.input} w-48`}
              aria-label={t("blockNote")}
              placeholder={t("blockNote")}
              value={note[i.open_item_id] ?? ""}
              onChange={(e) => setNote((v) => ({ ...v, [i.open_item_id]: e.target.value }))}
            />
            <button type="button" className={ui.buttonSm} onClick={() => void set(i.open_item_id)}>
              {t("blockSet")}
            </button>
            <WriteOffRequestButton openItemId={i.open_item_id} />
          </div>
        );
      })}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}

/** M16-02/05: Zinsberechnung je Basiszinssatzzeitraum und Zinsentwurf (nie eine Buchung). */
export function DunningInterestPanel({ c }: { c: DunningCaseInfo }) {
  const t = useTranslations("DunningDetails");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(Boolean(c.interest_entry_id));
  const amount = c.interest_amount ?? "0.00";
  const positive = Number(amount) > 0;
  const draft = async () => {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/accounting/dunning-cases/${c.id}/interest-draft`, { method: "POST" });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setDone(true);
    router.refresh();
  };
  const periods = c.interest_detail ?? [];
  return (
    <section className="flex flex-col gap-2" data-testid="dunning-interest">
      <h3 className={ui.h2}>{t("interestTitle")}</h3>
      {periods.length === 0 ? (
        <p className={ui.help}>{t("interestNone")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("periodFrom")}</th>
                <th>{t("periodTo")}</th>
                <th className="num">{t("days")}</th>
                <th className="num">{t("rate")}</th>
                <th className="num">{t("amount")}</th>
              </tr>
            </thead>
            <tbody>
              {periods.map((p) => (
                <tr key={`${p.from}-${p.to}`}>
                  <td>{formatDate(p.from)}</td>
                  <td>{formatDate(p.to)}</td>
                  <td className="num">{p.days}</td>
                  <td className="num">{p.rate} %</td>
                  <td className="num">{formatEur(p.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-sm">{t("interestTotal", { amount: formatEur(amount) })}</p>
      {positive ? (
        done ? (
          <span className={ui.badge}>{t("interestDrafted")}</span>
        ) : (
          <button type="button" className={ui.buttonSm} onClick={draft} disabled={busy}>
            {t("interestDraft")}
          </button>
        )
      ) : null}
      <p className={ui.help}>{t("interestDraftHint")}</p>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}

/** Prüfhinweise (M16-04) und Aufschlagsvorschlag (M16-06) plus die Bausteine oben. Alles
 * Hinweise an eine Person; nichts davon ändert Einstellungen oder bucht. */
export function DunningCaseDetails({ c }: { c: DunningCaseInfo }) {
  const t = useTranslations("DunningDetails");
  const spread = c.interest_spread_suggestion;
  return (
    <details className="mt-2 text-sm" data-testid="dunning-details">
      <summary className="cursor-pointer font-medium">{t("summary")}</summary>
      <div className="mt-2 flex flex-col gap-4">
        {(c.check_hints ?? []).length > 0 ? (
          <section data-testid="dunning-hints">
            <h3 className={ui.h2}>{t("hintsTitle")}</h3>
            <ul className="list-disc pl-5">
              {(c.check_hints ?? []).map((h) => (
                <li key={h}>{h}</li>
              ))}
            </ul>
          </section>
        ) : null}
        {spread ? (
          <section data-testid="dunning-spread">
            <h3 className={ui.h2}>{t("spreadTitle")}</h3>
            <p>
              {spread.profile && spread.spread != null
                ? t("spreadValue", { profile: t(`spreadProfile.${spread.profile}`), spread: spread.spread })
                : t("spreadNone")}
            </p>
            <p className={ui.help}>{spread.hinweis}</p>
          </section>
        ) : null}
        <DunningInterestPanel c={c} />
        <DunningDeliveryProofs caseId={c.id} initial={c.delivery_proofs ?? []} />
        {(c.open_items ?? []).length > 0 ? <DunningItemBlocks items={c.open_items ?? []} /> : null}
      </div>
    </details>
  );
}
