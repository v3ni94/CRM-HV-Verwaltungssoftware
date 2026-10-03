"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { GatedAction } from "@/components/gated/GatedAction";
import { MajorityCheckLine, type MajorityCheck } from "@/components/hoa/MajorityCheckLine";
import { AgendaResultForm, MEETING_KINDS } from "@/components/hoa/MeetingDetailsForm";
import { PlanDifferences } from "@/components/hoa/PlanDifferences";
import { StatementNewVersionDialog } from "@/components/hoa/StatementNewVersionDialog";
import { SUBJECT_KINDS } from "@/components/settings/MajorityRulesAdmin";
import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Key = { id: string; code: string; name: string };

function useCall() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const call = async <T,>(path: string, body?: unknown, confirmText?: string): Promise<T | null> => {
    if (confirmText && !window.confirm(confirmText)) return null;
    setBusy(true);
    setError(null);
    const res = await bff<T>(`/api/bff/hoa/${path}`, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return null;
    }
    router.refresh();
    return res.data;
  };
  return { busy, error, call, router };
}

function ErrorLine({ error }: { error: string | null }) {
  return error ? (
    <p role="alert" className={ui.alert}>
      {error}
    </p>
  ) : null;
}

/** Creates a plan, statement or meeting draft and opens it. */
export function HoaCreate({
  kind,
  ledgerId,
  legalEntityId,
  basePath,
  basisPlans = [],
  originMeetings = [],
}: {
  kind: "plan" | "statement" | "meeting";
  ledgerId?: string;
  legalEntityId: string;
  basePath: string;
  /** Earlier plans offered as comparison basis of a new plan (M24-04). */
  basisPlans?: { id: string; label: string }[];
  /** Earlier meetings of the same community, origin of a repeat or continuation (GA03-01). */
  originMeetings?: { id: string; label: string }[];
}) {
  const t = useTranslations("HoaWork");
  const { busy, error, call, router } = useCall();
  const year = new Date().getFullYear();
  const [value, setValue] = useState(kind === "meeting" ? "" : String(kind === "plan" ? year + 1 : year - 1));
  const [rhythm, setRhythm] = useState("monthly");
  const [dueDay, setDueDay] = useState("3");
  const [basisPlan, setBasisPlan] = useState("");
  const [meetingKind, setMeetingKind] = useState("ordinary");
  const [originId, setOriginId] = useState("");
  const needsOrigin = meetingKind === "repeat" || meetingKind === "continuation";
  const [localError, setLocalError] = useState<string | null>(null);
  const tKinds = useTranslations("HoaWork.meetingDetails");
  const create = async () => {
    setLocalError(null);
    if (kind === "meeting" && needsOrigin && !originId) {
      setLocalError(tKinds("originRequired"));
      return;
    }
    const body =
      kind === "plan"
        ? {
            ledger_id: ledgerId,
            year: Number(value),
            valid_from: `${value}-01-01`,
            payment_rhythm: rhythm,
            due_day: Number(dueDay) || 1,
            basis_plan_id: basisPlan || null,
          }
        : kind === "statement"
          ? { ledger_id: ledgerId, year: Number(value) }
          : {
              legal_entity_id: legalEntityId,
              scheduled_at: new Date(value).toISOString(),
              ...(meetingKind !== "ordinary" ? { kind: meetingKind } : {}),
              ...(needsOrigin ? { origin_meeting_id: originId } : {}),
            };
    const path = kind === "plan" ? "plans" : kind === "statement" ? "statements" : "meetings";
    const res = await call<{ id: string }>(path, body);
    if (res) router.push(`${basePath}/${kind === "plan" ? "plan" : kind === "statement" ? "abrechnung" : "versammlung"}/${res.id}`);
  };
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{kind === "meeting" ? t("scheduledAt") : t("year")}</span>
          <input
            className={ui.input}
            type={kind === "meeting" ? "datetime-local" : "number"}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </label>
        {kind === "meeting" ? (
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{tKinds("kind")}</span>
            <select className={ui.input} value={meetingKind} onChange={(e) => setMeetingKind(e.target.value)} data-testid="meeting-kind-select">
              {MEETING_KINDS.map((k) => (
                <option key={k} value={k}>
                  {tKinds(`kinds.${k}`)}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {kind === "meeting" && needsOrigin ? (
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{tKinds("origin")}</span>
            <select className={ui.input} value={originId} onChange={(e) => setOriginId(e.target.value)} data-testid="meeting-origin-select">
              <option value="">{tKinds("selectOrigin")}</option>
              {originMeetings.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {kind === "plan" ? (
          <>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("planRhythm")}</span>
              <select className={ui.input} value={rhythm} onChange={(e) => setRhythm(e.target.value)}>
                {["monthly", "quarterly", "yearly"].map((r) => (
                  <option key={r} value={r}>
                    {t(`rhythm.${r}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("planDueDayLabel")}</span>
              <input className={ui.input} type="number" min={1} max={28} value={dueDay} onChange={(e) => setDueDay(e.target.value)} />
            </label>
            {basisPlans.length ? (
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("comparisonBasisPlan")}</span>
                <select className={ui.input} value={basisPlan} onChange={(e) => setBasisPlan(e.target.value)}>
                  <option value="">{t("comparisonNoBasis")}</option>
                  {basisPlans.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </>
        ) : null}
        <button type="button" className={ui.button} onClick={create} disabled={busy || !value || (kind !== "meeting" && !ledgerId)}>
          {t(`create.${kind}`)}
        </button>
      </div>
      <ErrorLine error={localError ?? error} />
    </div>
  );
}

/** Plan item or statement cost item with allocation key; statement items need a basis. */
export function HoaItemForm({
  target,
  id,
  keys,
  accounts = [],
  subCommunities = [],
}: {
  target: "plan" | "statement";
  id: string;
  keys: Key[];
  accounts?: { id: string; number: string; name: string }[];
  /** AP21 / GAM-109: sub communities of the property (Mehrhausanlage). */
  subCommunities?: { id: string; code: string; name: string }[];
}) {
  const t = useTranslations("HoaWork");
  const { busy, error, call } = useCall();
  const [label, setLabel] = useState("");
  const [amount, setAmount] = useState("");
  const [key, setKey] = useState(keys.find((k) => k.code === "MEA")?.id ?? keys[0]?.id ?? "");
  const [component, setComponent] = useState("hoa_fee");
  const [basis, setBasis] = useState("");
  const [account, setAccount] = useState("");
  const [sub, setSub] = useState("");
  const ok = label.trim() && /^\d+([.,]\d{1,2})?$/.test(amount) && key && (target === "plan" || basis.trim().length >= 3);
  const add = async () => {
    const common = { label: label.trim(), amount: amount.replace(",", "."), allocation_key_id: key };
    const res =
      target === "plan"
        ? await call(`plans/${id}/items`, { ...common, component })
        : await call(`statements/${id}/costs`, { ...common, basis: basis.trim(), account_id: account || null, ...(sub ? { sub_community_id: sub } : {}) });
    if (res !== null) {
      setLabel("");
      setAmount("");
      setBasis("");
    }
  };
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("label")}</span>
          <input className={ui.input} value={label} onChange={(e) => setLabel(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("amount")}</span>
          <input className={ui.input} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("key")}</span>
          <select className={ui.input} value={key} onChange={(e) => setKey(e.target.value)}>
            {keys.map((k) => (
              <option key={k.id} value={k.id}>
                {k.code} {k.name}
              </option>
            ))}
          </select>
        </label>
        {target === "plan" ? (
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("component")}</span>
            <select className={ui.input} value={component} onChange={(e) => setComponent(e.target.value)}>
              <option value="hoa_fee">{t("components.hoa_fee")}</option>
              <option value="reserve">{t("components.reserve")}</option>
            </select>
          </label>
        ) : (
          <>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("basis")}</span>
              <input className={ui.input} value={basis} onChange={(e) => setBasis(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("account")}</span>
              <select className={ui.input} value={account} onChange={(e) => setAccount(e.target.value)}>
                <option value="">{t("noAccount")}</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.number} {a.name}
                  </option>
                ))}
              </select>
            </label>
            {subCommunities.length ? (
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("subCommunity.label")}</span>
                <select className={ui.input} value={sub} onChange={(e) => setSub(e.target.value)}>
                  <option value="">{t("subCommunity.none")}</option>
                  {subCommunities.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.code} {c.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
          </>
        )}
        <button type="button" className={ui.button} onClick={add} disabled={busy || !ok}>
          {t("addItem")}
        </button>
      </div>
      {sub ? <p className="text-xs text-muted">{t("subCommunity.basisHint")}</p> : null}
      <ErrorLine error={error} />
    </div>
  );
}

type ApplyRow = {
  unit_number: string;
  component: string;
  owner: string | null;
  contract_number: string | null;
  current: string | null;
  new: string;
  action: "create" | "unchanged" | "zero" | "no_contract";
  rhythm?: string;
  instalment?: string;
};
type ApplyPreview = {
  valid_from: string;
  snapshot_hash: string | null;
  applied_at: string | null;
  can_apply: boolean;
  rows: ApplyRow[];
  counts: { create: number; unchanged: number; zero: number; no_contract: number };
  posted_months: number;
};

/** Wirtschaftsplan into the payment plans (rule W02): preview of the standing amounts per
 *  ownership contract from the start date, then the confirmed takeover with the snapshot
 *  hash. The API demands a second person (not the plan's creator); the rows are contract
 *  master data, the receivable run reads them only behind G1. */
export function PlanApplyPreview({ id, snapshotHash }: { id: string; snapshotHash: string | null }) {
  const t = useTranslations("HoaWork");
  const { busy, error, call } = useCall();
  const [preview, setPreview] = useState<ApplyPreview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [applied, setApplied] = useState<number | null>(null);
  const load = async () => {
    setLoadError(null);
    const res = await bff<ApplyPreview>(`/api/bff/hoa/plans/${id}/apply/preview`);
    if (res.ok) setPreview(res.data);
    else setLoadError(res.message);
  };
  const apply = async () => {
    if (!preview) return;
    const res = await call<{ payments_created: number }>(`plans/${id}/apply`, { confirm: true, snapshot_hash: preview.snapshot_hash ?? snapshotHash }, t("confirmApply"));
    if (res) setApplied(res.payments_created);
  };
  return (
    <div className="flex w-full flex-col gap-2" data-testid="plan-apply-preview">
      {!preview ? (
        <button type="button" className={ui.primary} onClick={() => void load()} data-testid="plan-apply-load">
          {t("preview")}
        </button>
      ) : (
        <>
          <p className={ui.subtitle}>{t("previewTitle")}</p>
          <p className={ui.help}>{t("previewIntro")}</p>
          <div className="overflow-x-auto">
            <table className="mhvp-table">
              <thead>
                <tr>
                  <th>{t("unit")}</th>
                  <th>{t("owner")}</th>
                  <th>{t("component")}</th>
                  <th className="num">{t("current")}</th>
                  <th className="num">{t("new", { date: formatDate(preview.valid_from) })}</th>
                  <th>{t("action")}</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((r) => (
                  <tr key={`${r.unit_number}-${r.component}`} data-testid={`plan-apply-row-${r.unit_number}-${r.component}`}>
                    <td>{r.unit_number}</td>
                    <td>{r.owner ?? ""}</td>
                    <td>{t(`components.${r.component}`)}</td>
                    <td className="num">{r.current ? formatEur(r.current) : ""}</td>
                    <td className="num">
                      {formatEur(r.new)}
                      {r.rhythm && r.rhythm !== "monthly" && r.instalment ? (
                        <span className="block text-xs text-muted" data-testid={`plan-apply-instalment-${r.unit_number}-${r.component}`}>
                          {t(`rhythm.${r.rhythm}`)}: {formatEur(r.instalment)}
                        </span>
                      ) : null}
                    </td>
                    <td>{t(`actions.${r.action}`)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted">{t("counts", preview.counts)}</p>
          {preview.posted_months > 0 ? <p className={ui.notice}>{t("postedMonths", { count: preview.posted_months })}</p> : null}
          {preview.posted_months > 0 ? <PlanDifferences id={id} /> : null}
          {preview.applied_at ? <p className={ui.success}>{t("alreadyApplied", { date: formatDate(preview.applied_at.slice(0, 10)) })}</p> : null}
          {applied !== null ? <p className={ui.success}>{t("applied", { count: applied })}</p> : null}
          {preview.can_apply && applied === null ? (
            <div className={ui.formActions}>
              <button type="button" className={ui.primary} onClick={() => void apply()} disabled={busy} data-testid="plan-apply-confirm">
                {t("confirmApplyPreview")}
              </button>
            </div>
          ) : null}
        </>
      )}
      <ErrorLine error={loadError ?? error} />
    </div>
  );
}

export type ResolutionOption = {
  id: string;
  number?: number | null;
  decided_on: string;
  subject: string;
  status: string;
  subject_type?: string | null;
  subject_id?: string | null;
  snapshot_hash?: string | null;
};

/** Status steps for plan or statement. "Beschluss" records the resolution bound to the current
 *  snapshot hash (W06) and moves to resolved in one step. Issue, due and post sit behind GatedAction G4 (GAM-101). */
export function HoaSteps({
  target,
  id,
  status,
  legalEntityId,
  snapshotHash,
  resolutions = [],
}: {
  target: "plan" | "statement";
  id: string;
  status: string;
  legalEntityId: string;
  snapshotHash: string | null;
  resolutions?: ResolutionOption[];
}) {
  const t = useTranslations("HoaWork");
  const { busy, error, call, router } = useCall();
  const [decidedOn, setDecidedOn] = useState("");
  const [wording, setWording] = useState("");
  const [chosen, setChosen] = useState("");
  const subjectType = target === "plan" ? "economic_plan" : "hoa_statement";
  // GAM-102: only passed resolutions of this subject; where the list carries the binding fields
  // they must match, the API stays the authority for the snapshot hash.
  const candidates = resolutions.filter(
    (r) =>
      ["positive", "final", "legally_binding"].includes(r.status) &&
      (r.subject_type == null || r.subject_type === subjectType) &&
      (r.subject_id == null || r.subject_id === id) &&
      (r.snapshot_hash == null || r.snapshot_hash === snapshotHash),
  );
  const useExisting = async () => {
    if (!chosen) return;
    await call(`${base}/transition`, { target: "resolved", resolution_id: chosen });
  };
  const base = target === "plan" ? `plans/${id}` : `statements/${id}`;
  const resolve = async () => {
    const res = await call<{ id: string }>("resolutions", {
      legal_entity_id: legalEntityId,
      decided_on: decidedOn,
      subject: t(target === "plan" ? "resolutionSubject.plan" : "resolutionSubject.statement"),
      wording: wording.trim() || t(target === "plan" ? "resolutionWording.plan" : "resolutionWording.statement"),
      status: "positive",
      kind: "external",
      subject_type: target === "plan" ? "economic_plan" : "hoa_statement",
      subject_id: id,
      snapshot_hash: snapshotHash,
    });
    if (res) await call(`${base}/transition`, { target: "resolved", resolution_id: res.id });
  };
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-2">
        {status === "draft" ? (
          <button type="button" className={ui.primary} onClick={() => call(`${base}/calculate`)} disabled={busy}>
            {t("calculate")}
          </button>
        ) : null}
        {status === "calculated" ? (
          <button type="button" className={ui.primary} onClick={() => call(`${base}/transition`, { target: "internally_approved" })} disabled={busy}>
            {t("approveInternal")}
          </button>
        ) : null}
        {status === "internally_approved" || status === "board_reviewed" ? (
          <div className="flex w-full flex-col gap-2" data-testid="resolution-step">
            {candidates.length > 0 ? (
              <div className="flex flex-wrap items-end gap-2" data-testid="resolution-existing">
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("existingResolution")}</span>
                  <select className={ui.input} value={chosen} onChange={(e) => setChosen(e.target.value)}>
                    <option value="">{t("noResolutionChosen")}</option>
                    {candidates.map((r) => (
                      <option key={r.id} value={r.id}>
                        {`${r.number ?? ""} ${formatDate(r.decided_on)} ${r.subject}`.trim()}
                      </option>
                    ))}
                  </select>
                </label>
                <button type="button" className={ui.primary} onClick={useExisting} disabled={busy || !chosen} data-testid="resolution-use-existing">
                  {t("useExisting")}
                </button>
                <span className={ui.help}>{t("existingResolutionHint")}</span>
              </div>
            ) : null}
            <details open={candidates.length === 0} data-testid="resolution-new">
              <summary className="cursor-pointer text-sm">{t("newResolutionException")}</summary>
              <div className="mt-2 flex flex-wrap items-end gap-2">
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("decidedOn")}</span>
                  <input type="date" className={ui.input} value={decidedOn} onChange={(e) => setDecidedOn(e.target.value)} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("resolutionWordingLabel")}</span>
                  <textarea className={ui.input} rows={2} value={wording} placeholder={t(target === "plan" ? "resolutionWording.plan" : "resolutionWording.statement")} onChange={(e) => setWording(e.target.value)} />
                </label>
                <button type="button" className={ui.primary} onClick={resolve} disabled={busy || !decidedOn || !snapshotHash}>
                  {t("recordResolution")}
                </button>
              </div>
            </details>
          </div>
        ) : null}
        {target === "plan" && status === "resolved" ? <PlanApplyPreview id={id} snapshotHash={snapshotHash} /> : null}
        {target === "statement" && status === "resolved" ? (
          <GatedAction
            gate="G4"
            url={`/api/bff/hoa/${base}/transition`}
            label={t("issue")}
            lockedText={t("lockedG4")}
            body={{ target: "issued" }}
            onDone={() => router.refresh()}
            testId="hoa-step-issue"
          />
        ) : null}
        {target === "statement" && status === "issued" ? (
          <GatedAction
            gate="G4"
            url={`/api/bff/hoa/${base}/transition`}
            label={t("due")}
            lockedText={t("lockedG4")}
            body={{ target: "due" }}
            onDone={() => router.refresh()}
            testId="hoa-step-due"
          />
        ) : null}
        {target === "statement" && status === "due" ? (
          <GatedAction
            gate="G4"
            url={`/api/bff/hoa/${base}/post`}
            label={t("post")}
            lockedText={t("lockedG4")}
            confirmText={t("confirmPost")}
            onDone={() => router.refresh()}
            testId="hoa-step-post"
          />
        ) : null}
        {target === "statement" && status !== "draft" ? (
          <StatementNewVersionDialog statementId={id} legalEntityId={legalEntityId} disabled={busy} />
        ) : null}
      </div>
      <ErrorLine error={error} />
    </div>
  );
}

/** Agenda, invitation, tally and announcement of an owners' meeting (M25). */
export type MajorityRule = {
  id: string;
  label: string;
  principle: string;
  share_of_votes_cast: string | null;
  strictly_greater: boolean;
  min_mea_share_of_all: string | null;
  unanimous: boolean;
  source: string;
  valid_from: string;
  valid_to: string | null;
  /** AN06 / GAJ-602: "draft" only for rules created under the four eyes switch. */
  approval_status?: "draft" | "approved";
};

/** Majority rules per community with their source (M25-01, decided 24.09.2026). The tally
 *  evaluates the chosen rule; the announcement stays a human decision. */
export function MajorityRules({ legalEntityId, rules }: { legalEntityId: string; rules: MajorityRule[] }) {
  const t = useTranslations("HoaWork");
  const { busy, error, call } = useCall();
  const empty = { label: "", principle: "head", share: "", greater: true, mea: "", unanimous: false, source: "", from: "" };
  const [f, setF] = useState(empty);
  // Percent to ratio as an exact decimal string (no float): "66,67" -> "0.6667".
  const share = (v: string) => {
    if (!v) return null;
    const [whole = "0", frac = ""] = v.replace(",", ".").split(".");
    const digits = whole.padStart(3, "0") + frac;
    const ratio = `${digits.slice(0, -2 - frac.length) || "0"}.${digits.slice(-2 - frac.length)}`;
    return ratio.replace(/^0+(?=\d)/, "").replace(/\.?0+$/, "") || "0";
  };
  const pct = /^\d+([.,]\d+)?$/;
  const valid =
    f.label.trim().length >= 3 &&
    f.source.trim().length >= 3 &&
    f.from &&
    (f.unanimous || pct.test(f.share) || pct.test(f.mea)) &&
    (!f.share || pct.test(f.share)) &&
    (!f.mea || pct.test(f.mea));
  const create = async () => {
    const res = await call("majority-rules", {
      legal_entity_id: legalEntityId,
      label: f.label.trim(),
      principle: f.principle,
      share_of_votes_cast: share(f.share),
      strictly_greater: f.greater,
      min_mea_share_of_all: share(f.mea),
      unanimous: f.unanimous,
      source: f.source.trim(),
      valid_from: f.from,
    });
    if (res !== null) setF(empty);
  };
  const describe = (r: MajorityRule) =>
    [
      r.unanimous ? t("rule.unanimousText") : null,
      r.share_of_votes_cast
        ? t(r.strictly_greater ? "rule.moreThan" : "rule.atLeast", { p: String(Number(r.share_of_votes_cast) * 100).replace(".", ",") })
        : null,
      r.min_mea_share_of_all ? t("rule.meaMin", { p: String(Number(r.min_mea_share_of_all) * 100).replace(".", ",") }) : null,
    ]
      .filter(Boolean)
      .join(", ");
  return (
    <section className={ui.card}>
      <h2 className={ui.h2}>{t("rule.title")}</h2>
      {rules.length ? (
        <ul className="mt-1 text-sm">
          {rules.map((r) => (
            <li key={r.id}>
              <span className="font-medium">{r.label}</span> ({t(`principle.${r.principle}`)}): {describe(r)} ·{" "}
              <span className="text-muted">{r.source}</span>
              {r.approval_status === "draft" ? (
                <span className="ml-2 inline-flex flex-wrap items-center gap-2" data-testid={`rule-draft-${r.id}`}>
                  <span className={ui.badge}>{t("rule.draft")}</span>
                  <button
                    type="button"
                    className={ui.buttonSm}
                    disabled={busy}
                    title={t("rule.approveHint")}
                    onClick={() => void call(`majority-rules/${r.id}/approve`, undefined, t("rule.approveHint"))}
                  >
                    {t("rule.approve")}
                  </button>
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">{t("rule.none")}</p>
      )}
      <div className="mt-2 grid gap-2 sm:grid-cols-4">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("rule.label")}</span>
          <input className={ui.input} value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("rule.principle")}</span>
          <select className={ui.input} value={f.principle} onChange={(e) => setF({ ...f, principle: e.target.value })}>
            {["head", "mea", "unit"].map((p) => (
              <option key={p} value={p}>
                {t(`principle.${p}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("rule.share")}</span>
          <input className={ui.input} value={f.share} onChange={(e) => setF({ ...f, share: e.target.value })} />
        </label>
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={f.greater} onChange={(e) => setF({ ...f, greater: e.target.checked })} />
          {t("rule.strictly")}
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("rule.mea")}</span>
          <input className={ui.input} value={f.mea} onChange={(e) => setF({ ...f, mea: e.target.value })} />
        </label>
        <label className="flex items-center gap-1 text-sm">
          <input type="checkbox" checked={f.unanimous} onChange={(e) => setF({ ...f, unanimous: e.target.checked })} />
          {t("rule.unanimous")}
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("rule.source")}</span>
          <input className={ui.input} value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("rule.from")}</span>
          <input type="date" className={ui.input} value={f.from} onChange={(e) => setF({ ...f, from: e.target.value })} />
        </label>
      </div>
      <button type="button" className={`${ui.button} mt-2`} disabled={busy || !valid} onClick={create}>
        {t("rule.add")}
      </button>
      <ErrorLine error={error} />
    </section>
  );
}

export function MeetingPanel({
  id,
  status,
  agenda,
  rules = [],
}: {
  id: string;
  status: string;
  rules?: MajorityRule[];
  agenda: {
    id: string;
    position: number;
    title: string;
    majority: string;
    resolution: { number: number; status: string } | null;
    result?: string | null;
    minutes_text?: string | null;
  }[];
}) {
  const t = useTranslations("HoaWork");
  const tr = useTranslations("MajorityRules");
  const { busy, error, call } = useCall();
  const [title, setTitle] = useState("");
  const [proposal, setProposal] = useState("");
  const [ruleId, setRuleId] = useState("");
  const [majority, setMajority] = useState("simple");
  const tAgenda = useTranslations("HoaWork.agendaResult");
  const [invitedAt, setInvitedAt] = useState("");
  const [urgency, setUrgency] = useState("");
  const [tallies, setTallies] = useState<Record<string, { yes: string; no: string; abstain: string; proposal: string | null; manual_check: boolean }>>({});
  const [basis, setBasis] = useState(t("simpleMajority"));
  const [subjectKinds, setSubjectKinds] = useState<Record<string, string>>({});
  const [checks, setChecks] = useState<Record<string, MajorityCheck | null>>({});
  const announce = async (itemId: string, outcome: string) => {
    const res = await call<{ majority_check: MajorityCheck | null }>(
      `agenda/${itemId}/announce`,
      { outcome, majority_basis: basis, ...(subjectKinds[itemId] ? { subject_kind: subjectKinds[itemId] } : {}) },
      t("confirmAnnounce"),
    );
    if (res) setChecks((prev) => ({ ...prev, [itemId]: res.majority_check }));
  };
  const tally = async (itemId: string) => {
    const res = await bff<{ yes: string; no: string; abstain: string; proposal: string | null; manual_check: boolean }>(
      `/api/bff/hoa/agenda/${itemId}/tally`,
    );
    if (res.ok) setTallies((prev) => ({ ...prev, [itemId]: res.data }));
  };
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-2 text-sm">
        {agenda.map((a) => {
          const r = tallies[a.id];
          return (
            <li key={a.id} className={ui.card}>
              <div className="font-medium">
                TOP {a.position}: {a.title}
              </div>
              {a.resolution ? (
                <div className="text-muted">
                  {t("announced", { number: a.resolution.number, status: t(`resolutionStatus.${a.resolution.status}`) })}
                  {checks[a.id] ? <MajorityCheckLine check={checks[a.id] as MajorityCheck} /> : null}
                </div>
              ) : status === "held" && (a.result === "deferred" || a.result === "no_vote") ? null : status === "held" ? (
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <button type="button" className={ui.button} onClick={() => tally(a.id)}>
                    {t("tally")}
                  </button>
                  {r ? (
                    <span data-testid={`tally-${a.id}`}>
                      {t("votes", { yes: r.yes, no: r.no, abstain: r.abstain })}
                      {r.manual_check ? ` · ${t("manualCheck")}` : ""}
                    </span>
                  ) : null}
                  <label className="flex items-center gap-1">
                    <span className={ui.label}>{t("subjectKind")}</span>
                    <select
                      className={ui.input}
                      aria-label={t("subjectKind")}
                      value={subjectKinds[a.id] ?? ""}
                      onChange={(e) => setSubjectKinds((prev) => ({ ...prev, [a.id]: e.target.value }))}
                    >
                      <option value="">{t("subjectKindNone")}</option>
                      {SUBJECT_KINDS.map((k) => (
                        <option key={k} value={k}>
                          {tr(`subjectKinds.${k}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                  {r?.proposal ? (
                    <button
                      type="button"
                      className={ui.primary}
                      disabled={busy}
                      onClick={() => announce(a.id, r.proposal as string)}
                    >
                      {t("announce", { outcome: t(`resolutionStatus.${r.proposal}`) })}
                    </button>
                  ) : null}
                </div>
              ) : null}
              {status === "held" || status === "closed" ? (
                <AgendaResultForm itemId={a.id} result={a.result ?? null} minutesText={a.minutes_text ?? null} closed={status === "closed"} />
              ) : null}
            </li>
          );
        })}
      </ul>
      {status === "held" ? (
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("majorityBasis")}</span>
          <input className={ui.input} value={basis} onChange={(e) => setBasis(e.target.value)} />
        </label>
      ) : null}
      {status === "planned" ? (
        <>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("agendaTitle")}</span>
              <input className={ui.input} value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("proposal")}</span>
              <input className={ui.input} value={proposal} onChange={(e) => setProposal(e.target.value)} />
            </label>
            {rules.length ? (
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("rule.choose")}</span>
                <select className={ui.input} value={ruleId} onChange={(e) => setRuleId(e.target.value)}>
                  <option value="">{t("rule.simple")}</option>
                  {rules.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {ruleId ? null : (
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{tAgenda("majority")}</span>
                <select className={ui.input} value={majority} onChange={(e) => setMajority(e.target.value)} data-testid="agenda-majority">
                  <option value="simple">{tAgenda("simple")}</option>
                  <option value="all_owners">{tAgenda("allOwners")}</option>
                </select>
              </label>
            )}
            <button
              type="button"
              className={ui.button}
              disabled={busy || title.trim().length < 3}
              onClick={async () => {
                if ((await call(`meetings/${id}/agenda`, {
                    title: title.trim(),
                    proposal: proposal.trim() || null,
                    ...(ruleId ? { rule_id: ruleId } : majority !== "simple" ? { majority } : {}),
                  })) !== null) {
                  setTitle("");
                  setProposal("");
                }
              }}
            >
              {t("addAgenda")}
            </button>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("invitedAt")}</span>
              <input type="date" className={ui.input} value={invitedAt} onChange={(e) => setInvitedAt(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("urgency")}</span>
              <input className={ui.input} value={urgency} onChange={(e) => setUrgency(e.target.value)} />
            </label>
            <button
              type="button"
              className={ui.primary}
              disabled={busy || !invitedAt}
              onClick={() => call(`meetings/${id}/invite`, { invited_at: invitedAt, urgency_reason: urgency.trim() || null })}
            >
              {t("invite")}
            </button>
          </div>
        </>
      ) : null}
      <ErrorLine error={error} />
    </div>
  );
}
