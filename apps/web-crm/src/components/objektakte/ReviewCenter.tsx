"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type CategoryOption = { id: string; code: string; name: string };

type Candidate = {
  rule_id?: string;
  category_id: string | null;
  document_type: string | null;
  score?: number;
  confidence?: number;
};

export type ReviewCase = {
  id: string;
  document_id: string | null;
  document_title: string | null;
  document_preview_url: string | null;
  stage: string;
  candidates: { candidates?: Candidate[]; ai?: Candidate } | null;
  proposed_action: Record<string, unknown> | null;
  priority: number;
  status: "open" | "in_progress" | "resolved" | "dismissed";
  snoozed_until: string | null;
  created_at: string;
  updated_at: string;
};

const STATUSES = ["open", "in_progress", "resolved", "dismissed"] as const;

/** M35 Stufe 3 part 5: Review-Center-Oberfläche (Liste mit Filtern, Sammelentscheidung,
 * Falldetails mit Kandidaten, "KI fragen" und Dokumentlink). Spiegelt die Backend-Endpunkte
 * unter `/api/v1/objektakte/review` (part 3) und `ask-ai` (part 2). */
export function ReviewCenter({ categories }: { categories: CategoryOption[] }) {
  const t = useTranslations("Objektakte");
  const [status, setStatus] = useState<string>("open");
  const [priorityMin, setPriorityMin] = useState<string>("");
  const [stage, setStage] = useState<string>("");
  const [cases, setCases] = useState<ReviewCase[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [openCaseId, setOpenCaseId] = useState<string | null>(null);
  const [bulkCategory, setBulkCategory] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = async () => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (priorityMin) params.set("priority_min", priorityMin);
    if (stage) params.set("stage", stage);
    const res = await bff<{ items: ReviewCase[] }>(`/api/bff/objektakte/review?${params.toString()}`);
    if (res.ok) setCases(res.data.items);
    else setError(res.message);
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, priorityMin, stage]);

  const toggleSelected = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const bulkDecide = async () => {
    if (selected.size === 0 || !bulkCategory) return;
    setBusy(true);
    setError(null);
    const res = await bff<{ decided: string[]; skipped: unknown[] }>(
      "/api/bff/objektakte/review/bulk-decide",
      {
        method: "POST",
        body: JSON.stringify({ case_ids: Array.from(selected), category_id: bulkCategory }),
      },
    );
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setSelected(new Set());
    await reload();
  };

  const decide = async (
    caseId: string,
    body: Record<string, unknown>,
  ): Promise<void> => {
    setBusy(true);
    setError(null);
    const res = await bff<{ case: ReviewCase }>(`/api/bff/objektakte/review/${caseId}/decide`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    await reload();
  };

  const askAi = async (caseId: string) => {
    setBusy(true);
    setError(null);
    const res = await bff<{ run_status: string; run_error: string | null; case: ReviewCase }>(
      `/api/bff/objektakte/review/${caseId}/ask-ai`,
      { method: "POST" },
    );
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    await reload();
  };

  const categoryName = (id: string | null) => categories.find((c) => c.id === id)?.name ?? id ?? "–";

  return (
    <div className="flex flex-col gap-4">
      <section className={`${ui.card} flex flex-wrap items-end gap-3`}>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("review.filterStatus")}</span>
          <select className={ui.input} value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">{t("review.statusAll")}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`review.status.${s}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("review.filterPriority")}</span>
          <input
            type="number"
            className={ui.input}
            value={priorityMin}
            onChange={(e) => setPriorityMin(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("review.filterStage")}</span>
          <input className={ui.input} value={stage} onChange={(e) => setStage(e.target.value)} />
        </label>
        <label className="flex flex-1 flex-col gap-1">
          <span className={ui.label}>{t("review.bulkCategory")}</span>
          <select className={ui.input} value={bulkCategory} onChange={(e) => setBulkCategory(e.target.value)}>
            <option value="">{t("rules.noCategory")}</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className={ui.primary}
          disabled={busy || selected.size === 0 || !bulkCategory}
          onClick={() => void bulkDecide()}
        >
          {t("review.bulkDecide")} ({selected.size})
        </button>
      </section>

      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}

      <ul className="flex flex-col gap-2">
        {cases.length === 0 ? <li className="text-xs text-muted">{t("review.empty")}</li> : null}
        {cases.map((c) => (
          <li key={c.id} className="rounded-md border border-border p-3">
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="checkbox"
                aria-label={t("review.select")}
                checked={selected.has(c.id)}
                onChange={() => toggleSelected(c.id)}
              />
              <span className="text-sm font-medium">{c.document_title ?? t("review.noDocument")}</span>
              <span className="text-xs text-muted">
                {t(`review.status.${c.status}`)} · {t("review.priorityLabel")} {c.priority} · {c.stage}
              </span>
              <button
                type="button"
                className={ui.buttonSm}
                onClick={() => setOpenCaseId(openCaseId === c.id ? null : c.id)}
              >
                {t("review.details")}
              </button>
            </div>
            {openCaseId === c.id ? (
              <div className="mt-3 flex flex-col gap-2 border-t border-border pt-3">
                {c.document_preview_url ? (
                  <a
                    href={c.document_preview_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm underline"
                  >
                    {t("review.openDocument")}
                  </a>
                ) : null}
                <div className="flex flex-col gap-1">
                  <span className={ui.label}>{t("review.candidates")}</span>
                  {(c.candidates?.candidates ?? []).length === 0 && !c.candidates?.ai ? (
                    <span className="text-xs text-muted">{t("review.noCandidates")}</span>
                  ) : null}
                  {(c.candidates?.candidates ?? []).map((cand, i) => (
                    <div key={i} className="flex flex-wrap items-center gap-2 text-sm">
                      <span>
                        {categoryName(cand.category_id)}
                        {cand.document_type ? ` · ${cand.document_type}` : ""}
                        {typeof cand.score === "number" ? ` · ${Math.round(cand.score * 100)}%` : ""}
                      </span>
                      <button
                        type="button"
                        className={ui.buttonSm}
                        disabled={busy}
                        onClick={() => void decide(c.id, { action: "accept_candidate", candidate_index: i })}
                      >
                        {t("review.acceptCandidate")}
                      </button>
                    </div>
                  ))}
                  {c.candidates?.ai ? (
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span>
                        {t("review.aiSuggestion")}: {categoryName(c.candidates.ai.category_id)}
                        {typeof c.candidates.ai.confidence === "number"
                          ? ` · ${Math.round(c.candidates.ai.confidence * 100)}%`
                          : ""}
                      </span>
                    </div>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void askAi(c.id)}>
                    {t("review.askAi")}
                  </button>
                  <button
                    type="button"
                    className={ui.buttonSm}
                    disabled={busy}
                    onClick={() => void decide(c.id, { action: "reject" })}
                  >
                    {t("review.reject")}
                  </button>
                  <button
                    type="button"
                    className={ui.buttonSm}
                    disabled={busy}
                    onClick={() =>
                      void decide(c.id, {
                        action: "snooze",
                        snoozed_until: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
                      })
                    }
                  >
                    {t("review.snooze")}
                  </button>
                </div>
                <ManualDecision
                  categories={categories}
                  busy={busy}
                  onDecide={(categoryId) => void decide(c.id, { action: "set_manually", category_id: categoryId })}
                />
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ManualDecision({
  categories,
  busy,
  onDecide,
}: {
  categories: CategoryOption[];
  busy: boolean;
  onDecide: (categoryId: string) => void;
}) {
  const t = useTranslations("Objektakte");
  const [categoryId, setCategoryId] = useState("");
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("review.manualCategory")}</span>
        <select className={ui.input} value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">{t("rules.noCategory")}</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className={ui.buttonSm}
        disabled={busy || !categoryId}
        onClick={() => onDecide(categoryId)}
      >
        {t("review.setManually")}
      </button>
    </div>
  );
}
