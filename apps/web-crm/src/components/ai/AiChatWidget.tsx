"use client";

import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import {
  contactsPreview,
  isRunPending,
  POLL_INTERVAL_MS,
  propertyPreview,
  type ContactChoice,
  type Conversation,
  type DocumentOut,
  type ImportRun,
  type Proposal,
  type Run,
} from "@/lib/ai";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { ContactProposal } from "./ContactProposal";
import { ImportResult } from "./ImportResult";
import { PropertyProposal } from "./PropertyProposal";

/** Where the user is; derived from the route so the assistant knows the page (M7, 10.1). */
type Area = "contacts" | "properties" | "hoa" | "letting" | "bank" | "invoices" | "tickets" | "other";
type PageContext = { area: Area; contextType: "global" | "property" | "contact"; contextId: string | null };

const UUID = /[0-9a-fA-F-]{36}/;

export function pageContext(pathname: string): PageContext {
  const id = pathname.match(UUID)?.[0] ?? null;
  if (pathname.startsWith("/kontakte")) return { area: "contacts", contextType: id ? "contact" : "global", contextId: id };
  if (pathname.startsWith("/objekte")) return { area: "properties", contextType: id ? "property" : "global", contextId: id };
  if (pathname.startsWith("/weg")) return { area: "hoa", contextType: id ? "property" : "global", contextId: id };
  if (pathname.startsWith("/vermietung")) return { area: "letting", contextType: "global", contextId: null };
  if (pathname.startsWith("/bank")) return { area: "bank", contextType: "global", contextId: null };
  if (pathname.startsWith("/rechnungen")) return { area: "invoices", contextType: "global", contextId: null };
  if (pathname.startsWith("/tickets")) return { area: "tickets", contextType: "global", contextId: null };
  return { area: "other", contextType: "global", contextId: null };
}

type Chip = { id: string; label: string };
type Entry =
  | { kind: "assistant"; text: string; chips?: Chip[] }
  | { kind: "user"; text: string }
  | { kind: "proposal"; proposal: Proposal }
  | { kind: "result"; importRun: ImportRun };

type Flow =
  | { step: "idle" }
  | { step: "ask_question" }
  | { step: "summarize" }
  | { step: "import_contacts"; role?: string }
  | { step: "import_property" }
  | { step: "confirm"; proposal: Proposal; documentIds: string[] }
  | { step: "reject_reason"; proposal: Proposal; documentIds: string[] };

/** Floating assistant available on every screen. Scripted steps with quick replies drive the
 *  import flow; the AI only extracts and answers, nothing is written before an explicit yes. */
export function AiChatWidget() {
  const t = useTranslations("AiChat");
  const pathname = usePathname();
  const ctx = pageContext(pathname);
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [flow, setFlow] = useState<Flow>({ step: "idle" });
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const greetedFor = useRef<string | null>(null);

  const say = (text: string, chips?: Chip[]) => setEntries((p) => [...p, { kind: "assistant", text, chips }]);
  const push = (e: Entry) => setEntries((p) => [...p, e]);

  const startChips = (area: Area): Chip[] => {
    const chips: Chip[] = [];
    if (area === "contacts" || area === "other") chips.push({ id: "import_contacts", label: t("chips.importContacts") });
    if (area === "properties" || area === "hoa") chips.push({ id: "import_property", label: t("chips.importProperty") });
    chips.push({ id: "ask", label: t("chips.ask") }, { id: "summarize", label: t("chips.summarize") });
    return chips;
  };

  // Greeting once per page area; the page is named so the user sees the context.
  useEffect(() => {
    if (!open || greetedFor.current === ctx.area) return;
    greetedFor.current = ctx.area;
    setFlow({ step: "idle" });
    say(t("greeting", { page: t(`area.${ctx.area}`) }), startChips(ctx.area));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, ctx.area]);

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "end" });
  }, [entries, busy]);

  const ensureConversation = async (): Promise<Conversation> => {
    if (conversation) return conversation;
    const res = await bff<Conversation>("/api/bff/ai/conversations", {
      method: "POST",
      body: JSON.stringify({ title: t("conversationTitle", { page: t(`area.${ctx.area}`) }), context_type: ctx.contextType, context_id: ctx.contextId }),
    });
    if (!res.ok) throw new Error(res.message);
    setConversation(res.data);
    return res.data;
  };

  const upload = async (list: File[]): Promise<string[]> => {
    const ids: string[] = [];
    for (const file of list) {
      const form = new FormData();
      form.set("file", file);
      form.set("title", file.name);
      const res = await bff<DocumentOut>("/api/bff/documents", { method: "POST", body: form });
      if (!res.ok) throw new Error(t("uploadFailed", { name: file.name }));
      ids.push(res.data.id);
    }
    return ids;
  };

  const waitForRun = async (run: Run): Promise<Run> => {
    let current = run;
    while (isRunPending(current)) {
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      const res = await bff<Run>(`/api/bff/ai/runs/${current.id}`);
      if (!res.ok) throw new Error(res.message);
      current = res.data;
    }
    return current;
  };

  const runTask = async (task: string, content: string, documentIds: string[]): Promise<Run> => {
    const conv = await ensureConversation();
    const res = await bff<Run>(`/api/bff/ai/conversations/${conv.id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, task, document_ids: documentIds }),
    });
    if (!res.ok) throw new Error(res.message);
    return waitForRun(res.data);
  };

  const proposalOf = async (run: Run): Promise<Proposal | null> => {
    if (!run.proposal_id) return null;
    const res = await bff<Proposal>(`/api/bff/ai/proposals/${run.proposal_id}`);
    return res.ok ? res.data : null;
  };

  const describeRun = (run: Run) => {
    if (run.status === "blocked") return t("blocked", { reason: run.error ?? "" });
    if (run.status !== "succeeded") return t("failed", { reason: run.error ?? "" });
    return null;
  };

  const summarizeProposal = (proposal: Proposal, documentIds: string[]) => {
    if (proposal.entity_type === "contacts") {
      const p = contactsPreview(proposal.proposed);
      const count = (s: string) => p.rows.filter((r) => r.status === s).length;
      const total = p.rows.length;
      const lines = [t("contactsRead", { total, fresh: count("new"), existing: count("existing"), incomplete: count("incomplete"), invalid: count("invalid") })];
      if (p.questions.length) lines.push(t("questions"), ...p.questions.map((q) => `• ${q}`));
      const importable = total - count("invalid");
      if (importable === 0) {
        say(lines.concat(t("nothingToImport")).join("\n"), [{ id: "restart", label: t("chips.restart") }]);
        setFlow({ step: "idle" });
        return;
      }
      lines.push(t("confirmContacts", { count: importable }));
      say(lines.join("\n"), [
        { id: "yes", label: t("chips.yes") },
        { id: "no", label: t("chips.no") },
        { id: "details", label: t("chips.details") },
      ]);
    } else {
      const p = propertyPreview(proposal.proposed);
      const lines = [t("propertyRead", { name: p.property.name ?? "", units: p.units.length, parties: p.parties.length })];
      if (p.questions?.length) lines.push(t("questions"), ...p.questions.map((q: string) => `• ${q}`));
      lines.push(t("confirmProperty"));
      say(lines.join("\n"), [
        { id: "yes", label: t("chips.yes") },
        { id: "no", label: t("chips.no") },
        { id: "details", label: t("chips.details") },
      ]);
    }
    setFlow({ step: "confirm", proposal, documentIds });
  };

  const applyAll = async (proposal: Proposal) => {
    let body: Record<string, unknown> = {};
    if (proposal.entity_type === "contacts") {
      const p = contactsPreview(proposal.proposed);
      const contacts: ContactChoice[] = p.rows.map((row) =>
        row.status === "invalid"
          ? { index: row.index, action: "skip" }
          : row.status === "existing" && row.duplicates[0]
            ? { index: row.index, action: "link", contact_id: row.duplicates[0].contact_id }
            : { index: row.index, action: "create" },
      );
      body = { contacts };
    }
    const res = await bff<ImportRun>(`/api/bff/ai/proposals/${proposal.id}/apply`, { method: "POST", body: JSON.stringify(body) });
    if (!res.ok) throw new Error(res.message);
    push({ kind: "result", importRun: res.data });
    say(t("imported"), [{ id: "restart", label: t("chips.restart") }]);
    setFlow({ step: "idle" });
  };

  const guarded = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const extract = (task: "extract_contacts" | "extract_property", content: string, list: File[]) =>
    guarded(async () => {
      const ids = await upload(list);
      say(t("working"));
      const run = await runTask(task, content, ids);
      const problem = describeRun(run);
      if (problem) {
        say(problem, [{ id: "restart", label: t("chips.restart") }]);
        setFlow({ step: "idle" });
        return;
      }
      const proposal = await proposalOf(run);
      if (!proposal) {
        say(t("noProposal"), [{ id: "restart", label: t("chips.restart") }]);
        setFlow({ step: "idle" });
        return;
      }
      summarizeProposal(proposal, ids);
    });

  const onChip = (chip: Chip) => {
    push({ kind: "user", text: chip.label });
    switch (chip.id) {
      case "restart":
        say(t("greeting", { page: t(`area.${ctx.area}`) }), startChips(ctx.area));
        setFlow({ step: "idle" });
        return;
      case "ask":
        setFlow({ step: "ask_question" });
        say(t("askPrompt"));
        return;
      case "summarize":
        setFlow({ step: "summarize" });
        say(t("summarizePrompt"));
        return;
      case "import_contacts":
        setFlow({ step: "import_contacts" });
        say(t("importContactsRole"), [
          { id: "role_owner", label: t("chips.owners") },
          { id: "role_tenant", label: t("chips.tenants") },
          { id: "role_mixed", label: t("chips.mixed") },
        ]);
        return;
      case "role_owner":
      case "role_tenant":
      case "role_mixed": {
        const role = chip.id === "role_owner" ? "owner" : chip.id === "role_tenant" ? "tenant" : "mixed";
        setFlow({ step: "import_contacts", role });
        say(t("importContactsUpload"));
        return;
      }
      case "import_property":
        setFlow({ step: "import_property" });
        say(t("importPropertyUpload"));
        return;
      case "yes":
        if (flow.step === "confirm") void guarded(() => applyAll(flow.proposal));
        return;
      case "no":
        if (flow.step === "confirm") {
          setFlow({ step: "reject_reason", proposal: flow.proposal, documentIds: flow.documentIds });
          say(t("whyNot"), [
            { id: "only_new", label: t("chips.onlyNew") },
            { id: "cancel", label: t("chips.cancel") },
          ]);
        }
        return;
      case "details":
        if (flow.step === "confirm") push({ kind: "proposal", proposal: flow.proposal });
        return;
      case "only_new":
        if (flow.step === "reject_reason") {
          const proposal = flow.proposal;
          void guarded(async () => {
            const p = contactsPreview(proposal.proposed);
            const contacts: ContactChoice[] = p.rows.map((row) => ({ index: row.index, action: row.status === "new" ? "create" : "skip" }));
            const res = await bff<ImportRun>(`/api/bff/ai/proposals/${proposal.id}/apply`, { method: "POST", body: JSON.stringify({ contacts }) });
            if (!res.ok) throw new Error(res.message);
            push({ kind: "result", importRun: res.data });
            say(t("imported"), [{ id: "restart", label: t("chips.restart") }]);
            setFlow({ step: "idle" });
          });
        }
        return;
      case "cancel":
        if (flow.step === "reject_reason") {
          const proposal = flow.proposal;
          void guarded(async () => {
            await bff(`/api/bff/ai/proposals/${proposal.id}/reject`, { method: "POST" });
            say(t("rejected"), [{ id: "restart", label: t("chips.restart") }]);
            setFlow({ step: "idle" });
          });
        }
        return;
      default:
        return;
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const content = text.trim();
    const list = files;
    if (!content && list.length === 0) return;
    push({ kind: "user", text: content || list.map((f) => f.name).join(", ") });
    setText("");
    setFiles([]);
    if (fileInput.current) fileInput.current.value = "";
    switch (flow.step) {
      case "import_contacts": {
        if (list.length === 0) return say(t("needFile"));
        const role = flow.role ?? "mixed";
        return extract("extract_contacts", [t(`roleText.${role}`), content].filter(Boolean).join(" "), list);
      }
      case "import_property":
        if (list.length === 0) return say(t("needFile"));
        return extract("extract_property", [t("propertyText"), content].filter(Boolean).join(" "), list);
      case "summarize":
        if (list.length === 0) return say(t("needFile"));
        return guarded(async () => {
          const ids = await upload(list);
          say(t("working"));
          const run = await runTask("summarize", content || t("summarizeText"), ids);
          const problem = describeRun(run);
          const out = run.output as { summary?: string; open_points?: string[] } | null;
          say(problem ?? [out?.summary ?? "", ...(out?.open_points ?? []).map((p) => `• ${p}`)].filter(Boolean).join("\n"), [{ id: "restart", label: t("chips.restart") }]);
          setFlow({ step: "idle" });
        });
      case "reject_reason":
        return guarded(async () => {
          // The reason becomes a new extraction with the same documents and the correction.
          const { documentIds } = flow;
          say(t("working"));
          const run = await runTask("extract_contacts", t("correctionText", { text: content }), documentIds);
          const problem = describeRun(run);
          const proposal = problem ? null : await proposalOf(run);
          if (!proposal) {
            say(problem ?? t("noProposal"), [{ id: "restart", label: t("chips.restart") }]);
            setFlow({ step: "idle" });
            return;
          }
          summarizeProposal(proposal, documentIds);
        });
      case "confirm":
        return say(t("pleaseChoose"), [
          { id: "yes", label: t("chips.yes") },
          { id: "no", label: t("chips.no") },
        ]);
      default:
        // Free question (with optional documents), on every page.
        return guarded(async () => {
          const ids = list.length ? await upload(list) : [];
          say(t("working"));
          const run = await runTask("answer_question", [t("pageHint", { page: t(`area.${ctx.area}`) }), content].join(" "), ids);
          const problem = describeRun(run);
          const out = run.output as { answer?: string; answerable?: boolean } | null;
          say(problem ?? (out?.answerable === false ? t("notAnswerable") : (out?.answer ?? "")), startChips(ctx.area));
          setFlow({ step: "idle" });
        });
    }
  };

  const needsFile = flow.step === "import_contacts" || flow.step === "import_property" || flow.step === "summarize";

  return (
    <>
      <button
        type="button"
        aria-label={open ? t("close") : t("open")}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="fixed bottom-5 right-5 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-accent text-accent-fg shadow-lg transition duration-200 hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-gold/60"
      >
        <span aria-hidden className="text-xl">
          {open ? "×" : "✦"}
        </span>
      </button>
      {open ? (
        <section
          aria-label={t("title")}
          className="fixed inset-0 z-40 flex flex-col overflow-hidden border-2 border-gold/70 bg-bg shadow-lg sm:inset-auto sm:bottom-20 sm:right-5 sm:h-[32rem] sm:w-[min(26rem,calc(100vw-2.5rem))] sm:rounded-2xl"
          style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
        >
          <header className="flex items-center justify-between border-b border-gold/40 bg-gold-tint px-4 py-3">
            <div>
              <p className="text-sm font-semibold">{t("title")}</p>
              <p className="mhvp-label">{t("onPage", { page: t(`area.${ctx.area}`) })}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-gold" aria-hidden />
              <button
                type="button"
                aria-label={t("close")}
                onClick={() => setOpen(false)}
                className="flex h-11 w-11 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-fg sm:hidden"
              >
                <span aria-hidden>×</span>
              </button>
            </div>
          </header>
          <ol className="flex flex-1 flex-col gap-2 overflow-y-auto px-3 py-3 text-sm" data-testid="ai-chat-log">
            {entries.map((e, i) => {
              if (e.kind === "user") {
                return (
                  <li key={i} className="max-w-[85%] self-end rounded-2xl rounded-br-md bg-accent px-3.5 py-2 text-accent-fg">
                    {e.text}
                  </li>
                );
              }
              if (e.kind === "proposal") {
                return (
                  <li key={i} className="rounded-lg border border-border p-2">
                    {e.proposal.entity_type === "contacts" ? <ContactProposal proposal={e.proposal} /> : <PropertyProposal proposal={e.proposal} />}
                  </li>
                );
              }
              if (e.kind === "result") {
                return (
                  <li key={i} className="rounded-lg border border-border p-2">
                    <ImportResult importRun={e.importRun} showItems={false} />
                  </li>
                );
              }
              const last = i === entries.length - 1;
              return (
                <li key={i} className="max-w-[92%] self-start rounded-2xl rounded-bl-md border border-gold/30 bg-gold-tint px-3.5 py-2">
                  <p className="whitespace-pre-wrap">{e.text}</p>
                  {last && e.chips?.length && !busy ? (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {e.chips.map((c) => (
                        <button
                          key={c.id}
                          type="button"
                          className="inline-flex items-center rounded-full border border-border bg-bg px-3 py-1 text-xs font-medium text-fg transition duration-150 hover:border-gold hover:bg-surface focus:outline-none focus:ring-2 focus:ring-gold/40"
                          onClick={() => onChip(c)}
                        >
                          {c.label}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </li>
              );
            })}
            {busy ? (
              <li className="w-full self-start" aria-live="polite">
                <div className="max-w-[92%] rounded-2xl rounded-bl-md bg-gold-tint px-3.5 py-2">
                  <p className="text-xs text-muted">{t("thinking")}</p>
                  <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-gold-soft" role="progressbar" aria-label={t("thinking")}>
                    <div className="mhvp-progress-slide h-full w-1/3 rounded-full bg-gold" />
                  </div>
                </div>
              </li>
            ) : null}
            {error ? (
              <li role="alert" className={ui.alert}>
                {error}
              </li>
            ) : null}
            <div ref={bottom} />
          </ol>
          <form onSubmit={submit} className="flex flex-col gap-2 border-t border-border-soft p-3">
            {files.length ? <p className="text-xs text-muted">{files.map((f) => f.name).join(", ")}</p> : null}
            <div className="flex items-end gap-2">
              <label className="inline-flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-full border border-border bg-bg text-fg transition duration-150 hover:border-gold hover:bg-surface" title={t("attach")}>
                <span aria-hidden>📎</span>
                <input ref={fileInput} type="file" multiple aria-label={t("attach")} className="sr-only" onChange={(e) => setFiles(Array.from(e.target.files ?? []).slice(0, 20))} />
              </label>
              <textarea
                aria-label={t("inputLabel")}
                className={`${ui.input} max-h-28 min-h-9 resize-none`}
                rows={1}
                value={text}
                placeholder={needsFile ? t("placeholderFile") : t("placeholder")}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void submit(e as unknown as React.FormEvent);
                  }
                }}
              />
              <button type="submit" className={ui.primary} disabled={busy || (!text.trim() && files.length === 0)}>
                {t("send")}
              </button>
            </div>
            <p className="text-[11px] text-subtle">{t("disclaimer")}</p>
          </form>
        </section>
      ) : null}
    </>
  );
}
