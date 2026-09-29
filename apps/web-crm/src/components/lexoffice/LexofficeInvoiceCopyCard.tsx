"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Invoice copy requests of a ticket (INT-LEXO-01, `/integrations/lexoffice/tickets/{id}/
 *  invoice-copies`): status, invoice number, lookup hits and the recipient check. A person
 *  requests, corrects, links the recipient or accepts; accept fetches the PDF and creates the
 *  reply draft with locked recipient and second approval. The card stays away when the
 *  extension is not reachable for this user. */
export type InvoiceCopyHit = {
  config_id: string;
  legal_entity_label: string | null;
  kind: string;
  lexoffice_invoice_id: string;
  voucher_number: string;
  voucher_date: string | null;
  total_gross: string | null;
  status: string;
  address_name: string | null;
  address_contact_id: string | null;
  deeplink: string | null;
};

export type InvoiceCopyRequest = {
  id: string;
  ticket_id: string;
  message_id: string | null;
  invoice_number: string;
  requester_contact_id: string | null;
  recipient_contact_id: string | null;
  sender_config_id: string | null;
  status: string;
  lookup: { status?: string; hits?: InvoiceCopyHit[]; selected_invoice_id?: string | null };
  verification: {
    status?: string;
    hint_from_address_match?: boolean | null;
    warnings?: string[];
    recipient?: { contact_id: string; display_name: string; primary_email: string | null };
  };
  document_id: string | null;
  reply_message_id: string | null;
  last_error: string | null;
  created_at: string;
};

const STATUS_KEYS = new Set(["pending", "found", "ambiguous", "draft_only", "creditnote_only", "not_found", "fetching", "draft_ready", "draft_in_lexoffice", "failed", "rejected"]);
const VERIFICATION_KEYS = new Set(["pending", "verified", "requester_mismatch", "recipient_unresolved", "not_found"]);
const OPEN = new Set(["pending", "found", "ambiguous", "draft_only", "creditnote_only", "not_found", "failed"]);

type PickedContact = { id: string; display_name: string };

function amount(value: string | null): string {
  if (!value) return "";
  const num = Number(value);
  if (!Number.isFinite(num)) return value;
  return `${num.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} EUR`;
}

export function LexofficeInvoiceCopyCard({ ticketId, canUpdate, canLinkContacts }: { ticketId: string; canUpdate: boolean; canLinkContacts: boolean }) {
  const t = useTranslations("Lexoffice.copy");
  const [rows, setRows] = useState<InvoiceCopyRequest[] | null>(null);
  const [hidden, setHidden] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const [number, setNumber] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await bff<InvoiceCopyRequest[]>(`/api/bff/integrations/lexoffice/tickets/${ticketId}/invoice-copies`);
    if (res.ok) setRows(res.data);
    else {
      setRows([]);
      setHidden(true);
    }
  }, [ticketId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function post(path: string, body?: unknown): Promise<boolean> {
    setBusy(true);
    setError(null);
    setNotice(null);
    const res = await bff<InvoiceCopyRequest>(path, { method: "POST", ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return false;
    }
    await load();
    return true;
  }

  if (hidden || rows === null || !canUpdate) return null;

  return (
    <section className={`${ui.card} flex min-w-0 flex-col gap-2`} data-testid="lexoffice-invoice-copy-card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{t("heading")}</h2>
        {!requesting ? (
          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => setRequesting(true)}>
            {t("request")}
          </button>
        ) : null}
      </div>
      {requesting ? (
        <form
          className="flex flex-wrap items-end gap-2"
          data-testid="lexoffice-invoice-copy-request"
          onSubmit={(e) => {
            e.preventDefault();
            void post(`/api/bff/integrations/lexoffice/tickets/${ticketId}/invoice-copies`, { invoice_number: number.trim() }).then((ok) => {
              if (ok) {
                setRequesting(false);
                setNumber("");
              }
            });
          }}
        >
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("invoiceNumber")}</span>
            <input className={ui.input} value={number} maxLength={64} onChange={(e) => setNumber(e.target.value)} />
          </label>
          <button type="submit" className={ui.primary} disabled={busy || number.trim().length === 0}>
            {t("submitRequest")}
          </button>
          <button type="button" className={ui.button} onClick={() => setRequesting(false)}>
            {t("cancel")}
          </button>
          <p className={`${ui.help} w-full`}>{t("invoiceNumberHint")}</p>
        </form>
      ) : null}
      {rows.length === 0 && !requesting ? <p className="text-xs text-muted">{t("empty")}</p> : null}
      {rows.map((row) => (
        <RequestRow key={row.id} row={row} busy={busy} canLinkContacts={canLinkContacts} post={post} onNotice={setNotice} />
      ))}
      {notice ? <p className={ui.success}>{notice}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}

function RequestRow({
  row,
  busy,
  canLinkContacts,
  post,
  onNotice,
}: {
  row: InvoiceCopyRequest;
  busy: boolean;
  canLinkContacts: boolean;
  post: (path: string, body?: unknown) => Promise<boolean>;
  onNotice: (text: string) => void;
}) {
  const t = useTranslations("Lexoffice.copy");
  const [mode, setMode] = useState<"none" | "correct" | "reject">("none");
  const [newNumber, setNewNumber] = useState(row.invoice_number);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<PickedContact[]>([]);
  const [picked, setPicked] = useState<PickedContact | null>(null);
  const [reason, setReason] = useState("");

  const statusKey = STATUS_KEYS.has(row.status) ? row.status : "failed";
  const verification = row.verification.status && VERIFICATION_KEYS.has(row.verification.status) ? row.verification.status : "pending";
  const invoiceHits = (row.lookup.hits ?? []).filter((h) => h.kind === "invoice");
  const selected = row.lookup.selected_invoice_id ?? null;
  const acceptable = row.status === "found" && verification === "verified";
  const base = `/api/bff/integrations/lexoffice/invoice-copies/${row.id}`;

  async function searchContacts() {
    const q = query.trim();
    if (q.length < 2) return;
    const res = await bff<{ items: PickedContact[] }>(`/api/bff/contacts?${new URLSearchParams({ q, page_size: "10" }).toString()}`);
    setHits(res.ok ? res.data.items.map((c) => ({ id: c.id, display_name: c.display_name })) : []);
  }

  return (
    <article className="flex flex-col gap-2 rounded-md border border-border p-3 text-sm" data-testid="lexoffice-invoice-copy-request-row">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{row.invoice_number}</span>
        <span className={ui.badge} data-testid="lexoffice-invoice-copy-status">
          {t(`status.${statusKey}`)}
        </span>
        <span className="text-xs text-muted">
          {t("createdAt")} {formatDateTime(row.created_at)}
        </span>
      </div>
      <p className="text-xs" data-testid="lexoffice-invoice-copy-verification">
        {t("verification.label")}: {t(`verification.${verification}`)}
        {row.verification.recipient ? ` (${t("recipient")}: ${row.verification.recipient.display_name})` : ""}
      </p>
      {row.verification.hint_from_address_match === true ? <p className="text-xs text-muted">{t("hintMatch")}</p> : null}
      {row.verification.hint_from_address_match === false ? <p className="text-xs text-muted">{t("hintNoMatch")}</p> : null}
      {(row.verification.warnings ?? []).map((w) => (
        <p key={w} className={ui.error}>
          {w}
        </p>
      ))}
      {invoiceHits.length > 0 ? (
        <ul className="flex flex-col gap-1 text-xs" aria-label={t("hits")}>
          {invoiceHits.map((hit) => (
            <li key={hit.lexoffice_invoice_id} className="flex flex-wrap items-center gap-2">
              <span>
                {t("hit", {
                  entity: hit.legal_entity_label ?? "",
                  number: hit.voucher_number,
                  date: hit.voucher_date ? formatDate(hit.voucher_date) : "",
                  status: hit.status,
                  amount: amount(hit.total_gross),
                })}
              </span>
              {hit.deeplink ? (
                <a href={hit.deeplink} target="_blank" rel="noreferrer" className="hover:underline">
                  {t("openInvoice")}
                </a>
              ) : null}
              {row.status === "ambiguous" && selected !== hit.lexoffice_invoice_id ? (
                <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(`${base}/correct`, { selected_invoice_id: hit.lexoffice_invoice_id })}>
                  {t("choose")}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {row.last_error ? (
        <p className={ui.error}>
          {t("lastError")}: {row.last_error}
        </p>
      ) : null}
      {row.reply_message_id ? (
        <Link href={`/mail?message=${row.reply_message_id}`} className="text-xs hover:underline">
          {t("openReply")}
        </Link>
      ) : null}

      {OPEN.has(row.status) && mode === "none" ? (
        <div className="flex flex-wrap gap-2">
          {acceptable ? (
            <button
              type="button"
              className={ui.primary}
              disabled={busy}
              onClick={() => void post(`${base}/accept`).then((ok) => ok && onNotice(t("accepted")))}
            >
              {t("accept")}
            </button>
          ) : null}
          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => setMode("correct")}>
            {t("correct")}
          </button>
          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => setMode("reject")}>
            {t("reject")}
          </button>
        </div>
      ) : null}
      {acceptable && mode === "none" ? <p className={ui.help}>{t("acceptHint")}</p> : null}

      {mode === "correct" ? (
        <div className="flex flex-col gap-2" data-testid="lexoffice-invoice-copy-correct">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("correctNumber")}</span>
            <input className={ui.input} value={newNumber} maxLength={64} onChange={(e) => setNewNumber(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("correctRequester")}</span>
            <span className="flex gap-2">
              <input
                className={ui.input}
                value={query}
                placeholder={t("searchContact")}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void searchContacts();
                  }
                }}
              />
              <button type="button" className={ui.buttonSm} disabled={query.trim().length < 2} onClick={() => void searchContacts()}>
                {t("search")}
              </button>
            </span>
          </label>
          {hits.length > 0 ? (
            <ul className="flex flex-wrap gap-1">
              {hits.map((c) => (
                <li key={c.id}>
                  <button type="button" className={ui.buttonSm} aria-pressed={picked?.id === c.id} onClick={() => setPicked(c)}>
                    {c.display_name}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          {picked ? <p className="text-xs text-muted">{picked.display_name}</p> : null}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className={ui.primary}
              disabled={busy || (newNumber.trim() === row.invoice_number && !picked)}
              onClick={() =>
                void post(`${base}/correct`, {
                  invoice_number: newNumber.trim() !== row.invoice_number ? newNumber.trim() : null,
                  requester_contact_id: picked?.id ?? null,
                }).then((ok) => ok && setMode("none"))
              }
            >
              {t("saveCorrection")}
            </button>
            {canLinkContacts && picked && verification === "recipient_unresolved" ? (
              <button
                type="button"
                className={ui.button}
                disabled={busy}
                title={t("linkRecipientHint")}
                onClick={() => void post(`${base}/link-recipient`, { contact_id: picked.id }).then((ok) => ok && setMode("none"))}
              >
                {t("linkRecipient")}
              </button>
            ) : null}
            <button type="button" className={ui.button} onClick={() => setMode("none")}>
              {t("cancel")}
            </button>
          </div>
        </div>
      ) : null}

      {mode === "reject" ? (
        <div className="flex flex-wrap items-end gap-2" data-testid="lexoffice-invoice-copy-reject">
          <label className="flex min-w-0 flex-1 flex-col gap-1">
            <span className={ui.label}>{t("rejectReason")}</span>
            <input className={ui.input} value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
          </label>
          <button
            type="button"
            className={ui.danger}
            disabled={busy || reason.trim().length === 0}
            onClick={() => void post(`${base}/reject`, { reason: reason.trim() }).then((ok) => ok && setMode("none"))}
          >
            {t("confirmReject")}
          </button>
          <button type="button" className={ui.button} onClick={() => setMode("none")}>
            {t("cancel")}
          </button>
        </div>
      ) : null}
    </article>
  );
}
