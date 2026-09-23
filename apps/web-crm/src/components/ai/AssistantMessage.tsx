"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { reasoningOf, type Message, type Proposal, type Run } from "@/lib/ai";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

import { ContactProposal } from "./ContactProposal";
import { PropertyProposal } from "./PropertyProposal";
import { ProposalBadge } from "./ProposalBadge";

/** One chat message; assistant answers load their run (confidence, sources) and proposal. */
export function AssistantMessage({ message }: { message: Message }) {
  const t = useTranslations("Ai");
  const [run, setRun] = useState<Run | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isAssistant = message.role === "assistant";

  useEffect(() => {
    if (!isAssistant) return;
    let cancelled = false;
    void (async () => {
      if (message.task_run_id) {
        const res = await bff<Run>(`/api/bff/ai/runs/${message.task_run_id}`);
        if (!cancelled && res.ok) setRun(res.data);
      }
      if (message.proposal_id) {
        const res = await bff<Proposal>(`/api/bff/ai/proposals/${message.proposal_id}`);
        if (cancelled) return;
        if (res.ok) setProposal(res.data);
        else setError(res.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isAssistant, message.task_run_id, message.proposal_id]);

  if (!isAssistant) {
    return (
      <li className="self-end rounded border border-border bg-bg px-3 py-2 text-sm" data-testid="message-user">
        <p className="whitespace-pre-wrap">{message.content}</p>
        <p className="mt-1 text-xs text-muted">
          {formatDateTime(message.created_at)}
          {message.document_ids.length ? `, ${t("attachments", { count: message.document_ids.length })}` : ""}
        </p>
      </li>
    );
  }

  const failed = run && run.status !== "succeeded";
  return (
    <li className={`${ui.card} flex flex-col gap-2 text-sm`} data-testid="message-assistant">
      {failed ? null : <ProposalBadge confidence={run?.confidence} reasoning={reasoningOf(run?.output ?? null)} />}
      <p className="whitespace-pre-wrap">{message.content}</p>
      <p className="text-xs text-muted">{formatDateTime(message.created_at)}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {proposal ? (
        proposal.decision !== "pending" && proposal.import_run_id ? (
          <p className="text-sm">
            {t(`decision.${proposal.decision}`)}{" "}
            <Link href={`/importe/${proposal.import_run_id}`} className="underline">
              {t("toImport")}
            </Link>
          </p>
        ) : proposal.entity_type === "contacts" ? (
          <ContactProposal proposal={proposal} />
        ) : (
          <PropertyProposal proposal={proposal} />
        )
      ) : null}
    </li>
  );
}
