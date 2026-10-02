"use client";

import { useFormatter, useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import type { AssistantAnswer, AssistantHistoryRow, AssistantScopeView, AssistantStatus } from "@/components/portal/types";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const POLL_MS = 1500;
const POLL_MAX = 90;

/** Assistent für die eigenen Unterlagen (AE28, M7-06, SA-04): Fragen werden nur aus den
 *  Unterlagen beantwortet, die für diesen Zugang freigegeben sind. Ohne freigegebenen
 *  Datenschutzhinweis, ohne Kenntnisnahme oder ohne freigegebenen KI-Anbieter zeigt der Assistent
 *  nur Treffer aus den Unterlagen. KI-Antworten sind als solche gekennzeichnet und Information,
 *  keine Auskunft der Verwaltung. Die Rechte prüft allein die API. */
export function PortalAssistant() {
  const t = useTranslations("Assistant");
  const format = useFormatter();
  const [status, setStatus] = useState<AssistantStatus | null>(null);
  const [locked, setLocked] = useState(false);
  const [scope, setScope] = useState<AssistantScopeView | null>(null);
  const [history, setHistory] = useState<AssistantHistoryRow[]>([]);
  const [question, setQuestion] = useState("");
  const [unitId, setUnitId] = useState("");
  const [answer, setAnswer] = useState<AssistantAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const state = await bff<AssistantStatus>("/api/bff/portal/assistant/status");
    if (!state.ok) {
      if (state.status === 403) setLocked(true);
      else setError(state.message);
      return;
    }
    setStatus(state.data);
    const [scopeResult, historyResult] = await Promise.all([
      bff<AssistantScopeView>("/api/bff/portal/assistant/scope"),
      bff<AssistantHistoryRow[]>("/api/bff/portal/assistant/questions?limit=10"),
    ]);
    if (scopeResult.ok) setScope(scopeResult.data);
    if (historyResult.ok) setHistory(historyResult.data);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function acknowledge() {
    if (!status || status.privacy.version === null) return;
    setError(null);
    const result = await bff("/api/bff/portal/assistant/privacy-ack", {
      method: "POST",
      body: JSON.stringify({ text_version: status.privacy.version }),
    });
    if (!result.ok) {
      setError(result.message);
      return;
    }
    await load();
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (question.trim().length < 3) {
      setError(t("questionRequired"));
      return;
    }
    setBusy(true);
    const result = await bff<AssistantAnswer>("/api/bff/portal/assistant/questions/async", {
      method: "POST",
      body: JSON.stringify({ question: question.trim(), ...(unitId ? { unit_id: unitId } : {}) }),
    });
    if (!result.ok) {
      setBusy(false);
      setError(result.message);
      return;
    }
    let current = result.data;
    // GAE-29: the answer is produced by a job in the worker; poll the status (the API closes an
    // overdue job as timeout, the loop stops after a fixed number of polls as well).
    for (let i = 0; current.status === "pending" && i < POLL_MAX; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, POLL_MS));
      const next = await bff<AssistantAnswer>(`/api/bff/portal/assistant/questions/${current.id}`);
      if (!next.ok) {
        setBusy(false);
        setError(next.message);
        return;
      }
      current = next.data;
    }
    setBusy(false);
    if (current.status === "pending") {
      setError(t("stillPending"));
      return;
    }
    setAnswer(current);
    setQuestion("");
    await load();
  }

  if (locked) {
    return (
      <p role="status" className={ui.notice} data-testid="assistant-locked">
        {t("locked")}
      </p>
    );
  }
  if (!status) {
    return error ? (
      <p role="alert" className={ui.alert}>
        {error}
      </p>
    ) : (
      <p role="status" className="text-sm text-muted">
        {t("loading")}
      </p>
    );
  }

  const privacy = status.privacy;
  const needsAck = privacy.feature_enabled && privacy.notice_status === "released" && !privacy.acknowledged;
  const stamp = (value: string) =>
    format.dateTime(new Date(value), { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });

  return (
    <div className={ui.pageGap} data-testid="portal-assistant">
      <p className={ui.notice}>{status.notice}</p>
      <p className={ui.help} data-testid="assistant-scope">
        {status.scope.documents === 0 ? t("scopeEmpty") : t("scopeLine", { documents: status.scope.documents })}
      </p>

      {privacy.feature_enabled ? (
        <section className={`${ui.card} flex flex-col gap-2`} aria-labelledby="assistant-privacy">
          <h2 id="assistant-privacy" className={ui.h2}>
            {privacy.title ?? t("privacyTitle")}
          </h2>
          {privacy.notice_status === "released" ? (
            <>
              <p className="whitespace-pre-wrap break-words text-sm" data-testid="assistant-privacy-body">
                {privacy.body}
              </p>
              <p className={ui.help}>{t("privacyVersion", { version: privacy.version ?? 0 })}</p>
              {privacy.acknowledged ? (
                <p className="text-sm text-muted" data-testid="assistant-acknowledged">
                  {t("privacyAcknowledged")}
                </p>
              ) : (
                <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={() => void acknowledge()}>
                  {t("privacyAcknowledge")}
                </button>
              )}
            </>
          ) : (
            <p className="text-sm text-muted">{t("privacyNotReleased")}</p>
          )}
        </section>
      ) : null}

      {!status.ai.available ? (
        <p className={ui.help} data-testid="assistant-ai-blocked">
          {status.ai.blocked_message}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}

      <form onSubmit={onSubmit} noValidate aria-busy={busy} className={`${ui.card} flex flex-col gap-3`}>
        {scope && scope.units.length > 1 ? (
          <div className="flex flex-col gap-1">
            <label htmlFor="assistant-unit" className={ui.label}>
              {t("unitField")}
            </label>
            <select id="assistant-unit" className={ui.input} value={unitId} onChange={(e) => setUnitId(e.target.value)}>
              <option value="">{t("allUnits")}</option>
              {scope.units.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.label ?? t("unitNumber", { number: u.number })}
                </option>
              ))}
            </select>
          </div>
        ) : null}
        <label htmlFor="assistant-question" className={ui.label}>
          {t("questionField")}
        </label>
        <textarea
          id="assistant-question"
          rows={3}
          maxLength={2000}
          className={ui.input}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy || needsAck}>
          {busy ? t("asking") : t("ask")}
        </button>
        {needsAck ? <p className={ui.help}>{t("ackFirst")}</p> : null}
      </form>

      {answer ? (
        <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="assistant-answer" data-testid="assistant-answer">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="assistant-answer" className={ui.h2}>
              {t("answerTitle")}
            </h2>
            <span className={ui.badge}>{answer.mode === "ai" && answer.status === "answered" ? t("aiLabel") : t("searchLabel")}</span>
          </div>
          {answer.answer ? <p className="whitespace-pre-wrap break-words text-sm">{answer.answer}</p> : null}
          {answer.sources.length > 0 ? (
            <div>
              <p className={ui.label}>{t("sources")}</p>
              <ul className="flex flex-col gap-1 text-sm" data-testid="assistant-sources">
                {answer.sources.map((s) => (
                  <li key={s.document_id}>
                    <span className="font-medium">{s.title}</span>
                    {s.excerpt ? <span className="block text-xs text-muted">{s.excerpt}</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {answer.hits.length > 0 ? (
            <div>
              <p className={ui.label}>{t("hits")}</p>
              <ul className="flex flex-col gap-1 text-sm" data-testid="assistant-hits">
                {answer.hits.map((h) => (
                  <li key={h.document_id}>{h.title}</li>
                ))}
              </ul>
              <Link href="/dokumente" className="text-sm underline">
                {t("openDocuments")}
              </Link>
            </div>
          ) : answer.status === "search_hits" || answer.status === "failed" ? (
            <p className="text-sm text-muted">{t("noHits")}</p>
          ) : null}
          <p className={ui.help}>{answer.notice}</p>
          <p className={ui.help}>{answer.emergency_note}</p>
          <Link href="/meldungen" className="text-sm underline">
            {t("reportIssue")}
          </Link>
        </section>
      ) : null}

      <section className={`${ui.card} flex flex-col gap-2`} aria-labelledby="assistant-history">
        <h2 id="assistant-history" className={ui.h2}>
          {t("history")}
        </h2>
        {history.length === 0 ? (
          <p className="text-sm text-muted">{t("historyEmpty")}</p>
        ) : (
          <ul className="flex flex-col gap-2" data-testid="assistant-history">
            {history.map((row) => (
              <li key={row.id} className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm">
                <span className="block text-xs text-subtle">{stamp(row.created_at)}</span>
                <span className="block whitespace-pre-wrap break-words font-medium">{row.question}</span>
                {row.answer ? <span className="mt-1 block whitespace-pre-wrap break-words text-muted">{row.answer}</span> : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
