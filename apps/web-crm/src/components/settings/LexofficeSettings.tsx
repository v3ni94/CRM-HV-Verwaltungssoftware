"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

import { LexofficeContactLinks } from "./LexofficeContactLinks";
import { LexofficeOutbox } from "./LexofficeOutbox";
import { LexofficeRecurringPreps } from "./LexofficeRecurringPreps";

/** Einstellungen, Lexware Office (INT-LEXO-01). The API key is write only; the API answers
 *  "gesetzt" plus the last four characters. Enabling needs the AVV date and a successful
 *  connection test; the invoice switches need the INVOICING feature of the organisation. */
export type LexofficeConfig = {
  id: string;
  legal_entity_id: string | null;
  legal_entity_name: string | null;
  label: string | null;
  base_url: string;
  app_base_url: string;
  enabled: boolean;
  api_key_set: boolean;
  api_key_last4: string | null;
  token_invalid: boolean;
  organization_id: string | null;
  organization_name: string | null;
  profile_tax_type: string | null;
  profile_small_business: boolean | null;
  profile_business_features: string[];
  has_invoicing: boolean;
  avv_confirmed_on: string | null;
  avv_confirmed_by: string | null;
  avv_note: string | null;
  mailbox_id: string | null;
  sync_contacts: boolean;
  sync_names: boolean;
  invoice_copies: boolean;
  invoice_drafts: boolean;
  last_tested_at: string | null;
  last_test_ok: boolean | null;
  last_test_message: string | null;
  message?: string | null;
};

export type LexofficeLegalEntity = { id: string; kind: string; name: string };
export type LexofficeKindMapping = { kind: string; label: string; legal_entity_id: string | null; legal_entity_name: string | null; config_id: string | null };
export type LexofficeMailbox = { id: string; address: string };

type Tab = "configs" | "kinds" | "links" | "outbox" | "recurring";
const NEW = "__new__";

export function LexofficeSettings({
  configs,
  legalEntities,
  kinds,
  mailboxes,
  canManage,
  canLinkContacts,
  canAccounting,
}: {
  configs: LexofficeConfig[];
  legalEntities: LexofficeLegalEntity[];
  kinds: LexofficeKindMapping[];
  mailboxes: LexofficeMailbox[];
  canManage: boolean;
  canLinkContacts: boolean;
  canAccounting: boolean;
}) {
  const t = useTranslations("Lexoffice");
  const [tab, setTab] = useState<Tab>("configs");
  const [rows, setRows] = useState(configs);
  const [selected, setSelected] = useState<string>(configs[0]?.id ?? NEW);
  const current = rows.find((c) => c.id === selected) ?? null;
  const tabs: { id: Tab; label: string; show: boolean }[] = [
    { id: "configs", label: t("tabs.configs"), show: true },
    { id: "kinds", label: t("tabs.kinds"), show: true },
    { id: "links", label: t("tabs.links"), show: canLinkContacts && rows.length > 0 },
    { id: "outbox", label: t("tabs.outbox"), show: canManage && rows.length > 0 },
    { id: "recurring", label: t("tabs.recurring"), show: canAccounting },
  ];
  return (
    <div className="flex flex-col gap-4">
      <nav className="flex flex-wrap gap-2" aria-label={t("title")}>
        {tabs
          .filter((x) => x.show)
          .map((x) => (
            <button key={x.id} type="button" className={tab === x.id ? ui.primary : ui.secondary} aria-pressed={tab === x.id} onClick={() => setTab(x.id)}>
              {x.label}
            </button>
          ))}
      </nav>
      {tab === "configs" ? (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-2" role="tablist" aria-label={t("config.heading")}>
            {rows.map((c) => (
              <button key={c.id} type="button" role="tab" aria-selected={selected === c.id} className={selected === c.id ? ui.primary : ui.secondary} onClick={() => setSelected(c.id)}>
                {c.label || c.legal_entity_name || t("config.default")}
              </button>
            ))}
            {canManage ? (
              <button type="button" role="tab" aria-selected={selected === NEW} className={selected === NEW ? ui.primary : ui.secondary} onClick={() => setSelected(NEW)}>
                {t("config.new")}
              </button>
            ) : null}
          </div>
          <LexofficeConfigForm
            key={selected}
            config={current}
            legalEntities={legalEntities}
            mailboxes={mailboxes}
            canManage={canManage}
            onSaved={(saved) => {
              setRows((prev) => (prev.some((c) => c.id === saved.id) ? prev.map((c) => (c.id === saved.id ? saved : c)) : [...prev, saved]));
              setSelected(saved.id);
            }}
          />
        </div>
      ) : null}
      {tab === "kinds" ? <LexofficeKindMappingForm initial={kinds} legalEntities={legalEntities} canManage={canManage} /> : null}
      {tab === "links" && current ? <LexofficeContactLinks configId={current.id} canDecide={canLinkContacts} /> : null}
      {tab === "links" && !current ? <p className={ui.help}>{t("config.organizationUnknown")}</p> : null}
      {tab === "outbox" ? <LexofficeOutbox configId={current?.id ?? null} canManage={canManage} /> : null}
      {tab === "recurring" ? <LexofficeRecurringPreps canManage={canAccounting} /> : null}
    </div>
  );
}

export function LexofficeConfigForm({
  config,
  legalEntities,
  mailboxes,
  canManage,
  onSaved,
}: {
  config: LexofficeConfig | null;
  legalEntities: LexofficeLegalEntity[];
  mailboxes: LexofficeMailbox[];
  canManage: boolean;
  onSaved: (saved: LexofficeConfig) => void;
}) {
  const t = useTranslations("Lexoffice");
  const [saved, setSaved] = useState<LexofficeConfig | null>(config);
  const [legalEntityId, setLegalEntityId] = useState(config?.legal_entity_id ?? "");
  const [label, setLabel] = useState(config?.label ?? "");
  const [apiKey, setApiKey] = useState("");
  const [mailboxId, setMailboxId] = useState(config?.mailbox_id ?? "");
  const [avvDate, setAvvDate] = useState(config?.avv_confirmed_on ?? "");
  const [avvNote, setAvvNote] = useState(config?.avv_note ?? "");
  const [enabled, setEnabled] = useState(config?.enabled ?? false);
  const [syncContacts, setSyncContacts] = useState(config?.sync_contacts ?? false);
  const [syncNames, setSyncNames] = useState(config?.sync_names ?? false);
  const [invoiceCopies, setInvoiceCopies] = useState(config?.invoice_copies ?? false);
  const [invoiceDrafts, setInvoiceDrafts] = useState(config?.invoice_drafts ?? false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function apply(data: LexofficeConfig, note: string) {
    setSaved(data);
    setEnabled(data.enabled);
    setSyncContacts(data.sync_contacts);
    setSyncNames(data.sync_names);
    setInvoiceCopies(data.invoice_copies);
    setInvoiceDrafts(data.invoice_drafts);
    setApiKey("");
    setMessage(data.message ? `${note} ${data.message}.` : note);
    onSaved(data);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    setError(null);
    const body: Record<string, unknown> = {
      label,
      enabled,
      sync_contacts: syncContacts,
      sync_names: syncNames,
      invoice_copies: invoiceCopies,
      invoice_drafts: invoiceDrafts,
      avv_note: avvNote,
      ...(apiKey ? { api_key: apiKey } : {}),
      ...(avvDate ? { avv_confirmed_on: avvDate } : {}),
      ...(mailboxId ? { mailbox_id: mailboxId } : { clear_mailbox: true }),
    };
    const res = saved
      ? await bff<LexofficeConfig>(`/api/bff/integrations/lexoffice/configs/${saved.id}`, { method: "PUT", body: JSON.stringify(body) })
      : await bff<LexofficeConfig>("/api/bff/integrations/lexoffice/configs", {
          method: "POST",
          body: JSON.stringify({ ...body, legal_entity_id: legalEntityId || null }),
        });
    setBusy(false);
    if (res.ok) apply(res.data, t("config.saved"));
    else setError(res.message);
  }

  async function test() {
    if (!saved) return;
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<LexofficeConfig>(`/api/bff/integrations/lexoffice/configs/${saved.id}/test`, { method: "POST" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    apply(res.data, res.data.last_test_ok ? t("config.testOk") : t("config.testFailed", { reason: res.data.last_test_message ?? "" }));
  }

  const disabled = busy || !canManage;
  const invoicing = saved?.has_invoicing ?? false;
  const id = saved?.id ?? "new";
  return (
    <form onSubmit={submit} className={`${ui.card} flex flex-col gap-3`}>
      <h2 className={ui.h2}>{saved ? saved.label || saved.legal_entity_name || t("config.default") : t("config.new")}</h2>
      {saved?.token_invalid ? (
        <p role="alert" className={ui.alert}>
          {t("config.tokenInvalid")}
        </p>
      ) : null}
      {saved && saved.api_key_set && saved.last_test_ok !== true && !saved.token_invalid ? <p className={ui.warning}>{t("config.testRequired")}</p> : null}
      {!saved ? (
        <div>
          <label htmlFor={`lx-entity-${id}`} className={ui.label}>
            {t("config.legalEntity")}
          </label>
          <select id={`lx-entity-${id}`} className={ui.input} value={legalEntityId} disabled={disabled} onChange={(e) => setLegalEntityId(e.target.value)}>
            <option value="">{t("config.legalEntityNone")}</option>
            {legalEntities.map((le) => (
              <option key={le.id} value={le.id}>
                {le.name}
              </option>
            ))}
          </select>
        </div>
      ) : (
        <p className={ui.help}>
          {t("config.legalEntity")}: {saved.legal_entity_name ?? t("config.legalEntityNone")}
        </p>
      )}
      <div>
        <label htmlFor={`lx-label-${id}`} className={ui.label}>
          {t("config.label")}
        </label>
        <input id={`lx-label-${id}`} className={ui.input} value={label} maxLength={120} disabled={disabled} onChange={(e) => setLabel(e.target.value)} />
      </div>
      <div>
        <label htmlFor={`lx-key-${id}`} className={ui.label}>
          {t("config.apiKey")}
        </label>
        <input
          id={`lx-key-${id}`}
          type="password"
          autoComplete="new-password"
          className={ui.input}
          value={apiKey}
          disabled={disabled}
          placeholder={saved?.api_key_set ? t("config.apiKeyStored", { last4: saved.api_key_last4 ?? "" }) : t("config.apiKeyMissing")}
          onChange={(e) => setApiKey(e.target.value)}
        />
      </div>
      <div>
        <label htmlFor={`lx-mailbox-${id}`} className={ui.label}>
          {t("config.mailbox")}
        </label>
        <select id={`lx-mailbox-${id}`} className={ui.input} value={mailboxId} disabled={disabled} onChange={(e) => setMailboxId(e.target.value)}>
          <option value="">{t("config.mailboxNone")}</option>
          {mailboxes.map((m) => (
            <option key={m.id} value={m.id}>
              {m.address}
            </option>
          ))}
        </select>
        <p className={ui.help}>{t("config.mailboxHint")}</p>
      </div>
      <fieldset className="flex flex-col gap-2">
        <legend className={ui.label}>{t("config.avvTitle")}</legend>
        <p className={ui.help}>{t("config.avvHint")}</p>
        <label htmlFor={`lx-avv-date-${id}`} className={ui.label}>
          {t("config.avvDate")}
        </label>
        <input id={`lx-avv-date-${id}`} type="date" className={ui.input} value={avvDate} disabled={disabled} onChange={(e) => setAvvDate(e.target.value)} />
        <label htmlFor={`lx-avv-note-${id}`} className={ui.label}>
          {t("config.avvNote")}
        </label>
        <input id={`lx-avv-note-${id}`} className={ui.input} value={avvNote} maxLength={500} disabled={disabled} onChange={(e) => setAvvNote(e.target.value)} />
        {saved?.avv_confirmed_on ? <p className={ui.help}>{t("config.avvConfirmed", { date: formatDate(saved.avv_confirmed_on) })}</p> : null}
      </fieldset>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={enabled} disabled={disabled} onChange={(e) => setEnabled(e.target.checked)} />
        {t("config.enabled")}
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={syncContacts} disabled={disabled} onChange={(e) => setSyncContacts(e.target.checked)} />
        {t("config.syncContacts")}
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={syncNames} disabled={disabled || !syncContacts} onChange={(e) => setSyncNames(e.target.checked)} />
        {t("config.syncNames")}
      </label>
      <label className="flex items-center gap-2 text-sm" title={invoicing ? undefined : t("config.noInvoicing")}>
        <input type="checkbox" checked={invoiceCopies} disabled={disabled || !invoicing} onChange={(e) => setInvoiceCopies(e.target.checked)} />
        {t("config.invoiceCopies")}
      </label>
      <label className="flex items-center gap-2 text-sm" title={invoicing ? undefined : t("config.noInvoicing")}>
        <input type="checkbox" checked={invoiceDrafts} disabled={disabled || !invoicing} onChange={(e) => setInvoiceDrafts(e.target.checked)} />
        {t("config.invoiceDrafts")}
      </label>
      {saved && !invoicing && saved.organization_id ? <p className={ui.help}>{t("config.noInvoicing")}</p> : null}
      <p className={ui.help}>{saved?.organization_name ? t("config.organization", { name: saved.organization_name }) : t("config.organizationUnknown")}</p>
      <p className={ui.help}>{t("config.dataHint")}</p>
      {saved?.last_tested_at ? <p className={ui.help}>{t("config.lastTest", { at: formatDateTime(saved.last_tested_at), result: saved.last_test_message ?? "" })}</p> : null}
      {canManage ? (
        <div className={ui.formActions}>
          <button type="submit" className={ui.primary} disabled={busy}>
            {t("config.save")}
          </button>
          <button type="button" className={ui.secondary} disabled={busy || !saved?.api_key_set} onClick={() => void test()}>
            {t("config.test")}
          </button>
        </div>
      ) : (
        <p className={ui.help}>{t("config.readOnly")}</p>
      )}
      {message ? (
        <p role="status" className={ui.success}>
          {message}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </form>
  );
}

export function LexofficeKindMappingForm({ initial, legalEntities, canManage }: { initial: LexofficeKindMapping[]; legalEntities: LexofficeLegalEntity[]; canManage: boolean }) {
  const t = useTranslations("Lexoffice");
  const [rows, setRows] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<LexofficeKindMapping[]>("/api/bff/integrations/lexoffice/invoice-kinds", {
      method: "PUT",
      body: JSON.stringify(rows.map((r) => ({ kind: r.kind, legal_entity_id: r.legal_entity_id }))),
    });
    setBusy(false);
    if (res.ok) {
      setRows(res.data);
      setMessage(t("kinds.saved"));
    } else setError(res.message);
  }

  return (
    <form onSubmit={save} className={`${ui.card} flex flex-col gap-3`}>
      <h2 className={ui.h2}>{t("kinds.heading")}</h2>
      <p className={ui.help}>{t("kinds.intro")}</p>
      <div className={ui.tableScroll}>
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("kinds.kind")}</th>
              <th>{t("kinds.legalEntity")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.kind}>
                <td>
                  <label htmlFor={`lx-kind-${r.kind}`}>{r.label}</label>
                </td>
                <td>
                  <select
                    id={`lx-kind-${r.kind}`}
                    className={ui.input}
                    value={r.legal_entity_id ?? ""}
                    disabled={busy || !canManage}
                    onChange={(e) => setRows((prev) => prev.map((x) => (x.kind === r.kind ? { ...x, legal_entity_id: e.target.value || null } : x)))}
                  >
                    <option value="">{t("kinds.unassigned")}</option>
                    {legalEntities.map((le) => (
                      <option key={le.id} value={le.id}>
                        {le.name}
                      </option>
                    ))}
                  </select>
                  {r.legal_entity_id && !r.config_id ? <p className={ui.help}>{t("kinds.noConfig")}</p> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canManage ? (
        <div className={ui.formActions}>
          <button type="submit" className={ui.primary} disabled={busy}>
            {t("kinds.save")}
          </button>
        </div>
      ) : null}
      {message ? (
        <p role="status" className={ui.success}>
          {message}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </form>
  );
}
