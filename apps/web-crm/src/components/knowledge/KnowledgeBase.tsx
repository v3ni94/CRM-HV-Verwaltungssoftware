"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type PlaybookRow = {
  id: string;
  title: string;
  category: string | null;
  keywords: string[];
  steps: string[];
  status: string;
  usage_count: number;
  last_used_at?: string | null;
};

export type ExampleRow = {
  id: string;
  task: string;
  created_at: string;
  decision: string | null;
  text: string;
};

export type ExamplePage = { data: ExampleRow[]; meta: { page: number; per_page: number; total: number } };

const TASKS = [
  "ticket_resolution",
  "contact_master_data_change",
  "classify_document",
  "classify_email",
  "draft_reply",
  "propose_posting",
  "extract_invoice",
] as const;

/** Wissensdatenbank mit zwei Reitern: Playbooks (lesen, deaktivieren, Bearbeiten im
 *  Playbook-Editor unter /mail/playbooks) und Lernbeispiele mit Filter nach Aufgabe. */
export function KnowledgeBase({
  initialPlaybooks,
  initialExamples,
  canManage,
}: {
  initialPlaybooks: PlaybookRow[];
  initialExamples: ExamplePage;
  canManage: boolean;
}) {
  const t = useTranslations("Knowledge");
  const tr = useTranslations("Tickets");
  const [tab, setTab] = useState<"playbooks" | "examples">("playbooks");
  const [playbooks, setPlaybooks] = useState(initialPlaybooks);
  const [examples, setExamples] = useState(initialExamples);
  const [task, setTask] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const decisionLabel = (row: ExampleRow) => {
    if (!row.decision) return "";
    if (row.task === "ticket_resolution" && tr.has(`resolution.kinds.${row.decision}`)) return tr(`resolution.kinds.${row.decision}`);
    return row.decision;
  };
  const taskLabel = (value: string) => (t.has(`tasks.${value}`) ? t(`tasks.${value}`) : value);

  async function loadExamples(nextTask: string, page: number) {
    setBusy(true);
    setError(null);
    const params = new URLSearchParams({ page: String(page), per_page: "50" });
    if (nextTask) params.set("task", nextTask);
    const res = await bff<ExamplePage>(`/api/bff/ai/examples?${params.toString()}`);
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setExamples((prev) => (page > 1 ? { data: [...prev.data, ...res.data.data], meta: res.data.meta } : res.data));
  }

  async function deactivate(id: string) {
    setBusy(true);
    setError(null);
    const res = await bff<PlaybookRow>(`/api/bff/mail/playbooks/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "archived" }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setPlaybooks((prev) => prev.map((p) => (p.id === id ? { ...p, status: "archived" } : p)));
  }

  const hasMore = examples.data.length < examples.meta.total;

  return (
    <div className="flex flex-col gap-4">
      <div role="tablist" className="flex gap-2">
        {(["playbooks", "examples"] as const).map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            className={tab === key ? ui.primary : ui.secondary}
            onClick={() => setTab(key)}
          >
            {t(`tabs.${key}`)}
          </button>
        ))}
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {tab === "playbooks" ? (
        playbooks.length === 0 ? (
          <p className="text-sm text-muted">{t("playbooks.empty")}</p>
        ) : (
          <div className="overflow-x-auto" role="tabpanel">
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t("playbooks.title")}</th>
                  <th>{t("playbooks.trigger")}</th>
                  <th>{t("playbooks.steps")}</th>
                  <th>{t("playbooks.usage")}</th>
                  <th>{t("playbooks.lastUsed")}</th>
                  <th>{t("playbooks.status")}</th>
                  {canManage ? <th>{t("playbooks.actions")}</th> : null}
                </tr>
              </thead>
              <tbody>
                {playbooks.map((p) => (
                  <tr key={p.id} data-testid="playbook-row">
                    <td>{p.title}</td>
                    <td>{[p.category, ...p.keywords].filter(Boolean).join(", ")}</td>
                    <td>
                      <ol className="list-decimal pl-4 text-sm">
                        {p.steps.map((step, i) => (
                          <li key={i}>{step}</li>
                        ))}
                      </ol>
                    </td>
                    <td>{p.usage_count}</td>
                    <td>{p.last_used_at ? formatDateTime(p.last_used_at) : t("playbooks.never")}</td>
                    <td>
                      <StatusPill variant={p.status === "active" ? "success" : "neutral"} label={t(`playbooks.statuses.${p.status}`)} />
                    </td>
                    {canManage ? (
                      <td>
                        <div className="flex gap-2">
                          {p.status !== "archived" ? (
                            <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void deactivate(p.id)}>
                              {t("playbooks.deactivate")}
                            </button>
                          ) : null}
                          <Link href="/mail/playbooks" className={ui.buttonSm}>
                            {t("playbooks.edit")}
                          </Link>
                        </div>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : (
        <div className="flex flex-col gap-3" role="tabpanel">
          <label className="flex max-w-xs flex-col gap-1">
            <span className={ui.label}>{t("examples.filter")}</span>
            <select
              className={ui.input}
              value={task}
              disabled={busy}
              onChange={(e) => {
                setTask(e.target.value);
                void loadExamples(e.target.value, 1);
              }}
            >
              <option value="">{t("examples.all")}</option>
              {TASKS.map((value) => (
                <option key={value} value={value}>
                  {taskLabel(value)}
                </option>
              ))}
            </select>
          </label>
          <p className="text-xs text-muted">{t("examples.total", { total: examples.meta.total })}</p>
          {examples.data.length === 0 ? (
            <p className="text-sm text-muted">{t("examples.empty")}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className={ui.table}>
                <thead>
                  <tr>
                    <th>{t("examples.date")}</th>
                    <th>{t("examples.task")}</th>
                    <th>{t("examples.decision")}</th>
                    <th>{t("examples.text")}</th>
                  </tr>
                </thead>
                <tbody>
                  {examples.data.map((row) => (
                    <tr key={row.id} data-testid="example-row">
                      <td>{formatDate(row.created_at)}</td>
                      <td>{taskLabel(row.task)}</td>
                      <td>{decisionLabel(row)}</td>
                      <td>{row.text}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {hasMore ? (
            <button type="button" className={ui.secondary} disabled={busy} onClick={() => void loadExamples(task, examples.meta.page + 1)}>
              {t("examples.more")}
            </button>
          ) : null}
        </div>
      )}
    </div>
  );
}
