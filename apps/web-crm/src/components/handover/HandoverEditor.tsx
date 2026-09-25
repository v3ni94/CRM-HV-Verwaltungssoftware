"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

import { PortalAccessBox } from "./PortalAccessBox";
import { SignaturePad } from "./SignaturePad";
import {
  FIELDS,
  PHOTO_SECTIONS,
  SECTIONS,
  itemTitle,
  type Doc,
  type FieldDef,
  type Full,
  type Item,
  type Section,
} from "./types";

type Tab =
  | "object"
  | Section
  | "deposit"
  | "internal"
  | "attachments"
  | "signatures"
  | "summary";

const TABS: Tab[] = [
  "object",
  "participants",
  "deposit",
  "internal",
  "meters",
  "rooms",
  "defects",
  "keys",
  "items",
  "notes",
  "attachments",
  "signatures",
  "summary",
];

const OBJECT_FIELDS: FieldDef[] = [
  { name: "street", type: "text" },
  { name: "house_number", type: "text" },
  { name: "postal_code", type: "text" },
  { name: "city", type: "text" },
  { name: "object_label", type: "text" },
  { name: "building", type: "text" },
  { name: "floor", type: "text" },
  { name: "unit_number", type: "text" },
  { name: "unit_label", type: "text" },
  { name: "unit_position", type: "text" },
  { name: "handover_date", type: "date" },
  { name: "handover_start", type: "time" },
  { name: "handover_end", type: "time" },
  { name: "hide_time_information", type: "checkbox" },
  { name: "handover_location", type: "text" },
  { name: "ticket_number", type: "text" },
  { name: "reference_number", type: "text" },
  { name: "rental_contract_number", type: "text" },
  { name: "general_note", type: "textarea", wide: true },
];
const DEPOSIT_FIELDS: FieldDef[] = [
  { name: "deposit_amount", type: "decimal" },
  { name: "deposit_account_holder", type: "text" },
  { name: "deposit_iban", type: "text" },
  { name: "deposit_bic", type: "text" },
  { name: "deposit_bank_name", type: "text" },
  { name: "deposit_iban_verified", type: "checkbox" },
  { name: "deposit_separate_statement", type: "checkbox" },
  { name: "deposit_note", type: "textarea", wide: true },
];
const INTERNAL_FIELDS: FieldDef[] = [
  { name: "management_number", type: "text" },
  { name: "internal_contact", type: "text" },
  { name: "internal_note", type: "textarea", wide: true },
];

function valueOf(
  item: Record<string, unknown>,
  field: FieldDef,
): string | boolean {
  const v = item[field.name];
  if (field.type === "checkbox") return Boolean(v);
  if (v == null) return "";
  if (field.type === "time") return String(v).slice(0, 5);
  if (field.type === "decimal") return String(v).replace(".", ",");
  return String(v);
}

/** German input ("1.500,50" or "1500,50") or API format ("1500.50") to an API decimal string. */
export function parseDecimal(raw: string): string {
  const text = raw.trim().replace(/\s/g, "");
  if (text.includes(",")) return text.replace(/\./g, "").replace(",", ".");
  const dots = text.split(".").length - 1;
  return dots > 1 ? text.replace(/\./g, "") : text;
}

function toBody(
  form: Record<string, string | boolean>,
  fields: FieldDef[],
): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const f of fields) {
    const v = form[f.name];
    if (f.type === "checkbox") body[f.name] = Boolean(v);
    else if (v === "" || v === undefined) body[f.name] = null;
    else if (f.type === "number") body[f.name] = Number(v);
    else if (f.type === "decimal") body[f.name] = parseDecimal(String(v));
    else body[f.name] = v;
  }
  return body;
}

/** Field grid used for the protocol, the deposit, the internal section and every sub record. */
function Fields({
  id,
  fields,
  form,
  onChange,
  disabled,
  section,
  rooms,
  t,
}: {
  id: string;
  fields: FieldDef[];
  form: Record<string, string | boolean>;
  onChange: (name: string, value: string | boolean) => void;
  disabled: boolean;
  section?: Section;
  rooms?: Item[];
  t: (key: string) => string;
}) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {fields.map((f) => {
        const key = `${id}-${f.name}`;
        const label = t(`fields.${f.name}`);
        const value = form[f.name];
        if (f.type === "checkbox") {
          return (
            <label
              key={key}
              className="flex items-center gap-2 self-end text-sm"
            >
              <input
                type="checkbox"
                checked={Boolean(value)}
                onChange={(e) => onChange(f.name, e.target.checked)}
                disabled={disabled}
              />
              {label}
            </label>
          );
        }
        if (f.type === "select") {
          const options =
            f.name === "room_id"
              ? (rooms ?? []).map((r) => ({
                  value: r.id,
                  label: String(r.name || r.room_type || "Raum"),
                }))
              : (f.options ?? []).map((o) => ({
                  value: o,
                  label: t(`options.${section ?? "x"}.${f.name}.${o}`),
                }));
          return (
            <div key={key}>
              <label htmlFor={key} className={ui.label}>
                {label}
              </label>
              <select
                id={key}
                className={ui.input}
                value={String(value ?? "")}
                onChange={(e) => onChange(f.name, e.target.value)}
                disabled={disabled}
              >
                <option value="">–</option>
                {options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          );
        }
        if (f.type === "textarea") {
          return (
            <div key={key} className={f.wide ? "md:col-span-3" : ""}>
              <label htmlFor={key} className={ui.label}>
                {label}
              </label>
              <textarea
                id={key}
                className={ui.input}
                rows={3}
                value={String(value ?? "")}
                onChange={(e) => onChange(f.name, e.target.value)}
                disabled={disabled}
              />
            </div>
          );
        }
        return (
          <div key={key}>
            <label htmlFor={key} className={ui.label}>
              {label}
            </label>
            <input
              id={key}
              type={
                f.type === "number"
                  ? "number"
                  : f.type === "date"
                    ? "date"
                    : f.type === "time"
                      ? "time"
                      : "text"
              }
              inputMode={f.type === "decimal" ? "decimal" : undefined}
              className={ui.input}
              value={String(value ?? "")}
              onChange={(e) => onChange(f.name, e.target.value)}
              disabled={disabled}
            />
          </div>
        );
      })}
    </div>
  );
}

/** Übergabeprotokoll (M30): sections as tabs, every save goes straight to the API, the
 *  protocol is locked after completion and continues only as a new version. */
export function HandoverEditor({ initial }: { initial: Full }) {
  const t = useTranslations("Handover");
  const router = useRouter();
  const [p, setP] = useState<Full>(initial);
  const [tab, setTab] = useState<Tab>(
    (initial.current_step as Tab) || "object",
  );
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showHints, setShowHints] = useState(false);
  const [reason, setReason] = useState("");
  const locked = p.locked;
  const base = `/api/bff/handover/protocols/${p.id}`;

  async function reload() {
    const res = await bff<Full>(base);
    if (res.ok) setP(res.data);
  }

  async function patchProtocol(body: Record<string, unknown>) {
    setError(null);
    const res = await bff(base, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    if (!res.ok) setError(res.message);
    else {
      setInfo(t("saved"));
      await reload();
    }
  }

  function switchTab(next: Tab) {
    setTab(next);
    setInfo(null);
    if (!locked)
      void bff(base, {
        method: "PATCH",
        body: JSON.stringify({ current_step: next }),
      });
  }

  async function complete(force: boolean) {
    if (!force && p.hints.length > 0) {
      setShowHints(true);
      return;
    }
    if (
      !window.confirm(t(force ? "complete.confirmForce" : "complete.confirm"))
    )
      return;
    setBusy(true);
    setError(null);
    const res = await bff<Full>(`${base}/complete`, {
      method: "POST",
      body: JSON.stringify({ force }),
    });
    setBusy(false);
    if (res.ok) {
      setP(res.data);
      setTab("summary");
      setShowHints(false);
    } else setError(res.message);
  }

  async function newVersion() {
    if (reason.trim().length < 3) {
      setError(t("versions.reasonRequired"));
      return;
    }
    setBusy(true);
    const res = await bff<Full>(`${base}/versions`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
    setBusy(false);
    if (res.ok) router.push(`/makler/uebergabe/${res.data.id}`);
    else setError(res.message);
  }

  async function status(action: "cancel" | "archive" | "unarchive") {
    if (!window.confirm(t(`status.confirm.${action}`))) return;
    const res = await bff(`${base}/status`, {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    if (res.ok) await reload();
    else setError(res.message);
  }

  async function dispatch() {
    setBusy(true);
    const res = await bff<{
      created: unknown[];
      skipped: { reason: string }[];
    }>(`${base}/dispatches`, {
      method: "POST",
      body: JSON.stringify({ channel: "email" }),
    });
    setBusy(false);
    if (res.ok) {
      setInfo(
        t("dispatch.result", {
          created: res.data.created.length,
          skipped: res.data.skipped.length,
        }),
      );
      await reload();
    } else setError(res.message);
  }

  return (
    <div className="flex flex-col gap-4" data-testid="handover-editor">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={
            p.finalized
              ? ui.badgeSuccess
              : p.status === "cancelled"
                ? ui.badgeDanger
                : ui.badgeGold
          }
        >
          {t(`statusLabel.${p.status}`)}
        </span>
        {p.version > 1 ? (
          <span className={ui.badge}>
            {t("versions.label", { version: p.version })}
          </span>
        ) : null}
        <a
          className={ui.buttonSm}
          href={`/api/handover-files/handover/protocols/${p.id}/pdf`}
          target="_blank"
          rel="noopener"
        >
          {p.finalized ? t("pdf.stored") : t("pdf.preview")}
        </a>
        {!locked ? (
          <button
            type="button"
            className={ui.buttonSm}
            onClick={() => status("cancel")}
            disabled={busy}
          >
            {t("status.cancel")}
          </button>
        ) : null}
        {p.status !== "archived" && locked ? (
          <button
            type="button"
            className={ui.buttonSm}
            onClick={() => status("archive")}
            disabled={busy}
          >
            {t("status.archive")}
          </button>
        ) : null}
        {p.status === "archived" ? (
          <button
            type="button"
            className={ui.buttonSm}
            onClick={() => status("unarchive")}
            disabled={busy}
          >
            {t("status.unarchive")}
          </button>
        ) : null}
      </div>
      {locked ? (
        <p className={ui.notice}>
          {p.status === "cancelled" ? t("lockedCancelled") : t("locked")}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {info ? <p className={ui.success}>{info}</p> : null}

      <nav className="flex flex-wrap gap-1" aria-label={t("steps")}>
        {TABS.map((x) => (
          <button
            key={x}
            type="button"
            className={x === tab ? ui.badgeGold : ui.badge}
            onClick={() => switchTab(x)}
            aria-current={x === tab ? "step" : undefined}
          >
            {t(`tabs.${x}`)}
          </button>
        ))}
      </nav>

      {tab === "object" ? (
        <ProtocolForm
          p={p}
          fields={OBJECT_FIELDS}
          onSave={patchProtocol}
          disabled={locked}
          t={t}
          id="object"
        />
      ) : null}
      {tab === "deposit" ? (
        <>
          <p className={ui.notice}>{t("deposit.notice")}</p>
          <ProtocolForm
            p={p}
            fields={DEPOSIT_FIELDS}
            onSave={patchProtocol}
            disabled={locked}
            t={t}
            id="deposit"
          />
        </>
      ) : null}
      {tab === "internal" ? (
        <>
          <p className={ui.notice}>{t("internal.notice")}</p>
          <ProtocolForm
            p={p}
            fields={INTERNAL_FIELDS}
            onSave={patchProtocol}
            disabled={locked}
            t={t}
            id="internal"
          />
        </>
      ) : null}
      {(SECTIONS as readonly string[]).includes(tab) ? (
        <SectionList
          section={tab as Section}
          p={p}
          base={base}
          disabled={locked}
          onChanged={reload}
          onError={setError}
          t={t}
        />
      ) : null}
      {tab === "attachments" ? (
        <Attachments
          p={p}
          base={base}
          disabled={locked}
          onChanged={reload}
          onError={setError}
          t={t}
        />
      ) : null}
      {tab === "signatures" ? (
        <div className="flex flex-col gap-3">
          <p className={ui.notice}>{t("signature.consent")}</p>
          {p.signatures.length ? (
            <ul className="grid gap-2 md:grid-cols-2">
              {p.signatures.map((s) => (
                <li
                  key={s.id}
                  className={`${ui.card} flex items-start justify-between gap-2`}
                >
                  <div className="text-sm">
                    <div className="font-medium">
                      {s.signer_name || t("signature.noName")}
                    </div>
                    <div className="text-muted">
                      {s.signer_role ? t(`roles.${s.signer_role}`) : ""} ·{" "}
                      {formatDateTime(s.signed_at)}
                    </div>
                    {/* eslint-disable-next-line @next/next/no-img-element -- protected same-origin blob, no optimizer */}
                    <img
                      src={`/api/handover-files/documents/${s.document_id}/content`}
                      alt=""
                      className="mt-2 max-h-20 rounded border border-border bg-white"
                    />
                  </div>
                  {!locked ? (
                    <button
                      type="button"
                      className={ui.buttonSm}
                      onClick={async () => {
                        if (!window.confirm(t("signature.confirmDelete")))
                          return;
                        const res = await bff(`${base}/signatures/${s.id}`, {
                          method: "DELETE",
                        });
                        if (res.ok) await reload();
                        else setError(res.message);
                      }}
                    >
                      {t("delete")}
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted">{t("signature.none")}</p>
          )}
          <SignaturePad
            protocolId={p.id}
            kind={p.kind}
            participants={p.participants}
            signatures={p.signatures}
            disabled={locked}
            onSaved={reload}
          />
        </div>
      ) : null}
      {tab === "summary" ? (
        <div className="flex flex-col gap-4">
          <div className={ui.card}>
            <h2 className={ui.h2}>{t("summary.title")}</h2>
            <dl className="mt-2 grid gap-x-6 gap-y-1 text-sm md:grid-cols-2">
              <dt className="text-muted">{t("fields.address")}</dt>
              <dd>{p.address || "–"}</dd>
              <dt className="text-muted">{t("tabs.participants")}</dt>
              <dd>{p.participants.length}</dd>
              <dt className="text-muted">{t("tabs.meters")}</dt>
              <dd>{p.meters.length}</dd>
              <dt className="text-muted">{t("tabs.rooms")}</dt>
              <dd>
                {p.rooms.length} / {t("tabs.defects")} {p.defects.length}
              </dd>
              <dt className="text-muted">{t("tabs.keys")}</dt>
              <dd>{p.keys.length}</dd>
              <dt className="text-muted">{t("tabs.signatures")}</dt>
              <dd>{p.signatures.length}</dd>
            </dl>
          </div>
          {p.hints.length && (showHints || !locked) ? (
            <div className={ui.notice} data-testid="hints">
              <strong>{t("hints.title")}</strong>
              <ul className="mt-1 list-disc pl-5">
                {p.hints.map((h) => (
                  <li key={h}>{h}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {!locked ? (
            <div className="flex flex-wrap gap-2">
              {showHints ? (
                <button
                  type="button"
                  className={ui.primary}
                  disabled={busy}
                  onClick={() => complete(true)}
                >
                  {t("complete.force")}
                </button>
              ) : (
                <button
                  type="button"
                  className={ui.primary}
                  disabled={busy}
                  onClick={() => complete(false)}
                >
                  {t("complete.action")}
                </button>
              )}
              <p className="self-center text-sm text-muted">
                {t("complete.help")}
              </p>
            </div>
          ) : null}
          {p.finalized ? (
            <div className={`${ui.card} flex flex-col gap-2`}>
              <h2 className={ui.h2}>{t("dispatch.title")}</h2>
              <p className="text-sm text-muted">{t("dispatch.help")}</p>
              <div>
                <button
                  type="button"
                  className={ui.button}
                  disabled={busy}
                  onClick={dispatch}
                >
                  {t("dispatch.action")}
                </button>
              </div>
            </div>
          ) : null}
          {locked && p.status !== "cancelled" ? (
            <div className={`${ui.card} flex flex-col gap-2`}>
              <h2 className={ui.h2}>{t("versions.title")}</h2>
              <ul className="text-sm">
                {p.versions.map((v) => (
                  <li key={v.id}>
                    <Link
                      href={`/makler/uebergabe/${v.id}`}
                      className="hover:underline"
                    >
                      {t("versions.label", { version: v.version })}
                    </Link>{" "}
                    <span className="text-muted">
                      {t(`statusLabel.${v.status}`)}
                      {v.completed_at
                        ? `, ${formatDateTime(v.completed_at)}`
                        : ""}
                      {v.change_reason ? `, ${v.change_reason}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
              <label htmlFor="reason" className={ui.label}>
                {t("versions.reason")}
              </label>
              <input
                id="reason"
                className={ui.input}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <div>
                <button
                  type="button"
                  className={ui.button}
                  disabled={busy}
                  onClick={newVersion}
                >
                  {t("versions.create")}
                </button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function ProtocolForm({
  p,
  fields,
  onSave,
  disabled,
  t,
  id,
}: {
  p: Full;
  fields: FieldDef[];
  onSave: (body: Record<string, unknown>) => Promise<void>;
  disabled: boolean;
  t: (key: string) => string;
  id: string;
}) {
  const [form, setForm] = useState<Record<string, string | boolean>>(() =>
    Object.fromEntries(
      fields.map((f) => [
        f.name,
        valueOf(p as unknown as Record<string, unknown>, f),
      ]),
    ),
  );
  const [busy, setBusy] = useState(false);
  return (
    <form
      className={`${ui.card} flex flex-col gap-3`}
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        await onSave(toBody(form, fields));
        setBusy(false);
      }}
    >
      <Fields
        id={id}
        fields={fields}
        form={form}
        onChange={(n, v) => setForm((f) => ({ ...f, [n]: v }))}
        disabled={disabled}
        t={t}
      />
      {!disabled ? (
        <div>
          <button type="submit" className={ui.primary} disabled={busy}>
            {t("save")}
          </button>
        </div>
      ) : null}
    </form>
  );
}

function SectionList({
  section,
  p,
  base,
  disabled,
  onChanged,
  onError,
  t,
}: {
  section: Section;
  p: Full;
  base: string;
  disabled: boolean;
  onChanged: () => Promise<void>;
  onError: (m: string | null) => void;
  t: ReturnType<typeof useTranslations<"Handover">>;
}) {
  const items = p[section];
  const [editing, setEditing] = useState<Item | "new" | null>(null);
  const [contactQuery, setContactQuery] = useState("");
  const [contacts, setContacts] = useState<
    { id: string; display_name: string }[]
  >([]);
  const fields = FIELDS[section];
  const tRole = (r: string) => (r ? t(`roles.${r}`) : "");

  async function searchContacts() {
    const res = await bff<
      | { items?: { id: string; display_name: string }[] }
      | { id: string; display_name: string }[]
    >(`/api/bff/contacts?q=${encodeURIComponent(contactQuery)}&page_size=10`);
    if (res.ok)
      setContacts(Array.isArray(res.data) ? res.data : (res.data.items ?? []));
  }

  async function addFromContact(contactId: string) {
    const res = await bff(`${base}/participants`, {
      method: "POST",
      body: JSON.stringify({ contact_id: contactId, role: "other" }),
    });
    if (res.ok) {
      setContacts([]);
      setContactQuery("");
      await onChanged();
    } else onError(res.message);
  }

  async function remove(item: Item) {
    if (!window.confirm(t("confirmDelete"))) return;
    const res = await bff(`${base}/${section}/${item.id}`, {
      method: "DELETE",
    });
    if (res.ok) await onChanged();
    else onError(res.message);
  }

  return (
    <div className="flex flex-col gap-3" data-testid={`section-${section}`}>
      {section === "participants" && !disabled ? (
        <div className={`${ui.card} flex flex-col gap-2`}>
          <label htmlFor="contact-search" className={ui.label}>
            {t("participants.fromContact")}
          </label>
          <div className="flex gap-2">
            <input
              id="contact-search"
              className={ui.input}
              value={contactQuery}
              onChange={(e) => setContactQuery(e.target.value)}
              placeholder={t("participants.searchPlaceholder")}
            />
            <button
              type="button"
              className={ui.button}
              onClick={searchContacts}
              disabled={contactQuery.length < 2}
            >
              {t("participants.search")}
            </button>
          </div>
          {contacts.length ? (
            <ul className="flex flex-wrap gap-2">
              {contacts.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    className={ui.buttonSm}
                    onClick={() => addFromContact(c.id)}
                  >
                    + {c.display_name}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {items.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : null}
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <li key={item.id} className={`${ui.card} flex flex-col gap-2`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium">
                {itemTitle(section, item, tRole)}
              </span>
              {!disabled ? (
                <span className="flex gap-1">
                  <button
                    type="button"
                    className={ui.buttonSm}
                    onClick={() =>
                      setEditing(
                        editing && editing !== "new" && editing.id === item.id
                          ? null
                          : item,
                      )
                    }
                  >
                    {t("edit")}
                  </button>
                  <button
                    type="button"
                    className={ui.buttonSm}
                    onClick={() => remove(item)}
                  >
                    {t("delete")}
                  </button>
                </span>
              ) : null}
            </div>
            {section === "participants" && item.contact_id ? (
              <PortalAccessBox
                base={base}
                item={item}
                disabled={disabled}
                onChanged={onChanged}
                onError={onError}
                t={t}
              />
            ) : null}
            {editing && editing !== "new" && editing.id === item.id ? (
              <ItemForm
                section={section}
                base={base}
                item={item}
                rooms={p.rooms}
                fields={fields}
                onDone={async () => {
                  setEditing(null);
                  await onChanged();
                }}
                onError={onError}
                t={t}
              />
            ) : null}
            {PHOTO_SECTIONS.includes(section) ? (
              <Photos
                base={base}
                section={section}
                itemId={item.id}
                docs={p.documents.filter((d) => d.item_id === item.id)}
                disabled={disabled}
                onChanged={onChanged}
                onError={onError}
                t={t}
              />
            ) : null}
          </li>
        ))}
      </ul>
      {!disabled ? (
        editing === "new" ? (
          <div className={ui.card}>
            <ItemForm
              section={section}
              base={base}
              item={null}
              rooms={p.rooms}
              fields={fields}
              onDone={async () => {
                setEditing(null);
                await onChanged();
              }}
              onError={onError}
              t={t}
            />
          </div>
        ) : (
          <div>
            <button
              type="button"
              className={ui.primary}
              onClick={() => setEditing("new")}
            >
              {t(`add.${section}`)}
            </button>
          </div>
        )
      ) : null}
    </div>
  );
}

function ItemForm({
  section,
  base,
  item,
  rooms,
  fields,
  onDone,
  onError,
  t,
}: {
  section: Section;
  base: string;
  item: Item | null;
  rooms: Item[];
  fields: FieldDef[];
  onDone: () => Promise<void>;
  onError: (m: string | null) => void;
  t: (key: string) => string;
}) {
  const [form, setForm] = useState<Record<string, string | boolean>>(() =>
    Object.fromEntries(
      fields.map((f) => [
        f.name,
        item ? valueOf(item, f) : f.type === "checkbox" ? false : "",
      ]),
    ),
  );
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        onError(null);
        const res = await bff(
          item ? `${base}/${section}/${item.id}` : `${base}/${section}`,
          {
            method: item ? "PATCH" : "POST",
            body: JSON.stringify(toBody(form, fields)),
          },
        );
        setBusy(false);
        if (res.ok) await onDone();
        else onError(res.message);
      }}
    >
      <Fields
        id={item ? item.id : `new-${section}`}
        fields={fields}
        form={form}
        onChange={(n, v) => setForm((f) => ({ ...f, [n]: v }))}
        disabled={false}
        section={section}
        rooms={rooms}
        t={t}
      />
      <div className="flex gap-2">
        <button type="submit" className={ui.primary} disabled={busy}>
          {t("save")}
        </button>
        <button type="button" className={ui.button} onClick={onDone}>
          {t("cancel")}
        </button>
      </div>
    </form>
  );
}

function Photos({
  base,
  section,
  itemId,
  docs,
  disabled,
  onChanged,
  onError,
  t,
}: {
  base: string;
  section: Section;
  itemId: string;
  docs: Doc[];
  disabled: boolean;
  onChanged: () => Promise<void>;
  onError: (m: string | null) => void;
  t: (key: string) => string;
}) {
  const [busy, setBusy] = useState(false);
  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    for (const file of Array.from(files)) {
      const data = new FormData();
      data.append("file", file);
      data.append("section", section);
      data.append("item_id", itemId);
      const res = await bff(`${base}/documents`, {
        method: "POST",
        body: data,
      });
      if (!res.ok) onError(res.message);
    }
    setBusy(false);
    await onChanged();
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      {docs.map((d) => (
        <span key={d.id} className="relative">
          <a
            href={`/api/handover-files/documents/${d.id}/content`}
            target="_blank"
            rel="noopener"
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- protected same-origin blob, no optimizer */}
            <img
              src={`/api/handover-files/documents/${d.id}/content`}
              alt={d.title}
              className="h-16 w-16 rounded border border-border object-cover"
            />
          </a>
          {!disabled ? (
            <button
              type="button"
              className="absolute -right-1 -top-1 rounded-full bg-bg px-1 text-xs shadow-card"
              aria-label={t("photos.remove")}
              onClick={async () => {
                const res = await bff(`${base}/documents/${d.id}`, {
                  method: "DELETE",
                });
                if (res.ok) await onChanged();
                else onError(res.message);
              }}
            >
              ×
            </button>
          ) : null}
        </span>
      ))}
      {!disabled ? (
        <label className={`${ui.buttonSm} cursor-pointer`}>
          {busy ? t("photos.uploading") : t("photos.add")}
          <input
            type="file"
            accept="image/jpeg,image/png"
            capture="environment"
            multiple
            className="sr-only"
            onChange={(e) => upload(e.target.files)}
            disabled={busy}
          />
        </label>
      ) : null}
    </div>
  );
}

function Attachments({
  p,
  base,
  disabled,
  onChanged,
  onError,
  t,
}: {
  p: Full;
  base: string;
  disabled: boolean;
  onChanged: () => Promise<void>;
  onError: (m: string | null) => void;
  t: (key: string) => string;
}) {
  const [busy, setBusy] = useState(false);
  const docs = p.documents.filter(
    (d) => d.kind === "attachment" || (d.kind === "photo" && !d.item_id),
  );
  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    for (const file of Array.from(files)) {
      const data = new FormData();
      data.append("file", file);
      const res = await bff(`${base}/documents`, {
        method: "POST",
        body: data,
      });
      if (!res.ok) onError(res.message);
    }
    setBusy(false);
    await onChanged();
  }
  return (
    <div className={`${ui.card} flex flex-col gap-3`}>
      {docs.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : null}
      <ul className="flex flex-col gap-1 text-sm">
        {docs.map((d) => (
          <li key={d.id} className="flex items-center justify-between gap-2">
            <a
              href={`/api/handover-files/documents/${d.id}/content`}
              target="_blank"
              rel="noopener"
              className="hover:underline"
            >
              {d.filename}
            </a>
            <span className="text-muted">{Math.round(d.size / 1024)} KB</span>
            {!disabled ? (
              <button
                type="button"
                className={ui.buttonSm}
                onClick={async () => {
                  const res = await bff(`${base}/documents/${d.id}`, {
                    method: "DELETE",
                  });
                  if (res.ok) await onChanged();
                  else onError(res.message);
                }}
              >
                {t("delete")}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      {!disabled ? (
        <label className={`${ui.button} w-fit cursor-pointer`}>
          {busy ? t("photos.uploading") : t("attachments.add")}
          <input
            type="file"
            accept="image/jpeg,image/png,application/pdf"
            multiple
            className="sr-only"
            onChange={(e) => upload(e.target.files)}
            disabled={busy}
          />
        </label>
      ) : null}
    </div>
  );
}
