"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Connection = {
  id: string;
  connector: string;
  bank_name: string;
  bic: string | null;
  consent_valid_until: string | null;
  status: string;
  error_message: string | null;
  has_credentials: boolean;
};
type SyncRun = { id: string; source: string; status: string; counts: Record<string, unknown>; errors: unknown[] };
type Decision = {
  id: string;
  round: number;
  status: string;
  level: string;
  case_kind: string;
  best_source: string | null;
  best_confidence: string | null;
  decided_at: string | null;
  reason: string | null;
};
type Learning = { enabled: boolean; engine_version: string; rule_version: string; note: string };

const CONNECTORS = ["file_import", "fints", "ebics", "aggregator_finapi", "aggregator_gocardless"] as const;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** AF03 (GAF-03): Bankverbindungen (Liste, Anlage ohne Zugangsdaten), Sync-Protokoll,
 *  Schalter des Entscheidungsprotokolls (ADR 0014) und Protokoll je Umsatz. Das Anlegen einer
 *  Verbindung ruft nichts bei der Bank ab; der Schalter bucht nichts. Zahlungen: G2. */
export function BankConnectionsPanel({ canApprove }: { canApprove: boolean }) {
  const t = useTranslations("BankConnections");
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [runs, setRuns] = useState<SyncRun[] | null>(null);
  const [learning, setLearning] = useState<Learning | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState({ bank_name: "", bic: "", connector: "file_import" });
  const [reason, setReason] = useState("");
  const [txId, setTxId] = useState("");
  const [decisions, setDecisions] = useState<Decision[] | null>(null);

  const load = useCallback(async () => {
    const [c, r, l] = await Promise.all([
      bff<Connection[]>("/api/bff/banking/connections"),
      bff<SyncRun[]>("/api/bff/banking/runs"),
      bff<Learning>("/api/bff/banking/learning"),
    ]);
    if (c.ok) setConnections(c.data);
    else setError(c.message);
    if (r.ok) setRuns(r.data);
    if (l.ok) setLearning(l.data);
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const res = await bff("/api/bff/banking/connections", {
      method: "POST",
      body: JSON.stringify({
        bank_name: form.bank_name.trim(),
        connector: form.connector,
        bic: form.bic.trim() || null,
      }),
    });
    if (!res.ok) return setError(res.message);
    setMessage(t("created"));
    setForm({ bank_name: "", bic: "", connector: "file_import" });
    void load();
  };
  const switchLearning = async () => {
    if (!learning || !reason.trim()) return;
    setError(null);
    const res = await bff("/api/bff/banking/learning", {
      method: "PUT",
      body: JSON.stringify({ enabled: !learning.enabled, reason: reason.trim() }),
    });
    if (!res.ok) return setError(res.message);
    setReason("");
    setMessage(t("switched"));
    void load();
  };
  const lookup = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setDecisions(null);
    const res = await bff<Decision[]>(`/api/bff/banking/transactions/${txId.trim()}/decisions`);
    if (res.ok) setDecisions(res.data);
    else setError(res.message);
  };

  return (
    <div className="flex flex-col gap-6">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className={ui.notice}>
          {message}
        </p>
      ) : null}

      <section aria-labelledby="bc-connections" className="flex flex-col gap-2">
        <h2 id="bc-connections" className="text-base font-semibold">
          {t("connections")}
        </h2>
        {connections && connections.length === 0 ? <p className="text-sm text-muted">{t("noConnections")}</p> : null}
        {connections && connections.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="mhvp-table">
              <thead>
                <tr>
                  <th>{t("bank")}</th>
                  <th>{t("connector")}</th>
                  <th>{t("statusLabel")}</th>
                  <th>{t("consentUntil")}</th>
                </tr>
              </thead>
              <tbody>
                {connections.map((c) => (
                  <tr key={c.id}>
                    <td>
                      {c.bank_name}
                      {c.bic ? <span className="text-subtle"> ({c.bic})</span> : null}
                    </td>
                    <td>{t(`connectorName.${c.connector}` as never)}</td>
                    <td>
                      {c.status}
                      {c.error_message ? <span className="block text-xs text-danger-fg">{c.error_message}</span> : null}
                    </td>
                    <td>{c.consent_valid_until ? formatDate(c.consent_valid_until) : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        {canApprove ? (
          <form onSubmit={create} className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="flex-1">
              <span className={ui.label}>{t("bank")}</span>
              <input
                className={ui.input}
                required
                value={form.bank_name}
                onChange={(e) => setForm({ ...form, bank_name: e.target.value })}
              />
            </label>
            <label>
              <span className={ui.label}>{t("bic")}</span>
              <input
                className={ui.input}
                maxLength={11}
                value={form.bic}
                onChange={(e) => setForm({ ...form, bic: e.target.value })}
              />
            </label>
            <label>
              <span className={ui.label}>{t("connector")}</span>
              <select
                className={ui.input}
                value={form.connector}
                onChange={(e) => setForm({ ...form, connector: e.target.value })}
              >
                {CONNECTORS.map((c) => (
                  <option key={c} value={c}>
                    {t(`connectorName.${c}` as never)}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit" className={ui.primary}>
              {t("create")}
            </button>
          </form>
        ) : null}
        <p className={ui.help}>{t("createHint")}</p>
      </section>

      <section aria-labelledby="bc-runs" className="flex flex-col gap-2">
        <h2 id="bc-runs" className="text-base font-semibold">
          {t("runs")}
        </h2>
        {runs && runs.length === 0 ? <p className="text-sm text-muted">{t("noRuns")}</p> : null}
        {runs && runs.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="mhvp-table">
              <thead>
                <tr>
                  <th>{t("source")}</th>
                  <th>{t("statusLabel")}</th>
                  <th className="num">{t("errors")}</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td>{r.source}</td>
                    <td>{r.status}</td>
                    <td className="num">{r.errors.length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section aria-labelledby="bc-learning" className="flex flex-col gap-2">
        <h2 id="bc-learning" className="text-base font-semibold">
          {t("learning")}
        </h2>
        <p className={ui.notice}>{t("learningNotice")}</p>
        {learning ? (
          <>
            <p className="text-sm">
              {learning.enabled ? t("learningOn") : t("learningOff")} ({learning.engine_version})
            </p>
            {canApprove ? (
              <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                <label className="flex-1">
                  <span className={ui.label}>{t("reason")}</span>
                  <input className={ui.input} value={reason} onChange={(e) => setReason(e.target.value)} />
                </label>
                <button type="button" className={ui.button} disabled={!reason.trim()} onClick={switchLearning}>
                  {learning.enabled ? t("switchOff") : t("switchOn")}
                </button>
              </div>
            ) : null}
          </>
        ) : null}
      </section>

      <section aria-labelledby="bc-decisions" className="flex flex-col gap-2">
        <h2 id="bc-decisions" className="text-base font-semibold">
          {t("decisions")}
        </h2>
        <form onSubmit={lookup} className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="flex-1">
            <span className={ui.label}>{t("transactionId")}</span>
            <input className={ui.input} value={txId} onChange={(e) => setTxId(e.target.value)} />
          </label>
          <button type="submit" className={ui.button} disabled={!UUID.test(txId.trim())}>
            {t("lookup")}
          </button>
        </form>
        {decisions && decisions.length === 0 ? <p className="text-sm text-muted">{t("noDecisions")}</p> : null}
        {decisions && decisions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="mhvp-table">
              <thead>
                <tr>
                  <th className="num">{t("round")}</th>
                  <th>{t("statusLabel")}</th>
                  <th>{t("level")}</th>
                  <th>{t("bestSource")}</th>
                  <th>{t("decidedAt")}</th>
                  <th>{t("reason")}</th>
                </tr>
              </thead>
              <tbody>
                {decisions.map((d) => (
                  <tr key={d.id}>
                    <td className="num">{d.round}</td>
                    <td>{d.status}</td>
                    <td>{d.level}</td>
                    <td>
                      {d.best_source ?? "-"}
                      {d.best_confidence ? ` (${d.best_confidence})` : ""}
                    </td>
                    <td>{d.decided_at ? formatDate(d.decided_at) : "-"}</td>
                    <td>{d.reason ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}
