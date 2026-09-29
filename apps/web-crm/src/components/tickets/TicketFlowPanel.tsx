"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { PROCESS_CODES, TicketProcessBadge } from "@/components/tickets/TicketProcessBadge";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type TicketFlow = {
  process_code?: string | null;
  label?: string | null;
  responsible_role?: string | null;
  required_links?: string[];
  links?: Record<string, boolean>;
  deadline_proposals?: { type: string; status: string; due_on: string | null }[];
  document_kinds?: string[];
  applied_at?: string | null;
  source?: string | null;
};

const DEADLINE_KINDS = [
  "contract_end",
  "contract_termination",
  "meter_calibration",
  "bank_consent",
  "document_retention_end",
  "service_contract_notice",
  "meeting_resolution_deadline",
  "energy_certificate",
  "move_in",
  "move_out",
  "maintenance",
  "note_follow_up",
  "meeting",
  "ticket_due",
] as const;
const ROLE_CODES = [
  "tenant_admin",
  "administrator",
  "standard",
  "read_only",
  "read_only_master_data",
  "clerk_no_delete",
  "clerk_no_accounting",
  "accountant_no_banking",
  "accountant_banking",
  "caretaker",
  "technical_clerk",
  "support",
  "insurance_broker",
  "portal_user",
  "tax_advisor",
] as const;

/** Process flow of a ticket (rule M19-11): responsible role, required links with their
 *  status, deadline proposals (type only, the date is entered by the member on the ticket,
 *  never generated) and documents to collect. Without a flow the panel offers to apply one
 *  from the catalogue (`POST /tickets/{id}/apply-process`). The checklist itself is shown by
 *  `TicketChecklist`. */
export function TicketFlowPanel({
  ticketId,
  processCode,
  flow,
  canUpdate,
}: {
  ticketId: string;
  processCode: string | null;
  flow: TicketFlow | null;
  canUpdate: boolean;
}) {
  const t = useTranslations("Tickets.process");
  const tk = useTranslations("Deadlines.kind");
  const router = useRouter();
  const [choice, setChoice] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function apply(code: string) {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/tickets/${ticketId}/apply-process`, {
      method: "POST",
      body: JSON.stringify({ process_code: code }),
    });
    setBusy(false);
    if (res.ok) router.refresh();
    else setError(res.message);
  }

  const hasFlow = Boolean(processCode && flow && flow.process_code);
  const links = flow?.links ?? {};
  const roleLabel = (code: string) =>
    (ROLE_CODES as readonly string[]).includes(code) ? t(`roles.${code}`) : code;
  const kindLabel = (code: string) => ((DEADLINE_KINDS as readonly string[]).includes(code) ? tk(code) : code);

  return (
    <section className={`${ui.card} flex flex-col gap-2`} data-testid="ticket-flow">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className={ui.h2}>{t("title")}</h2>
        <TicketProcessBadge code={processCode} />
      </div>
      {hasFlow && flow ? (
        <div className="flex flex-col gap-2 text-sm">
          {flow.responsible_role ? (
            <p>
              <span className="text-muted">{t("responsibleRole")}: </span>
              {roleLabel(flow.responsible_role)}
            </p>
          ) : null}
          {(flow.required_links ?? []).length > 0 ? (
            <div>
              <span className="text-muted">{t("requiredLinks")}: </span>
              <ul className="inline">
                {(flow.required_links ?? []).map((kind) => (
                  <li key={kind} className="mr-2 inline-flex items-center gap-1" data-testid={`flow-link-${kind}`}>
                    <span aria-hidden="true">{links[kind] ? "✓" : "○"}</span>
                    {t(`links.${kind}`)}
                    <span className="sr-only">{links[kind] ? t("linkPresent") : t("linkMissing")}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {(flow.deadline_proposals ?? []).length > 0 ? (
            <div>
              <span className="text-muted">{t("deadlineProposals")}: </span>
              <ul className="inline">
                {(flow.deadline_proposals ?? []).map((d) => (
                  <li key={d.type} className="mr-2 inline" data-testid="flow-deadline">
                    {kindLabel(d.type)}
                  </li>
                ))}
              </ul>
              <p className="text-xs text-muted">{t("deadlineHint")}</p>
            </div>
          ) : null}
          {(flow.document_kinds ?? []).length > 0 ? (
            <p>
              <span className="text-muted">{t("documents")}: </span>
              {(flow.document_kinds ?? []).join(", ")}
            </p>
          ) : null}
        </div>
      ) : canUpdate ? (
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("choose")}</span>
            <select className={ui.input} value={choice} onChange={(e) => setChoice(e.target.value)} data-testid="flow-choice">
              <option value="">{t("none")}</option>
              {PROCESS_CODES.map((code) => (
                <option key={code} value={code}>
                  {t(`codes.${code}`)}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className={ui.buttonSm} disabled={busy || !choice} onClick={() => void apply(choice)}>
            {t("apply")}
          </button>
        </div>
      ) : (
        <p className="text-xs text-muted">{t("none")}</p>
      )}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
