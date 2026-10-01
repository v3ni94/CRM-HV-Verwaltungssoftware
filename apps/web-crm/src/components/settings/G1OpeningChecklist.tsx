"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Shapes of GET /api/v1/accounting/g1-opening (M12-09). */
export type G1Item = {
  item_key: string;
  title: string;
  status: "open" | "passed" | "failed";
  confirmed_on: string | null;
  confirmed_by_name: string | null;
  note: string | null;
  responsible_user_id?: string | null;
  evidence_document_id?: string | null;
  evidence_ref?: string | null;
  evidence_missing?: boolean;
};

type G1Member = { user_id: string; display_name: string; email: string };

export type G1GateRequest = { id: string; status: string; scope: string; requested_by: string; four_eyes: boolean };

export type G1OpeningState = {
  chart: { released: boolean; code: string | null; version: number | null; released_at: string | null; status: string | null };
  cases: G1Item[];
  cases_total: number;
  cases_passed: number;
  manual: G1Item[];
  manual_total: number;
  manual_passed: number;
  automation_levels: Record<string, string>;
  learning_bookkeeper_enabled: boolean;
  gate_open: boolean;
  open_request: G1GateRequest | null;
  requests: G1GateRequest[];
  can_request: boolean;
  documents: Record<string, string>;
  items_without_responsible?: number;
  items_without_evidence?: number;
  gate_checklist_ref?: string;
};

const BASE = "/api/bff/accounting/g1-opening";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Checkliste zur Öffnung der Freigabestufe G1 (Einstellungen, Buchhaltung, G1 Öffnung):
 *  Stand aus dem System, Ergebnis je Prüfpunkt (Recht Buchhaltung freigeben) und der Antrag
 *  über den bestehenden Freigabepfad (Recht Freigabestufen beantragen); die Entscheidung
 *  trifft eine zweite Person auf der Plattformseite. */
export function G1OpeningChecklist({
  initial,
  canRecord,
  canRequest,
}: {
  initial: G1OpeningState | null;
  canRecord: boolean;
  canRequest: boolean;
}) {
  const t = useTranslations("G1Opening");
  const [state, setState] = useState<G1OpeningState | null>(initial);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<G1Item | null>(null);
  const [form, setForm] = useState({
    status: "passed",
    confirmed_on: today(),
    confirmed_by_name: "",
    note: "",
    responsible_user_id: "",
    evidence_document_id: "",
    evidence_ref: "",
  });
  const [members, setMembers] = useState<G1Member[]>([]);

  useEffect(() => {
    if (!canRecord) return;
    void bff<G1Member[]>("/api/bff/tenant/members").then((res) => {
      if (res.ok && Array.isArray(res.data)) setMembers(res.data);
    });
  }, [canRecord]);

  const memberName = (id: string | null | undefined) =>
    id ? (members.find((m) => m.user_id === id)?.display_name ?? id.slice(0, 8)) : "";
  const [scope, setScope] = useState("");
  const [comment, setComment] = useState("");

  async function reload() {
    const res = await bff<G1OpeningState>(BASE);
    if (res.ok) setState(res.data);
    else setError(res.message);
  }

  function openEditor(item: G1Item) {
    setEditing(item);
    setForm({
      status: item.status === "open" ? "passed" : item.status,
      confirmed_on: item.confirmed_on ?? today(),
      confirmed_by_name: item.confirmed_by_name ?? "",
      note: item.note ?? "",
      responsible_user_id: item.responsible_user_id ?? "",
      evidence_document_id: item.evidence_document_id ?? "",
      evidence_ref: item.evidence_ref ?? "",
    });
    setMessage(null);
    setError(null);
  }

  async function saveItem(event: React.FormEvent) {
    event.preventDefault();
    if (!editing) return;
    setBusy(true);
    const refs = {
      responsible_user_id: form.responsible_user_id || null,
      evidence_document_id: form.evidence_document_id.trim() || null,
      evidence_ref: form.evidence_ref.trim() || null,
    };
    const body =
      form.status === "open"
        ? { status: "open", ...refs }
        : {
            status: form.status,
            confirmed_on: form.confirmed_on,
            confirmed_by_name: form.confirmed_by_name.trim(),
            note: form.note.trim() || null,
            ...refs,
          };
    const res = await bff<G1Item>(`${BASE}/items/${editing.item_key}`, { method: "PUT", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setEditing(null);
    setMessage(t("savedMessage"));
    await reload();
  }

  async function fileRequest(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<G1GateRequest>(`${BASE}/request`, {
      method: "POST",
      body: JSON.stringify({ scope: scope.trim(), comment: comment.trim() || null }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setScope("");
    setComment("");
    setMessage(t("requestedMessage"));
    await reload();
  }

  if (!state) {
    return (
      <p role="alert" className={ui.alert}>
        {error ?? t("loadError")}
      </p>
    );
  }

  const chartText = state.chart.released
    ? t("chart.released", { code: state.chart.code ?? "", version: state.chart.version ?? 0, date: formatDate(state.chart.released_at) })
    : state.chart.status
      ? t("chart.notReleased", { status: t(`chart.status.${state.chart.status}`) })
      : t("chart.missing");
  const levels = Object.entries(state.automation_levels);
  const levelsAboveL1 = levels.filter(([, level]) => level !== "L0" && level !== "L1").length;

  const statusBadge = (item: G1Item) => {
    const cls = item.status === "passed" ? ui.badgeSuccess : item.status === "failed" ? ui.badgeDanger : ui.badge;
    return <span className={cls}>{t(`itemStatus.${item.status}`)}</span>;
  };

  const renderItems = (items: G1Item[], testId: string) => (
    <div className={ui.tableScroll}>
      <table className={ui.table} data-testid={testId}>
        <thead>
          <tr>
            <th>{t("columns.key")}</th>
            <th>{t("columns.title")}</th>
            <th>{t("columns.status")}</th>
            <th>{t("columns.date")}</th>
            <th>{t("columns.name")}</th>
            <th>{t("columns.responsible")}</th>
            <th>{t("columns.evidence")}</th>
            {canRecord ? <th /> : null}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.item_key}>
              <td className={ui.mono}>{item.item_key}</td>
              <td>
                {item.title}
                {item.note ? <span className={`block ${ui.help}`}>{item.note}</span> : null}
              </td>
              <td>{statusBadge(item)}</td>
              <td>{formatDate(item.confirmed_on)}</td>
              <td>{item.confirmed_by_name ?? ""}</td>
              <td>{memberName(item.responsible_user_id)}</td>
              <td>
                {item.evidence_document_id ? (
                  <a className="underline" href={`/dokumente/${item.evidence_document_id}`}>
                    {t("evidence.document")}
                  </a>
                ) : item.evidence_ref ? (
                  <span className={ui.mono}>{item.evidence_ref}</span>
                ) : null}
                {item.evidence_missing ? <span className={ui.badgeWarning}>{t("evidence.missing")}</span> : null}
              </td>
              {canRecord ? (
                <td>
                  <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => openEditor(item)}>
                    {t("record")}
                  </button>
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="flex flex-col gap-4">
      <p className={ui.notice}>{t("intro")}</p>
      {message ? <p className={ui.success}>{message}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}

      <section className={ui.card} aria-labelledby="g1-status-title">
        <h2 id="g1-status-title" className={ui.h2}>
          {t("status.title")}
        </h2>
        <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className={ui.label}>{t("status.chart")}</dt>
            <dd data-testid="g1-chart">
              <span className={state.chart.released ? ui.badgeSuccess : ui.badgeWarning}>{chartText}</span>
            </dd>
          </div>
          <div>
            <dt className={ui.label}>{t("status.cases")}</dt>
            <dd data-testid="g1-cases">
              <span className={state.cases_passed === state.cases_total ? ui.badgeSuccess : ui.badgeWarning}>
                {t("status.countOf", { passed: state.cases_passed, total: state.cases_total })}
              </span>
            </dd>
          </div>
          <div>
            <dt className={ui.label}>{t("status.manual")}</dt>
            <dd data-testid="g1-manual">
              <span className={state.manual_passed === state.manual_total ? ui.badgeSuccess : ui.badgeWarning}>
                {t("status.countOf", { passed: state.manual_passed, total: state.manual_total })}
              </span>
            </dd>
          </div>
          <div>
            <dt className={ui.label}>{t("status.levels")}</dt>
            <dd data-testid="g1-levels">
              <span className={levelsAboveL1 === 0 ? ui.badgeSuccess : ui.badgeWarning}>
                {levels.map(([kind, level]) => `${kind} ${level}`).join(", ")}
              </span>
              <span className={`block ${ui.help}`}>
                {state.learning_bookkeeper_enabled ? t("status.learningOn") : t("status.learningOff")}
              </span>
            </dd>
          </div>
          <div>
            <dt className={ui.label}>{t("status.gate")}</dt>
            <dd data-testid="g1-gate">
              <span className={state.gate_open ? ui.badgeSuccess : ui.badge}>
                {state.gate_open ? t("status.gateOpen") : state.open_request ? t("status.gateRequested") : t("status.gateClosed")}
              </span>
            </dd>
          </div>
        </dl>
      </section>

      <section className={ui.card} aria-labelledby="g1-docs-title">
        <h2 id="g1-docs-title" className={ui.h2}>
          {t("documents.title")}
        </h2>
        <p className={ui.help}>{t("documents.help")}</p>
        {state.gate_checklist_ref ? (
          <p className={ui.help} data-testid="g1-gate-checklist">
            {t("documents.gateChecklist")}: <span className={ui.mono}>{state.gate_checklist_ref}</span>
          </p>
        ) : null}
        {state.items_without_responsible !== undefined ? (
          <p className={ui.help} data-testid="g1-gaps">
            {t("documents.gaps", {
              responsible: state.items_without_responsible,
              evidence: state.items_without_evidence ?? 0,
            })}
          </p>
        ) : null}
        <ul className="mt-2 list-disc pl-5 text-sm">
          {Object.entries(state.documents).map(([key, path]) => (
            <li key={key}>
              {t.has(`documents.${key}`) ? t(`documents.${key}`) : key}: <span className={ui.mono}>{path}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className={ui.card} aria-labelledby="g1-cases-title">
        <h2 id="g1-cases-title" className={ui.h2}>
          {t("cases.title")}
        </h2>
        <p className={ui.help}>{t("cases.help")}</p>
        {renderItems(state.cases, "g1-cases-table")}
      </section>

      <section className={ui.card} aria-labelledby="g1-manual-title">
        <h2 id="g1-manual-title" className={ui.h2}>
          {t("manual.title")}
        </h2>
        <p className={ui.help}>{t("manual.help")}</p>
        {renderItems(state.manual, "g1-manual-table")}
      </section>

      {editing ? (
        <form onSubmit={saveItem} className={ui.card} aria-labelledby="g1-record-title">
          <h2 id="g1-record-title" className={ui.h2}>
            {t("form.title", { key: editing.item_key })}
          </h2>
          <p className={ui.help}>{editing.title}</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("form.status")}</span>
              <select className={ui.input} value={form.status} onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}>
                <option value="passed">{t("itemStatus.passed")}</option>
                <option value="failed">{t("itemStatus.failed")}</option>
                <option value="open">{t("itemStatus.open")}</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("form.date")}</span>
              <input
                type="date"
                className={ui.input}
                value={form.confirmed_on}
                disabled={form.status === "open"}
                onChange={(e) => setForm((f) => ({ ...f, confirmed_on: e.target.value }))}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("form.name")}</span>
              <input
                className={ui.input}
                value={form.confirmed_by_name}
                disabled={form.status === "open"}
                required={form.status !== "open"}
                onChange={(e) => setForm((f) => ({ ...f, confirmed_by_name: e.target.value }))}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("form.responsible")}</span>
              <select
                className={ui.input}
                value={form.responsible_user_id}
                onChange={(e) => setForm((f) => ({ ...f, responsible_user_id: e.target.value }))}
              >
                <option value="">{t("form.noResponsible")}</option>
                {members.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("form.evidenceDocument")}</span>
              <input
                className={ui.input}
                value={form.evidence_document_id}
                onChange={(e) => setForm((f) => ({ ...f, evidence_document_id: e.target.value }))}
              />
            </label>
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className={ui.label}>{t("form.evidenceRef")}</span>
              <input
                className={ui.input}
                maxLength={500}
                value={form.evidence_ref}
                onChange={(e) => setForm((f) => ({ ...f, evidence_ref: e.target.value }))}
              />
            </label>
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className={ui.label}>{t("form.note")}</span>
              <textarea className={ui.input} rows={2} value={form.note} onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))} />
            </label>
          </div>
          <div className={`mt-3 ${ui.formActions}`}>
            <button type="submit" className={ui.primary} disabled={busy}>
              {t("form.save")}
            </button>
            <button type="button" className={ui.secondary} disabled={busy} onClick={() => setEditing(null)}>
              {t("form.cancel")}
            </button>
          </div>
        </form>
      ) : null}

      <section className={ui.card} aria-labelledby="g1-request-title">
        <h2 id="g1-request-title" className={ui.h2}>
          {t("request.title")}
        </h2>
        <p className={ui.help}>{t("request.help")}</p>
        {state.open_request ? (
          <p className={ui.notice} data-testid="g1-open-request">
            {t("request.pending", { scope: state.open_request.scope })}
          </p>
        ) : null}
        {canRequest && state.can_request ? (
          <form onSubmit={fileRequest} className="mt-3 flex flex-col gap-3">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("request.scope")}</span>
              <textarea className={ui.input} rows={2} required minLength={10} value={scope} onChange={(e) => setScope(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("request.comment")}</span>
              <input className={ui.input} value={comment} onChange={(e) => setComment(e.target.value)} />
            </label>
            <div className={ui.formActions}>
              <button type="submit" className={ui.primary} disabled={busy || scope.trim().length < 10}>
                {t("request.submit")}
              </button>
            </div>
          </form>
        ) : (
          <p className={ui.help}>{state.gate_open ? t("request.alreadyOpen") : canRequest ? t("request.blocked") : t("request.noRight")}</p>
        )}
        {state.requests.length > 0 ? (
          <ul className="mt-3 text-sm" data-testid="g1-requests">
            {state.requests.map((r) => (
              <li key={r.id}>
                {t(`requestStatus.${r.status}`)}: {r.scope}
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </div>
  );
}
