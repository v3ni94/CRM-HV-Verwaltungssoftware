"use client";

import { useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { CHAT_TASKS, type ChatTask, type Conversation, type DocumentOut, type Run } from "@/lib/ai";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

import { AssistantMessage } from "./AssistantMessage";
import { RunProgress, RunStatusView } from "./RunProgress";

const MAX_FILES = 20;

export function Assistant({ initialConversations }: { initialConversations: Conversation[] }) {
  const t = useTranslations("Ai");
  const [conversations, setConversations] = useState(initialConversations);
  const [current, setCurrent] = useState<Conversation | null>(null);
  const [task, setTask] = useState<ChatTask>("extract_contacts");
  const [content, setContent] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeRun, setActiveRun] = useState<Run | null>(null);
  const [finishedRun, setFinishedRun] = useState<Run | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const open = async (id: string) => {
    setError(null);
    setActiveRun(null);
    setFinishedRun(null);
    const res = await bff<Conversation>(`/api/bff/ai/conversations/${id}`);
    if (res.ok) setCurrent(res.data);
    else setError(res.message);
  };

  const create = async () => {
    setError(null);
    const res = await bff<Conversation>("/api/bff/ai/conversations", {
      method: "POST",
      body: JSON.stringify({ title: t("newTitle", { at: formatDateTime(new Date().toISOString()) }) }),
    });
    if (!res.ok) return setError(res.message);
    setConversations((prev) => [res.data, ...prev]);
    setCurrent(res.data);
    setActiveRun(null);
    setFinishedRun(null);
  };

  const upload = async (file: File): Promise<string> => {
    const form = new FormData();
    form.set("file", file);
    form.set("title", file.name);
    const res = await bff<DocumentOut>("/api/bff/documents", { method: "POST", body: form });
    if (!res.ok) throw new Error(t("uploadFailed", { name: file.name, reason: res.message }));
    return res.data.id;
  };

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!current || !content.trim()) return;
    setBusy(true);
    setError(null);
    setFinishedRun(null);
    let documentIds: string[];
    try {
      documentIds = [];
      for (const file of files) documentIds.push(await upload(file));
    } catch (err) {
      setBusy(false);
      return setError((err as Error).message);
    }
    const res = await bff<Run>(`/api/bff/ai/conversations/${current.id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content: content.trim(), task, document_ids: documentIds }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setContent("");
    setFiles([]);
    if (fileInput.current) fileInput.current.value = "";
    setActiveRun(res.data);
    await reload(current.id);
  };

  const reload = async (id: string) => {
    const res = await bff<Conversation>(`/api/bff/ai/conversations/${id}`);
    if (res.ok) setCurrent(res.data);
  };

  const onRunDone = async (run: Run) => {
    setActiveRun(null);
    setFinishedRun(run.status === "succeeded" ? null : run);
    if (current) await reload(current.id);
  };

  return (
    <div className="grid gap-4 md:grid-cols-[16rem_1fr]">
      <aside className="flex flex-col gap-2" aria-label={t("conversations")}>
        <button type="button" className={ui.primary} onClick={create}>
          {t("newConversation")}
        </button>
        {conversations.length === 0 ? <p className="text-sm text-muted">{t("noConversations")}</p> : null}
        <ul className="flex flex-col gap-1 text-sm">
          {conversations.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => open(c.id)}
                aria-current={current?.id === c.id ? "true" : undefined}
                className={`w-full rounded px-2 py-1 text-left hover:bg-surface ${current?.id === c.id ? "bg-surface font-medium" : ""}`}
              >
                <span className="block">{c.title}</span>
                <span className="block text-xs text-muted">{formatDateTime(c.created_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="flex min-w-0 flex-col gap-3" aria-label={t("chat")}>
        <p className="text-xs text-muted">{t("disclaimer")}</p>
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {!current ? (
          <p className="text-sm text-muted">{t("selectConversation")}</p>
        ) : (
          <>
            <h2 className="text-lg font-semibold">{current.title}</h2>
            {(current.messages ?? []).length === 0 ? <p className="text-sm text-muted">{t("noMessages")}</p> : null}
            <ol className="flex flex-col gap-2">
              {(current.messages ?? []).map((m) => (
                <AssistantMessage key={m.id} message={m} />
              ))}
            </ol>
            {activeRun ? <RunProgress key={activeRun.id} run={activeRun} onDone={onRunDone} /> : null}
            {finishedRun ? <RunStatusView run={finishedRun} /> : null}
            <form onSubmit={send} className={`${ui.card} flex flex-col gap-2`}>
              <div>
                <label htmlFor="ai-task" className={ui.label}>
                  {t("task")}
                </label>
                <select id="ai-task" className={ui.input} value={task} onChange={(e) => setTask(e.target.value as ChatTask)}>
                  {CHAT_TASKS.map((k) => (
                    <option key={k} value={k}>
                      {t(`tasks.${k}`)}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="ai-content" className={ui.label}>
                  {t("message")}
                </label>
                <textarea
                  id="ai-content"
                  className={ui.input}
                  rows={3}
                  maxLength={10000}
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder={t(`placeholder.${task}`)}
                />
              </div>
              <div>
                <label htmlFor="ai-files" className={ui.label}>
                  {t("files")}
                </label>
                <input
                  id="ai-files"
                  ref={fileInput}
                  type="file"
                  multiple
                  className="text-sm"
                  onChange={(e) => setFiles(Array.from(e.target.files ?? []).slice(0, MAX_FILES))}
                />
                {files.length > 0 ? <p className="text-xs text-muted">{files.map((f) => f.name).join(", ")}</p> : null}
                <p className="text-xs text-muted">{t("filesHint")}</p>
              </div>
              <div>
                <button type="submit" className={ui.primary} disabled={busy || !!activeRun || !content.trim()}>
                  {busy ? t("sending") : t("send")}
                </button>
              </div>
            </form>
          </>
        )}
      </section>
    </div>
  );
}
