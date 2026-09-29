"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

import { LexofficeInvoiceDraftForm } from "./LexofficeInvoiceDraftForm";

/** Lexware Office link status of one contact (INT-LEXO-01), read from
 *  `GET /integrations/lexoffice/contacts/{id}/lexoffice`: one row per organisation. The badge
 *  is a compact summary for the contact header, the section offers the person decisions
 *  (link, push, resolve conflict). Every action only queues a transfer. */
export type ContactLexofficeStatus = {
  config_id: string;
  label: string | null;
  legal_entity_id: string | null;
  sync_status: string | null;
  last_synced_at: string | null;
  diverged: boolean;
  deeplink: string | null;
  last_error: string | null;
  link_id: string | null;
};

const SETTINGS_HREF = "/einstellungen/schnittstellen/lexware-office";
const DECIDABLE = new Set(["proposed", "ambiguous"]);
const PUSHABLE = new Set(["linked", "synced", "error"]);

function useContactStatus(contactId: string) {
  const [rows, setRows] = useState<ContactLexofficeStatus[] | null>(null);
  const [failed, setFailed] = useState(false);
  const load = useCallback(async () => {
    const res = await bff<ContactLexofficeStatus[]>(`/api/bff/integrations/lexoffice/contacts/${contactId}/lexoffice`);
    if (res.ok) {
      setRows(res.data);
      setFailed(false);
    } else {
      setRows([]);
      setFailed(true);
    }
  }, [contactId]);
  useEffect(() => {
    void load();
  }, [load]);
  return { rows, failed, reload: load };
}

export function LexofficeContactBadge({ contactId }: { contactId: string }) {
  const t = useTranslations("Lexoffice");
  const { rows } = useContactStatus(contactId);
  const linked = (rows ?? []).filter((r) => r.sync_status);
  if (linked.length === 0) return null;
  const worst = linked.find((r) => r.sync_status === "conflict" || r.sync_status === "error" || r.sync_status === "manual_required") ?? linked[0]!;
  return (
    <span className={ui.badge} data-testid="lexoffice-contact-badge" title={worst.label ?? undefined}>
      {t("contact.badge")}: {t(`links.status.${worst.sync_status}`)}
      {worst.diverged ? `, ${t("contact.diverged")}` : ""}
    </span>
  );
}

export function LexofficeContactSection({
  contactId,
  contactName,
  canUpdate,
  canCreateDraft,
}: {
  contactId: string;
  contactName?: string | null;
  canUpdate: boolean;
  canCreateDraft: boolean;
}) {
  const t = useTranslations("Lexoffice");
  const { rows, failed, reload } = useContactStatus(contactId);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showDraft, setShowDraft] = useState(false);

  if (rows === null) return null;
  if (!failed && rows.length === 0 && !canCreateDraft) return null;

  async function post(row: ContactLexofficeStatus, action: string, body?: unknown) {
    if (!row.link_id) return;
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<unknown>(`/api/bff/integrations/lexoffice/configs/${row.config_id}/contacts/links/${row.link_id}/${action}`, {
      method: "POST",
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    setBusy(false);
    if (res.ok) {
      setMessage(t("contact.done"));
      await reload();
    } else setError(res.message);
  }

  return (
    <section className={`${ui.card} flex min-w-0 flex-col gap-2`} data-testid="lexoffice-contact-section">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{t("contact.heading")}</h2>
        <div className="flex flex-wrap gap-2">
          {canCreateDraft && !showDraft ? (
            <button type="button" className={ui.buttonSm} onClick={() => setShowDraft(true)}>
              {t("contact.newDraft")}
            </button>
          ) : null}
          <Link href={SETTINGS_HREF} className="text-xs text-muted hover:underline">
            {t("contact.settings")}
          </Link>
        </div>
      </div>
      {failed ? <p className="text-xs text-muted">{t("contact.loadFailed")}</p> : null}
      {!failed && rows.length === 0 ? <p className="text-xs text-muted">{t("contact.none")}</p> : null}
      <ul className="flex flex-col gap-2">
        {rows.map((row) => (
          <li key={row.config_id} className="flex flex-col gap-1 text-sm" data-testid="lexoffice-contact-row">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{row.label ?? row.config_id}</span>
              {row.sync_status ? (
                <span className={ui.badge}>
                  {t(`links.status.${row.sync_status}`)}
                  {row.diverged ? `, ${t("contact.diverged")}` : ""}
                </span>
              ) : (
                <span className="text-xs text-muted">{t("contact.noLink")}</span>
              )}
              {row.last_synced_at ? <span className="text-xs text-muted">{t("contact.lastSynced", { at: formatDateTime(row.last_synced_at) })}</span> : null}
              {row.deeplink ? (
                <a href={row.deeplink} target="_blank" rel="noreferrer" className="text-xs hover:underline">
                  {t("contact.open")}
                </a>
              ) : null}
            </div>
            {row.sync_status === "conflict" ? <p className="text-xs text-muted">{t("contact.conflictHint")}</p> : null}
            {row.last_error ? <p className={ui.error}>{row.last_error}</p> : null}
            {canUpdate && row.link_id ? (
              <div className="flex flex-wrap gap-2">
                {DECIDABLE.has(row.sync_status ?? "") ? (
                  <>
                    <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(row, "decide", { action: "link", contact_id: contactId })}>
                      {t("contact.link")}
                    </button>
                    <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(row, "decide", { action: "create_remote", contact_id: contactId, roles: ["customer"] })}>
                      {t("contact.createRemote")}
                    </button>
                  </>
                ) : null}
                {PUSHABLE.has(row.sync_status ?? "") ? (
                  <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(row, "push")}>
                    {t("contact.push")}
                  </button>
                ) : null}
                {row.sync_status === "conflict" ? (
                  <>
                    <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(row, "resolve-conflict", { resolution: "keep_crm" })}>
                      {t("contact.keepCrm")}
                    </button>
                    <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void post(row, "resolve-conflict", { resolution: "keep_lexoffice" })}>
                      {t("contact.keepLexoffice")}
                    </button>
                  </>
                ) : null}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
      {message ? <p className={ui.success}>{message}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {showDraft ? <LexofficeInvoiceDraftForm contactId={contactId} contactName={contactName} onClose={() => setShowDraft(false)} /> : null}
    </section>
  );
}
