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
  type ChatLink,
  type ImportRun,
  type Message,
  type Proposal,
  type Run,
  type AiToolUse,
  toolsUsedOf,
} from "@/lib/ai";
import { bff } from "@/lib/bff";
import { mergeChatContext, readChatContextAttribute, useChatContextOverride } from "@/lib/chat-context";
import { chatPageContext, suggestionsFor, type ChatArea, type ChatPageContext } from "@/lib/chat-suggestions";
import { ui } from "@/lib/ui";

import { ASSISTANT_OPEN_EVENT } from "./AssistantTab";
import { ChatActionProposal } from "./ChatActionProposal";
import { ChatLinks } from "./ChatLinks";
import { ChatTools } from "./ChatTools";
import { ContactProposal } from "./ContactProposal";
import { ImportResult } from "./ImportResult";
import { PropertyProposal } from "./PropertyProposal";

/** Where the user is; derived from the route so the assistant knows the page and the record
 *  open on it (M7, 10.1, rule AI-LOOKUP-01). */
type Area = ChatArea;
type PageContext = ChatPageContext;
/** Polling stops after this; a run that stays queued or running longer is reported as unresponsive. */
export const RUN_TIMEOUT_MS = 10 * 60 * 1000;

/** Error text with the failing step and HTTP status so a report can be diagnosed. */
function stepError(step: string, status: number, message: string): string {
  return `${step} (HTTP ${status}): ${message}`;
}

const EMAIL = /[\w.+-]+@[\w-]+\.[\w.-]+/;
const PHONE = /(?:\+\d{2}|0)\s?[\d\s/-]{6,}\d/;
const POSTAL_CITY = /\b\d{5}\s+[A-ZÄÖÜ][\wäöüß-]+/;
const IMPORT_INTENT = /\b(anlegen|importier\w*|erfass\w*|übernehm\w*|einlesen|aufnehm\w*)\b/i;
const CONTACT_WORDS = /\b(kontakt\w*|mieter\w*|eigentümer\w*|adress\w*|person\w*|firma|firmen|dienstleister\w*)\b/i;

/** Pasted contact data: at least one e-mail, phone number or postal code with town, and more
 *  than a short question. The AI extraction decides the rest; this only routes the flow. */
export function looksLikeContactData(text: string): boolean {
  const hits = [EMAIL, PHONE, POSTAL_CITY].filter((re) => re.test(text)).length;
  return hits >= 1 && (hits >= 2 || text.length >= 40);
}

/** "Kontakte anlegen", "Mieter importieren": the user wants the import flow without a file. */
export function looksLikeImportIntent(text: string): boolean {
  return IMPORT_INTENT.test(text) && CONTACT_WORDS.test(text);
}

export function pageContext(pathname: string, search?: string): PageContext {
  return chatPageContext(pathname, search);
}

type Chip = { id: string; label: string };
type Entry =
  | { kind: "assistant"; text: string; chips?: Chip[]; links?: ChatLink[]; tools?: AiToolUse[] }
  | { kind: "user"; text: string }
  | { kind: "proposal"; proposal: Proposal }
  | { kind: "chat_action"; proposal: Proposal }
  | { kind: "result"; importRun: ImportRun };

type Stage = "idle" | "uploading" | "queued" | "processing" | "done";

type Flow =
  | { step: "idle" }
  | { step: "ask_question" }
  | { step: "summarize" }
  | { step: "import_contacts"; role?: string; pendingText?: string }
  | { step: "import_property" }
  | { step: "offer_import"; text: string }
  | { step: "confirm"; proposal: Proposal; documentIds: string[]; sourceText?: string }
  | { step: "reject_reason"; proposal: Proposal; documentIds: string[]; sourceText?: string };

/** Floating assistant available on every screen. Scripted steps with quick replies drive the
 *  import flow; the AI only extracts and answers, nothing is written before an explicit yes. */
export function AiChatWidget() {
  const t = useTranslations("AiChat");
  const pathname = usePathname();
  // Query string and the page's own `data-chat-context` are read after navigation (no
  // useSearchParams: the widget lives in the layout and must not need a Suspense boundary).
  const [search, setSearch] = useState("");
  const [attribute, setAttribute] = useState<ReturnType<typeof readChatContextAttribute>>(null);
  useEffect(() => {
    setSearch(typeof window === "undefined" ? "" : window.location.search);
    setAttribute(readChatContextAttribute(typeof document === "undefined" ? null : document));
  }, [pathname]);
  const override = useChatContextOverride();
  const ctx = mergeChatContext(pageContext(pathname, search), override ?? attribute);
  /** Page name shown to the user and sent as `page`: area, sub page (a record detail page is
   *  named by the area alone; the record itself goes as context) and settings entry. */
  const subLabel = ctx.subArea && ctx.subArea !== "detail" && t.has(`subArea.${ctx.subArea}`) ? t(`subArea.${ctx.subArea}`) : null;
  const pageName = [t(`area.${ctx.area}`), ctx.settingsEntry ? ctx.settingsEntry.title : subLabel]
    .filter(Boolean)
    .join(" / ");
  const [open, setOpen] = useState(false);
  // Reiter "Assistent" am Objekt und am Kontakt (M7-05) opens the widget with the record.
  useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener(ASSISTANT_OPEN_EVENT, onOpen);
    return () => window.removeEventListener(ASSISTANT_OPEN_EVENT, onOpen);
  }, []);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [flow, setFlow] = useState<Flow>({ step: "idle" });
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const greetedFor = useRef<string | null>(null);
  const conversationRef = useRef<string | null>(null);

  const say = (text: string, chips?: Chip[], links?: ChatLink[], tools?: AiToolUse[]) =>
    setEntries((p) => [...p, { kind: "assistant", text, chips, links, tools }]);
  const push = (e: Entry) => setEntries((p) => [...p, e]);

  const startChips = (area: Area): Chip[] => {
    // Suggestions for the page and the record open on it: buttons that send the question.
    const chips: Chip[] = suggestionsFor(ctx).map((key) => ({
      id: `suggest:${key}`,
      label: t(`suggestions.${key}`, { title: ctx.settingsEntry?.title ?? t(`area.${ctx.area}`) }),
    }));
    if (area === "contacts" || area === "start" || area === "other") chips.push({ id: "import_contacts", label: t("chips.importContacts") });
    if (area === "properties" || area === "hoa") chips.push({ id: "import_property", label: t("chips.importProperty") });
    chips.push({ id: "ask", label: t("chips.ask") }, { id: "summarize", label: t("chips.summarize") });
    return chips;
  };

  // Greeting once per page area and record; the page is named so the user sees the context.
  // The widget survives client navigations (app layout), so the conversation of the previous
  // page is dropped here: the next question starts a conversation with the current record
  // (context_type, context_id) and never carries the history of another record.
  const greetKey = `${ctx.area}:${ctx.subArea ?? ""}:${ctx.entityId ?? ""}`;
  useEffect(() => {
    if (!open || greetedFor.current === greetKey) return;
    greetedFor.current = greetKey;
    setFlow({ step: "idle" });
    setConversation(null);
    conversationRef.current = null;
    say(t(ctx.entityType ? "greetingRecord" : "greeting", { page: pageName }), startChips(ctx.area));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, greetKey]);

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "end" });
  }, [entries, busy]);

  const ensureConversation = async (): Promise<Conversation> => {
    // Reuse only a conversation of the current record (see the greeting effect).
    if (conversation && conversation.context_type === ctx.contextType && (conversation.context_id ?? null) === ctx.contextId) return conversation;
    const res = await bff<Conversation>("/api/bff/ai/conversations", {
      method: "POST",
      body: JSON.stringify({ title: t("conversationTitle", { page: pageName }), context_type: ctx.contextType, context_id: ctx.contextId }),
    });
    if (!res.ok) throw new Error(stepError(t("stepConversation"), res.status, res.message));
    setConversation(res.data);
    conversationRef.current = res.data.id;
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
    const startedAt = Date.now();
    setStage(current.status === "running" ? "processing" : "queued");
    while (isRunPending(current)) {
      if (Date.now() - startedAt >= RUN_TIMEOUT_MS) throw new Error(t("runTimeout"));
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      const res = await bff<Run>(`/api/bff/ai/runs/${current.id}`);
      if (!res.ok) throw new Error(stepError(t("stepRun"), res.status, res.message));
      current = res.data;
      if (isRunPending(current)) setStage(current.status === "running" ? "processing" : "queued");
    }
    setStage("done");
    return current;
  };

  const runTask = async (task: string, content: string, documentIds: string[]): Promise<Run> => {
    const conv = await ensureConversation();
    const res = await bff<Run>(`/api/bff/ai/conversations/${conv.id}/messages`, {
      method: "POST",
      body: JSON.stringify({
        content,
        task,
        document_ids: documentIds,
        // Page context for questions: the lookup starts from the record open on the page.
        ...(task === "answer_question"
          ? {
              page: pageName,
              context_entity_type: ctx.entityType,
              context_entity_id: ctx.entityId,
              area: ctx.area,
              sub_area: ctx.subArea,
            }
          : {}),
      }),
    });
    if (!res.ok) throw new Error(stepError(t("stepMessage"), res.status, res.message));
    return waitForRun(res.data);
  };

  /** The stored chat answer of a run (text with hit list, links, proposal), as in the log. */
  const answerOf = async (run: Run): Promise<Message | null> => {
    if (!conversationRef.current) return null;
    const res = await bff<Conversation>(`/api/bff/ai/conversations/${conversationRef.current}`);
    if (!res.ok) return null;
    return [...(res.data.messages ?? [])].reverse().find((m) => m.role === "assistant" && m.task_run_id === run.id) ?? null;
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

  const summarizeProposal = (proposal: Proposal, documentIds: string[], sourceText?: string) => {
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
    setFlow({ step: "confirm", proposal, documentIds, sourceText });
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
    setStage("idle");
    try {
      await fn();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
      setStage("idle");
    }
  };

  /** Without files the message text itself is the material (pasted contact data); the backend
   *  reads it as the only chunk. The result is still a proposal that needs a yes. */
  const extract = (task: "extract_contacts" | "extract_property", content: string, list: File[], sourceText?: string) =>
    guarded(async () => {
      if (list.length) setStage("uploading");
      const ids = list.length ? await upload(list) : [];
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
      summarizeProposal(proposal, ids, sourceText);
    });

  const extractPasted = (role: string, pasted: string) =>
    extract("extract_contacts", [t(`roleText.${role}`), pasted].join("\n\n"), [], pasted);

  const onChip = (chip: Chip) => {
    push({ kind: "user", text: chip.label });
    switch (chip.id) {
      case "restart":
        say(t("greeting", { page: pageName }), startChips(ctx.area));
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
        const pasted = flow.step === "import_contacts" ? flow.pendingText : undefined;
        setFlow({ step: "import_contacts", role });
        if (pasted) {
          void extractPasted(role, pasted);
          return;
        }
        say(t("importContactsUpload"));
        return;
      }
      case "use_as_contacts":
        if (flow.step === "offer_import") {
          setFlow({ step: "import_contacts", pendingText: flow.text });
          say(t("pastedContactsRole"), [
            { id: "role_owner", label: t("chips.owners") },
            { id: "role_tenant", label: t("chips.tenants") },
            { id: "role_mixed", label: t("chips.mixed") },
          ]);
        }
        return;
      case "ask_instead":
        if (flow.step === "offer_import") {
          const question = flow.text;
          setFlow({ step: "idle" });
          void askQuestion(question, []);
        }
        return;
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
            const count = (s: string) => p.rows.filter((r) => r.status === s).length;
            const res = await bff<ImportRun>(`/api/bff/ai/proposals/${proposal.id}/apply`, { method: "POST", body: JSON.stringify({ contacts }) });
            if (!res.ok) throw new Error(res.message);
            push({ kind: "result", importRun: res.data });
            // The skipped rows are named so the user knows what was left out and why.
            const skipped = [
              count("incomplete") ? t("skippedIncomplete", { count: count("incomplete") }) : null,
              count("existing") ? t("skippedExisting", { count: count("existing") }) : null,
              count("invalid") ? t("skippedInvalid", { count: count("invalid") }) : null,
            ].filter(Boolean);
            say([t("onlyNewDone", { created: count("new") }), ...(skipped.length ? [t("skippedList", { list: skipped.join(", ") })] : []), t("imported")].join("\n"), [{ id: "restart", label: t("chips.restart") }]);
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
        if (chip.id.startsWith("suggest:")) {
          // Suggestion button: sends the prefilled question (the label) with the page context.
          setFlow({ step: "idle" });
          void askQuestion(chip.label, []);
        }
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
        const role = flow.role ?? "mixed";
        if (list.length === 0) {
          // No file: pasted contact data is the material, anything else needs a file or text.
          if (content && looksLikeContactData(content)) return extractPasted(role, content);
          return say(t("needFileOrPaste"));
        }
        return extract("extract_contacts", [t(`roleText.${role}`), content].filter(Boolean).join(" "), list);
      }
      case "import_property":
        if (list.length === 0) return say(t("needFile"));
        return extract("extract_property", [t("propertyText"), content].filter(Boolean).join(" "), list);
      case "summarize":
        if (list.length === 0) return say(t("needFile"));
        return guarded(async () => {
          setStage("uploading");
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
          const { documentIds, sourceText } = flow;
          say(t("working"));
          const correction = [t("correctionText", { text: content }), ...(documentIds.length === 0 && sourceText ? [sourceText] : [])].join("\n\n");
          const run = await runTask("extract_contacts", correction, documentIds);
          const problem = describeRun(run);
          const proposal = problem ? null : await proposalOf(run);
          if (!proposal) {
            say(problem ?? t("noProposal"), [{ id: "restart", label: t("chips.restart") }]);
            setFlow({ step: "idle" });
            return;
          }
          summarizeProposal(proposal, documentIds, sourceText);
        });
      case "offer_import":
        return say(t("pleaseChoose"), [
          { id: "use_as_contacts", label: t("chips.useAsContacts") },
          { id: "ask_instead", label: t("chips.askInstead") },
        ]);
      case "confirm":
        return say(t("pleaseChoose"), [
          { id: "yes", label: t("chips.yes") },
          { id: "no", label: t("chips.no") },
        ]);
      default:
        if (list.length === 0 && content && looksLikeContactData(content)) {
          // Pasted contact data outside the import flow: offer the import, never start it alone.
          setFlow({ step: "offer_import", text: content });
          return say(t("pastedContactsDetected"), [
            { id: "use_as_contacts", label: t("chips.useAsContacts") },
            { id: "ask_instead", label: t("chips.askInstead") },
          ]);
        }
        if (list.length === 0 && content && looksLikeImportIntent(content)) {
          setFlow({ step: "import_contacts" });
          return say(t("importIntentDetected"), [
            { id: "role_owner", label: t("chips.owners") },
            { id: "role_tenant", label: t("chips.tenants") },
            { id: "role_mixed", label: t("chips.mixed") },
          ]);
        }
        // Free question (with optional documents), on every page.
        return askQuestion(content, list);
    }
  };

  const askQuestion = (content: string, list: File[]) =>
    guarded(async () => {
      if (list.length) setStage("uploading");
      const ids = list.length ? await upload(list) : [];
      say(t("working"));
      const run = await runTask("answer_question", [t("pageHint", { page: pageName }), content].join(" "), ids);
      // Prefer the stored answer: it carries the platform hit list, the links and, without a
      // released provider, the deterministic fallback (rule AI-LOOKUP-01).
      const stored = await answerOf(run);
      if (stored) {
        say(stored.content, startChips(ctx.area), stored.links ?? [], toolsUsedOf(run));
        const proposal = stored.proposal_id ? await proposalOf({ ...run, proposal_id: stored.proposal_id }) : null;
        if (proposal?.entity_type === "chat_action") push({ kind: "chat_action", proposal });
      } else {
        const problem = describeRun(run);
        const out = run.output as { answer?: string; answerable?: boolean } | null;
        say(problem ?? (out?.answerable === false ? t("notAnswerable") : (out?.answer ?? "")), startChips(ctx.area), run.links ?? [], toolsUsedOf(run));
      }
      setFlow({ step: "idle" });
    });

  const needsFile = flow.step === "import_contacts" || flow.step === "import_property" || flow.step === "summarize";

  return (
    <>
      <div className="fixed bottom-5 right-5 z-40 h-14 w-14">
        {busy ? (
          <span
            aria-hidden
            data-testid="ai-chat-pulse"
            className="absolute inset-0 animate-ping rounded-full bg-gold/50"
          />
        ) : null}
        <button
          type="button"
          aria-label={open ? t("close") : t("open")}
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className="relative flex h-14 w-14 items-center justify-center rounded-full bg-accent text-accent-fg shadow-lg transition duration-200 hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-focus"
        >
          <span aria-hidden className="text-xl">
            {open ? "×" : "✦"}
          </span>
        </button>
      </div>
      {open ? (
        <section
          aria-label={t("title")}
          className="fixed inset-0 z-40 flex flex-col overflow-hidden border-2 border-gold/30 bg-raised shadow-lg sm:inset-auto sm:bottom-20 sm:right-5 sm:h-[32rem] sm:w-[min(26rem,calc(100vw-2.5rem))] sm:rounded-2xl"
          style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
        >
          <header className="flex items-center justify-between border-b border-rail-border bg-rail-bg px-4 py-3 text-rail-fg">
            <div>
              <p className="text-sm font-semibold">{t("title")}</p>
              <p className="mhvp-label text-rail-muted">{t("onPage", { page: pageName })}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-gold" aria-hidden />
              <button
                type="button"
                aria-label={t("close")}
                onClick={() => setOpen(false)}
                className="flex h-11 w-11 items-center justify-center rounded-md text-rail-muted hover:bg-rail-hover hover:text-rail-fg sm:hidden"
              >
                <span aria-hidden>×</span>
              </button>
            </div>
          </header>
          <ol className="flex flex-1 flex-col gap-2 overflow-y-auto px-3 py-3 text-sm" data-testid="ai-chat-log">
            {entries.map((e, i) => {
              if (e.kind === "user") {
                return (
                  <li key={i} className="max-w-[85%] self-end rounded-2xl rounded-br-md bg-anthracite-soft px-3.5 py-2 text-fg">
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
              if (e.kind === "chat_action") {
                return (
                  <li key={i} className="rounded-lg border border-border p-2">
                    <ChatActionProposal proposal={e.proposal} />
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
                <li key={i} className="max-w-[92%] self-start rounded-2xl rounded-bl-md bg-gold-soft px-3.5 py-2 text-fg">
                  <p className="whitespace-pre-wrap">{e.text}</p>
                  <ChatLinks links={e.links} />
                  <ChatTools tools={e.tools} />
                  {last && e.chips?.length && !busy ? (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {e.chips.map((c) => (
                        <button
                          key={c.id}
                          type="button"
                          className="inline-flex items-center rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-fg transition duration-150 hover:border-gold hover:bg-surface-2 focus:outline-none focus:ring-2 focus:ring-focus"
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
            {busy && stage !== "idle" ? (
              <li
                role="status"
                aria-live="polite"
                data-testid="ai-chat-progress"
                className="flex max-w-[92%] flex-col gap-1.5 self-start rounded-2xl rounded-bl-md bg-gold-soft px-3.5 py-2"
              >
                <span className="text-xs font-medium text-muted">{t(`progress.${stage}`)}</span>
                <div className="h-1.5 w-40 max-w-full overflow-hidden rounded-full bg-border">
                  <div className="h-full w-1/3 animate-[ai-chat-progress_1.2s_ease-in-out_infinite] rounded-full bg-gold" />
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
              <label className="inline-flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-full border border-border bg-surface text-fg transition duration-150 hover:border-gold hover:bg-surface-2" title={t("attach")}>
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
