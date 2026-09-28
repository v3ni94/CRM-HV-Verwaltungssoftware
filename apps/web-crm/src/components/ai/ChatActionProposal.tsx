"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import type { ImportRun, Proposal } from "@/lib/ai";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Change = { field: string; old?: string | null; new: string };
type Proposed = {
  kind?: "contact_change" | "contact_note" | "ticket_create";
  contact_id?: string | null;
  contact_label?: string | null;
  changes?: Change[];
  note?: string;
  title?: string;
  description?: string | null;
  property_label?: string | null;
  unit_label?: string | null;
  reason?: string;
};

/** Change asked for in the chat (rule AI-LOOKUP-01): shown as a proposal; written only after
 *  the confirmation through `POST /ai/proposals/{id}/apply`. Bank details never come here. */
export function ChatActionProposal({ proposal }: { proposal: Proposal }) {
  const t = useTranslations("AiChat");
  const p = proposal.proposed as Proposed;
  const [state, setState] = useState<"pending" | "applied" | "rejected">(proposal.decision === "pending" ? "pending" : proposal.decision === "rejected" ? "rejected" : "applied");
  const [result, setResult] = useState<ImportRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const act = async (action: "apply" | "reject") => {
    setBusy(true);
    setError(null);
    const res = await bff<ImportRun>(`/api/bff/ai/proposals/${proposal.id}/${action}`, {
      method: "POST",
      ...(action === "apply" ? { body: JSON.stringify({ chat_action: {} }) } : {}),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    if (action === "apply") setResult(res.data);
    setState(action === "apply" ? "applied" : "rejected");
  };

  const summary = (result?.summary ?? {}) as { ticket_id?: string; contact_id?: string };
  const target = summary.ticket_id ? `/tickets/${summary.ticket_id}` : p.contact_id ? `/kontakte/${p.contact_id}` : null;

  return (
    <div className={`${ui.card} flex flex-col gap-2 text-sm`} data-testid="chat-action-proposal">
      <p className="font-medium">{t(`chatAction.kind.${p.kind ?? "contact_change"}`)}</p>
      {p.contact_label ? <p>{t("chatAction.contact", { name: p.contact_label })}</p> : null}
      {p.reason ? <p className="text-muted">{t("chatAction.reason", { reason: p.reason })}</p> : null}
      {p.kind === "contact_change" ? (
        <ul className="list-disc pl-5">
          {(p.changes ?? []).map((c) => (
            <li key={c.field}>{t("chatAction.change", { field: t(`chatAction.field.${c.field}`), value: c.new })}</li>
          ))}
        </ul>
      ) : null}
      {p.kind === "contact_note" ? <p className="whitespace-pre-wrap">{p.note}</p> : null}
      {p.kind === "ticket_create" ? (
        <>
          <p>{t("chatAction.title", { title: p.title ?? "" })}</p>
          {p.description ? <p className="whitespace-pre-wrap text-muted">{p.description}</p> : null}
          {p.property_label ? <p>{t("chatAction.property", { name: p.property_label })}</p> : null}
          {p.unit_label ? <p>{t("chatAction.unit", { name: p.unit_label })}</p> : null}
        </>
      ) : null}
      {state === "pending" ? (
        <div className="flex flex-wrap gap-2">
          <button type="button" className={ui.primary} disabled={busy} onClick={() => void act("apply")}>
            {t("chatAction.confirm")}
          </button>
          <button type="button" className={ui.secondary} disabled={busy} onClick={() => void act("reject")}>
            {t("chatAction.reject")}
          </button>
        </div>
      ) : (
        <p role="status">
          {t(state === "applied" ? "chatAction.applied" : "chatAction.rejected")}{" "}
          {state === "applied" && target ? (
            <Link href={target} className="underline">
              {t("chatAction.open")}
            </Link>
          ) : null}
        </p>
      )}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
