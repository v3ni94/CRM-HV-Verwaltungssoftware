"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { StatusPill, type StatusPillVariant } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import { formatRate } from "./MatchingMetricsCard";

export type LevelRequest = {
  id: string;
  case_kind: string;
  level_from: string;
  level_to: string;
  reason: string;
  status: "requested" | "approved" | "rejected" | string;
  requested_by: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_comment: string | null;
  created_at: string;
};

export type LevelsOut = {
  levels: Record<string, string>;
  caps: Record<string, string>;
  labels: Record<string, string>;
  auto_posting_enabled: boolean;
  auto_posting_outgoing_enabled: boolean;
  learning_enabled: boolean;
  blocked: Record<string, number>;
  requests: LevelRequest[];
  note: string;
};

export type ClassMetrics = {
  case_kind: string;
  legal_entity_id: string | null;
  n_decided: number;
  n_accepted_unchanged: number;
  n_modified: number;
  n_rejected: number;
  n_auto: number;
  n_auto_reversed: number;
  n_total: number;
  precision_manual: string | null;
  error_rate_auto: string | null;
  coverage: string | null;
  days_at_level: number | null;
};

export type MetricsOut = { window_from: string; window_to: string; classes: ClassMetrics[] };

const CLASSES = ["debtor_full", "debtor_collective", "creditor_invoice", "recurring_expense", "transfer_pair", "excluded"];
const LEVEL_VARIANT: Record<string, StatusPillVariant> = { L0: "neutral", L1: "gold", L2: "warning", L3: "danger" };
const STATUS_VARIANT: Record<string, StatusPillVariant> = { requested: "gold", approved: "success", rejected: "neutral" };

/** Next level of a class, or null at its cap (the API refuses more than one step). */
export function nextLevel(current: string, cap: string): string | null {
  const order = ["L0", "L1", "L2", "L3"];
  const next = order[order.indexOf(current) + 1];
  return next && order.indexOf(next) <= order.indexOf(cap) ? next : null;
}

export type AutomationLevelsProps = { canApprove: boolean; userId: string | null };

/** Automatikstufen je Fallklasse (ADR 0014 Nachtrag S4, Regel M12-05): Stufe, Deckel, Kennzahlen
 *  (precision_manual, n_decided, n_auto, Fehlerquote, Abdeckung) je Klasse, Antrag auf die nächste
 *  Stufe mit Grund, Freigabe durch eine andere Person, sofortige Absenkung. Keine Stufe bucht
 *  hier etwas und keine öffnet ein Gate. */
export function AutomationLevels({ canApprove, userId }: AutomationLevelsProps) {
  const t = useTranslations("Bank.levels");
  const [state, setState] = useState<LevelsOut | null>(null);
  const [metrics, setMetrics] = useState<MetricsOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [requesting, setRequesting] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    const [lv, mt] = await Promise.all([bff<LevelsOut>("/api/bff/banking/automation/levels"), bff<MetricsOut>("/api/bff/banking/automation/metrics")]);
    if (lv.ok) setState(lv.data);
    else setError(lv.message);
    if (mt.ok) setMetrics(mt.data);
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const metric = (kind: string) => metrics?.classes.find((c) => c.case_kind === kind && c.legal_entity_id === null);

  const request = async (kind: string) => {
    if (!state) return;
    const target = nextLevel(state.levels[kind] ?? "L0", state.caps[kind] ?? "L0");
    if (!target || reason.trim().length < 3) return;
    setBusy(kind);
    setError(null);
    const res = await bff<LevelRequest>("/api/bff/banking/automation/level-requests", {
      method: "POST",
      body: JSON.stringify({ case_kind: kind, level_to: target, reason: reason.trim() }),
    });
    setBusy(null);
    if (res.ok) {
      setNotice(t("requested", { level: target }));
      setRequesting(null);
      setReason("");
      load();
    } else setError(res.message);
  };

  const lower = async (kind: string) => {
    if (!state) return;
    const current = state.levels[kind] ?? "L0";
    if (current === "L0") return;
    const target = `L${Number(current.slice(1)) - 1}`;
    setBusy(kind);
    setError(null);
    const res = await bff<Record<string, string>>("/api/bff/banking/automation/levels", {
      method: "PUT",
      body: JSON.stringify({ case_kind: kind, level: target, reason: t("lowerReason") }),
    });
    setBusy(null);
    if (res.ok) load();
    else setError(res.message);
  };

  const decide = async (req: LevelRequest, action: "approve" | "reject") => {
    setBusy(req.id);
    setError(null);
    const res = await bff<LevelRequest>(`/api/bff/banking/automation/level-requests/${req.id}/${action}`, { method: "POST", body: "{}" });
    setBusy(null);
    if (res.ok) load();
    else setError(res.message);
  };

  const none = t("noBase");
  return (
    <section className="flex flex-col gap-3" data-testid="automation-levels">
      <p className={ui.notice}>{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {notice ? <p className={ui.success}>{notice}</p> : null}
      {state === null && !error ? <p className="text-sm text-muted">{t("loading")}</p> : null}
      {state ? (
        <>
          <p className="text-sm" data-testid="automation-switches">
            <span className={state.auto_posting_enabled ? ui.badgeWarning : ui.badge}>{state.auto_posting_enabled ? t("runnerOn") : t("runnerOff")}</span>{" "}
            <span className={state.learning_enabled ? ui.badgeWarning : ui.badge}>{state.learning_enabled ? t("learningOn") : t("learningOff")}</span>{" "}
            <span className={state.auto_posting_outgoing_enabled ? ui.badgeWarning : ui.badge}>{state.auto_posting_outgoing_enabled ? t("outgoingOn") : t("outgoingOff")}</span>
          </p>
          <div className="overflow-x-auto">
            <table className="mhvp-table">
              <thead>
                <tr>
                  <th>{t("class")}</th>
                  <th>{t("level")}</th>
                  <th>{t("cap")}</th>
                  <th className="num">{t("nDecided")}</th>
                  <th className="num">{t("precision")}</th>
                  <th className="num">{t("nAuto")}</th>
                  <th className="num">{t("errorRate")}</th>
                  <th className="num">{t("coverage")}</th>
                  <th>{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {CLASSES.map((kind) => {
                  const level = state.levels[kind] ?? "L0";
                  const cap = state.caps[kind] ?? "L0";
                  const m = metric(kind);
                  const target = nextLevel(level, cap);
                  const blocked = state.blocked[kind] ?? 0;
                  return (
                    <tr key={kind} data-testid="level-row" className="align-top">
                      <td>
                        {state.labels[kind] ?? kind}
                        {blocked > 0 ? <span className={`ml-1 ${ui.badgeWarning}`}>{t("blocked", { count: blocked })}</span> : null}
                      </td>
                      <td>
                        <StatusPill label={level} variant={LEVEL_VARIANT[level] ?? "neutral"} />
                      </td>
                      <td>{cap}</td>
                      <td className="num">{m?.n_decided ?? 0}</td>
                      <td className="num">{formatRate(m?.precision_manual ?? null, none)}</td>
                      <td className="num">{m?.n_auto ?? 0}</td>
                      <td className="num">{formatRate(m?.error_rate_auto ?? null, none)}</td>
                      <td className="num">{formatRate(m?.coverage ?? null, none)}</td>
                      <td>
                        {canApprove ? (
                          <div className="flex flex-col gap-1">
                            {target ? (
                              <button type="button" className={ui.buttonSm} disabled={busy === kind} onClick={() => setRequesting(requesting === kind ? null : kind)}>
                                {t("request", { level: target })}
                              </button>
                            ) : null}
                            {level !== "L0" ? (
                              <button type="button" className={ui.buttonSm} disabled={busy === kind} onClick={() => lower(kind)}>
                                {t("lower")}
                              </button>
                            ) : null}
                            {requesting === kind && target ? (
                              <form
                                className="flex flex-col gap-1"
                                onSubmit={(e) => {
                                  e.preventDefault();
                                  request(kind);
                                }}
                                data-testid="level-request-form"
                              >
                                <label className="flex flex-col gap-1">
                                  <span className={ui.label}>{t("reason")}</span>
                                  <input className={ui.input} required minLength={3} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
                                </label>
                                <button type="submit" className={ui.primary} disabled={busy === kind || reason.trim().length < 3}>
                                  {t("submit")}
                                </button>
                              </form>
                            ) : null}
                          </div>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <h3 className={ui.h3}>{t("requests")}</h3>
          {state.requests.length === 0 ? <p className="text-sm text-muted">{t("noRequests")}</p> : null}
          {state.requests.length > 0 ? (
            <ul className="flex flex-col gap-2" data-testid="level-requests">
              {state.requests.map((req) => {
                const own = userId !== null && req.requested_by === userId;
                return (
                  <li key={req.id} className={`${ui.card} flex flex-col gap-1 text-sm`} data-testid="level-request">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{state.labels[req.case_kind] ?? req.case_kind}</span>
                      <span>
                        {req.level_from} → {req.level_to}
                      </span>
                      <StatusPill label={t(`status_${req.status}` as "status_requested")} variant={STATUS_VARIANT[req.status] ?? "neutral"} />
                      <span className="text-muted">{formatDate(req.created_at)}</span>
                    </div>
                    <p className="text-muted">{req.reason}</p>
                    {req.decision_comment ? <p className="text-muted">{req.decision_comment}</p> : null}
                    {req.status === "requested" && canApprove ? (
                      <div className={ui.formActions}>
                        <button type="button" className={ui.primary} disabled={own || busy === req.id} title={own ? t("fourEyes") : undefined} onClick={() => decide(req, "approve")}>
                          {t("approve")}
                        </button>
                        <button type="button" className={ui.secondary} disabled={busy === req.id} onClick={() => decide(req, "reject")}>
                          {t("reject")}
                        </button>
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          ) : null}
          <p className={ui.help}>{state.note}</p>
        </>
      ) : null}
    </section>
  );
}
