"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { downscaleImage, isImageAccepted } from "@/lib/image-downscale";
import { ui } from "@/lib/ui";

import { ConfirmSheet } from "./ConfirmSheet";
import { PhotoLightbox, type LightboxPhoto } from "./PhotoLightbox";
import { PhotoPicker, type PhotoJob } from "./PhotoPicker";
import { SignaturePad } from "./SignaturePad";
import {
  FIELDS,
  PHOTO_SECTIONS,
  SECTIONS,
  type Doc,
  type FieldDef,
  type Full,
  type Item,
  type Section,
  itemTitle,
} from "./types";

type Tab = "object" | Section | "deposit" | "signatures" | "summary";

const TABS: Tab[] = ["object", "participants", "deposit", ...SECTIONS.filter((s) => s !== "participants"), "signatures", "summary"];

/** Days the finished PDF stays available in the portal (mirrors READ_DAYS of the API). */
export const READ_DAYS = 14;

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
  { name: "deposit_separate_statement", type: "checkbox" },
  { name: "deposit_note", type: "textarea", wide: true },
];

type T = (key: string, values?: Record<string, string | number>) => string;

/** Pending confirmation shown in the ConfirmSheet (M31 WP5) instead of window.confirm. */
type Confirm = { title: string; text?: string; confirmLabel: string; danger?: boolean; action: () => Promise<void> | void };

/** Uploads the files of one entry one after the other (capture first: the entry is posted
 *  before its photos), reporting the status per file. Returns the failed files for a retry. */
export async function uploadPhotos(
  base: string,
  section: Section,
  itemId: string,
  files: File[],
  setJobs: (update: (jobs: PhotoJob[]) => PhotoJob[]) => void,
  unsupported: string,
): Promise<File[]> {
  const failed: File[] = [];
  for (const file of files) {
    const key = `${file.name}-${file.size}-${file.lastModified}`;
    const patch = (status: PhotoJob["status"], message?: string) =>
      setJobs((jobs) => jobs.map((j) => (j.key === key ? { ...j, status, message } : j)));
    if (!isImageAccepted(file.type) && file.type !== "") {
      patch("failed", unsupported);
      continue;
    }
    patch("uploading");
    const data = new FormData();
    data.append("file", await downscaleImage(file));
    data.append("section", section);
    data.append("item_id", itemId);
    const res = await bff(`${base}/documents`, { method: "POST", body: data });
    if (res.ok) patch("done");
    else {
      patch("failed", res.message);
      failed.push(file);
    }
  }
  return failed;
}

export function jobsOf(files: File[]): PhotoJob[] {
  return files.map((f) => ({ key: `${f.name}-${f.size}-${f.lastModified}`, name: f.name, status: "queued" }));
}

function valueOf(item: Record<string, unknown>, field: FieldDef): string | boolean {
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

function toBody(form: Record<string, string | boolean>, fields: FieldDef[]): Record<string, unknown> {
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

function initialForm(item: Record<string, unknown> | null, fields: FieldDef[]) {
  return Object.fromEntries(
    fields.map((f) => [f.name, item ? valueOf(item, f) : f.type === "checkbox" ? false : ""]),
  ) as Record<string, string | boolean>;
}

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
  t: T;
}) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {fields.map((f) => {
        const key = `${id}-${f.name}`;
        const label = t(`fields.${f.name}`);
        const value = form[f.name];
        if (f.type === "checkbox") {
          return (
            <label key={key} className="flex items-center gap-2 self-end text-sm">
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
              ? (rooms ?? []).map((r) => ({ value: r.id, label: String(r.name || r.room_type || "Raum") }))
              : (f.options ?? []).map((o) => ({ value: o, label: t(`options.${section ?? "x"}.${f.name}.${o}`) }));
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
                <option value=""> </option>
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
              type={f.type === "number" ? "number" : f.type === "date" ? "date" : f.type === "time" ? "time" : "text"}
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

/** Portal editor of one handover protocol (M30 Stufe 3): the participant fills in the
 *  sections, adds photos, signs and completes; afterwards the protocol is read only. */
export function HandoverFill({ initial }: { initial: Full }) {
  const t = useTranslations("Handover") as unknown as T;
  const [p, setP] = useState<Full>(initial);
  const [tab, setTab] = useState<Tab>(
    TABS.includes(initial.current_step as Tab) ? (initial.current_step as Tab) : "object",
  );
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showHints, setShowHints] = useState(false);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [lightbox, setLightbox] = useState<number | null>(null);
  const editable = p.access.right === "edit" && !p.locked;
  const base = `/api/bff/portal/handover/${p.id}`;
  const files = `/api/portal-files/portal/handover/${p.id}`;
  const gallery: LightboxPhoto[] = p.documents
    .filter((d) => d.kind === "photo")
    .map((d) => ({ id: d.id, src: `${files}/documents/${d.id}/content`, title: d.title }));

  async function reload() {
    const res = await bff<Full>(base);
    if (res.ok) setP(res.data);
  }

  async function patchProtocol(body: Record<string, unknown>) {
    setError(null);
    const res = await bff(base, { method: "PATCH", body: JSON.stringify(body) });
    if (!res.ok) setError(res.message);
    else {
      setInfo(t("saved"));
      await reload();
    }
  }

  function switchTab(next: Tab) {
    setTab(next);
    setInfo(null);
    if (editable) void bff(base, { method: "PATCH", body: JSON.stringify({ current_step: next }) });
  }

  async function doComplete(force: boolean) {
    setBusy(true);
    setError(null);
    const res = await bff<Full>(`${base}/complete`, { method: "POST", body: JSON.stringify({ force }) });
    setBusy(false);
    if (res.ok) {
      setP(res.data);
      setTab("summary");
      setShowHints(false);
    } else setError(res.message);
  }

  function complete(force: boolean) {
    if (!force && p.hints.length > 0) {
      setShowHints(true);
      return;
    }
    setConfirm({
      title: t(force ? "complete.force" : "complete.action"),
      text: t(force ? "complete.confirmForce" : "complete.confirm"),
      confirmLabel: t("confirm.yes"),
      danger: force,
      action: () => doComplete(force),
    });
  }

  const onError = (m: string | null) => setError(m);
  const ask = (c: Confirm) => setConfirm(c);
  const openPhoto = (id: string) => setLightbox(gallery.findIndex((g) => g.id === id));

  return (
    <div className="flex flex-col gap-4" data-testid="handover-fill">
      {!editable ? <p className={ui.notice}>{t("locked")}</p> : <p className="text-sm text-muted">{t("intro")}</p>}
      <nav className={ui.tabBar} aria-label={t("sections")}>
        {TABS.map((name) => (
          <button
            key={name}
            type="button"
            className={tab === name ? ui.tabActive : ui.tab}
            aria-current={tab === name ? "page" : undefined}
            onClick={() => switchTab(name)}
          >
            {t(`tabs.${name}`)}
          </button>
        ))}
      </nav>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {info ? (
        <p role="status" className={ui.success}>
          {info}
        </p>
      ) : null}

      {tab === "object" ? (
        <ProtocolForm id="object" fields={OBJECT_FIELDS} p={p} disabled={!editable} onSave={patchProtocol} t={t} />
      ) : null}
      {tab === "deposit" ? (
        <div className="flex flex-col gap-3">
          <p className={ui.notice}>{t("deposit.notice")}</p>
          <ProtocolForm id="deposit" fields={DEPOSIT_FIELDS} p={p} disabled={!editable} onSave={patchProtocol} t={t} />
        </div>
      ) : null}
      {SECTIONS.includes(tab as Section) ? (
        <SectionList
          section={tab as Section}
          p={p}
          base={base}
          files={files}
          disabled={!editable}
          onChanged={reload}
          onError={onError}
          ask={ask}
          openPhoto={openPhoto}
          t={t}
        />
      ) : null}
      {tab === "signatures" ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted">{t("signature.consent")}</p>
          {p.signatures.length === 0 ? <p className="text-sm text-muted">{t("signature.none")}</p> : null}
          <ul className="flex flex-col gap-2">
            {p.signatures.map((s) => (
              <li key={s.id} className={`${ui.card} flex flex-wrap items-center gap-3`}>
                {/* eslint-disable-next-line @next/next/no-img-element -- protected same-origin blob, no optimizer */}
                <img
                  src={`${files}/documents/${s.document_id}/content`}
                  alt={s.signer_name ?? t("signature.noName")}
                  className="h-12 w-auto rounded border border-border bg-paper"
                />
                <span className="text-sm">
                  {s.signer_name ?? t("signature.noName")}
                  {s.signer_role ? `, ${t(`roles.${s.signer_role}`)}` : ""}
                </span>
                <span className="text-xs text-subtle">{s.sha256.slice(0, 12)}</span>
                {editable ? (
                  <button
                    type="button"
                    className={ui.buttonSm}
                    onClick={() =>
                      ask({
                        title: t("delete"),
                        text: t("signature.confirmDelete"),
                        confirmLabel: t("confirm.deleteYes"),
                        danger: true,
                        action: async () => {
                          const res = await bff(`${base}/signatures/${s.id}`, { method: "DELETE" });
                          if (res.ok) await reload();
                          else setError(res.message);
                        },
                      })
                    }
                  >
                    {t("delete")}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
          {editable ? (
            <SignaturePad base={base} kind={p.kind} participants={p.participants} signatures={p.signatures} disabled={busy} onSaved={reload} />
          ) : null}
        </div>
      ) : null}
      {tab === "summary" ? (
        <div className="flex flex-col gap-4">
          <dl className={`${ui.card} grid gap-2 text-sm sm:grid-cols-2`}>
            {(["rooms", "meters", "defects", "keys", "items", "notes"] as const).map((s) => (
              <div key={s} className="flex justify-between gap-2">
                <dt className="text-muted">{t(`summary.${s}`)}</dt>
                <dd>{p[s].length}</dd>
              </div>
            ))}
            <div className="flex justify-between gap-2">
              <dt className="text-muted">{t("summary.photos")}</dt>
              <dd>{p.documents.filter((d) => d.kind === "photo").length}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-muted">{t("summary.signatures")}</dt>
              <dd>{p.signatures.length}</dd>
            </div>
          </dl>
          {p.hints.length > 0 && (showHints || !editable) ? (
            <div className={ui.notice} data-testid="hints">
              <p className="font-medium">{t("hints.title")}</p>
              <ul className="list-disc pl-5">
                {p.hints.map((hint) => (
                  <li key={hint}>{hint}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className={editable ? ui.bottomBar : "flex flex-wrap gap-2"}>
            {/* Same tab on purpose: an installed portal (iOS standalone) loses the session in an
                external tab; Zurück leads back to the protocol (M31 WP5). */}
            <a href={`${files}/pdf`} className={ui.button}>
              {p.finalized ? t("pdfFinal") : t("pdfDraft")}
            </a>
            {editable ? (
              <>
                <button type="button" className={ui.primary} disabled={busy} onClick={() => complete(false)}>
                  {t("complete.action")}
                </button>
                {showHints ? (
                  <button type="button" className={ui.danger} disabled={busy} onClick={() => complete(true)}>
                    {t("complete.force")}
                  </button>
                ) : null}
              </>
            ) : null}
          </div>
          {editable ? <p className={ui.help}>{t("complete.help", { days: READ_DAYS })}</p> : null}
          {p.access.right === "read" && p.access.valid_to ? (
            <p className={ui.help}>{t("access.read", { date: p.access.valid_to.split("-").reverse().join(".") })}</p>
          ) : null}
        </div>
      ) : null}
      <ConfirmSheet
        open={confirm !== null}
        title={confirm?.title ?? ""}
        text={confirm?.text}
        confirmLabel={confirm?.confirmLabel ?? ""}
        cancelLabel={t("confirm.no")}
        danger={confirm?.danger}
        busy={busy}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          const c = confirm;
          setConfirm(null);
          if (c) await c.action();
        }}
      />
      {lightbox != null && lightbox >= 0 ? (
        <PhotoLightbox photos={gallery} index={lightbox} onClose={() => setLightbox(null)} onIndex={setLightbox} />
      ) : null}
    </div>
  );
}

function ProtocolForm({
  id,
  fields,
  p,
  disabled,
  onSave,
  t,
}: {
  id: string;
  fields: FieldDef[];
  p: Full;
  disabled: boolean;
  onSave: (body: Record<string, unknown>) => Promise<void>;
  t: T;
}) {
  const [form, setForm] = useState(() => initialForm(p as unknown as Record<string, unknown>, fields));
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        await onSave(toBody(form, fields));
        setBusy(false);
      }}
    >
      <Fields id={id} fields={fields} form={form} onChange={(n, v) => setForm((f) => ({ ...f, [n]: v }))} disabled={disabled} t={t} />
      {!disabled ? (
        <div className={ui.bottomBar}>
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
  files,
  disabled,
  onChanged,
  onError,
  ask,
  openPhoto,
  t,
}: {
  section: Section;
  p: Full;
  base: string;
  files: string;
  disabled: boolean;
  onChanged: () => Promise<void>;
  onError: (m: string | null) => void;
  ask: (c: Confirm) => void;
  openPhoto: (id: string) => void;
  t: T;
}) {
  const items = p[section];
  const [editing, setEditing] = useState<Item | "new" | null>(null);
  const fields = FIELDS[section];
  const tRole = (r: string) => (r ? t(`roles.${r}`) : "");

  function remove(item: Item) {
    ask({
      title: t("delete"),
      text: t("confirmDelete"),
      confirmLabel: t("confirm.deleteYes"),
      danger: true,
      action: async () => {
        const res = await bff(`${base}/${section}/${item.id}`, { method: "DELETE" });
        if (res.ok) await onChanged();
        else onError(res.message);
      },
    });
  }

  return (
    <div className="flex flex-col gap-3" data-testid={`section-${section}`}>
      {items.length === 0 ? <p className="text-sm text-muted">{t("empty")}</p> : null}
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <li key={item.id} className={`${ui.card} flex flex-col gap-2`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium">{itemTitle(section, item, tRole)}</span>
              {!disabled ? (
                <span className="flex gap-1">
                  <button
                    type="button"
                    className={ui.buttonSm}
                    onClick={() => setEditing(editing && editing !== "new" && editing.id === item.id ? null : item)}
                  >
                    {t("edit")}
                  </button>
                  <button type="button" className={ui.buttonSm} onClick={() => remove(item)}>
                    {t("delete")}
                  </button>
                </span>
              ) : null}
            </div>
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
                files={files}
                section={section}
                itemId={item.id}
                version={p.version}
                docs={p.documents.filter((d) => d.item_id === item.id)}
                disabled={disabled}
                onChanged={onChanged}
                onError={onError}
                ask={ask}
                openPhoto={openPhoto}
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
              withPhotos={PHOTO_SECTIONS.includes(section)}
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
            <button type="button" className={ui.primary} onClick={() => setEditing("new")}>
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
  withPhotos,
  onDone,
  onError,
  t,
}: {
  section: Section;
  base: string;
  item: Item | null;
  rooms: Item[];
  fields: FieldDef[];
  /** Capture first (M31 WP5): a new meter, room, defect or item takes its photo in the same
   *  step; the entry is posted first, then the photos are uploaded one by one with a status. */
  withPhotos?: boolean;
  onDone: () => Promise<void>;
  onError: (m: string | null) => void;
  t: T;
}) {
  const [form, setForm] = useState(() => initialForm(item, fields));
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<File[]>([]);
  const [jobs, setJobs] = useState<PhotoJob[]>([]);
  // Set once the new entry is posted: a second Save (after a failed upload) patches it
  // instead of creating a duplicate.
  const [createdId, setCreatedId] = useState<string | null>(null);
  const targetId = item ? item.id : createdId;

  async function uploadPending(id: string, files: File[]): Promise<boolean> {
    setJobs((jobs) => [...jobs.filter((j) => j.status !== "failed" || !files.some((f) => `${f.name}-${f.size}-${f.lastModified}` === j.key)), ...jobsOf(files)]);
    const failed = await uploadPhotos(base, section, id, files, setJobs, t("photos.unsupported"));
    setPending(failed);
    return failed.length === 0;
  }

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        onError(null);
        const res = await bff<Item>(targetId ? `${base}/${section}/${targetId}` : `${base}/${section}`, {
          method: targetId ? "PATCH" : "POST",
          body: JSON.stringify(toBody(form, fields)),
        });
        if (!res.ok) {
          setBusy(false);
          onError(res.message);
          return;
        }
        const id = targetId ?? res.data.id;
        if (!item) setCreatedId(id);
        // Capture first: the entry exists before its photos are uploaded one by one.
        const complete = pending.length === 0 || (id ? await uploadPending(id, pending) : false);
        setBusy(false);
        if (complete) await onDone();
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
      {withPhotos ? (
        <div className="flex flex-col gap-1">
          <span className={ui.label}>{t("photos.withEntry")}</span>
          <PhotoPicker
            onFiles={(list) => setPending((files) => [...files, ...list])}
            jobs={jobs.length > 0 ? jobs : jobsOf(pending)}
            onRetry={(job) => {
              const file = pending.find((f) => `${f.name}-${f.size}-${f.lastModified}` === job.key);
              if (file && targetId) {
                void uploadPending(targetId, [file]).then(async (ok) => {
                  if (ok) await onDone();
                });
              }
            }}
            disabled={busy}
          />
        </div>
      ) : null}
      <div className={ui.bottomBar}>
        <button type="submit" className={ui.primary} disabled={busy}>
          {t("save")}
        </button>
        <button type="button" className={ui.button} onClick={onDone} disabled={busy}>
          {t("cancel")}
        </button>
      </div>
    </form>
  );
}

function Photos({
  base,
  files,
  section,
  itemId,
  version,
  docs,
  disabled,
  onChanged,
  onError,
  ask,
  openPhoto,
  t,
}: {
  base: string;
  files: string;
  section: Section;
  itemId: string;
  version: number;
  docs: Doc[];
  disabled: boolean;
  onChanged: () => Promise<void>;
  onError: (m: string | null) => void;
  ask: (c: Confirm) => void;
  openPhoto: (id: string) => void;
  t: T;
}) {
  const [jobs, setJobs] = useState<PhotoJob[]>([]);
  const [failed, setFailed] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  async function upload(list: File[]) {
    if (!list.length) return;
    setBusy(true);
    setJobs((jobs) => [...jobs.filter((j) => j.status !== "done"), ...jobsOf(list)]);
    const rest = await uploadPhotos(base, section, itemId, list, setJobs, t("photos.unsupported"));
    setFailed(rest);
    setBusy(false);
    await onChanged();
    setJobs((jobs) => jobs.filter((j) => j.status === "failed"));
  }
  return (
    <div className="flex flex-col gap-2">
      {docs.length > 0 ? (
        <ul className="flex flex-wrap items-center gap-2">
          {docs.map((d) => (
            <li key={d.id} className="relative">
              <button
                type="button"
                className="block rounded-md focus:outline-none focus-visible:ring-2 focus-visible:ring-focus"
                aria-label={t("photos.open", { title: d.title })}
                onClick={() => openPhoto(d.id)}
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- protected same-origin blob, no optimizer */}
                <img src={`${files}/documents/${d.id}/content`} alt={d.title} className="h-20 w-20 rounded-md border border-border object-cover" />
              </button>
              {!disabled ? (
                <button
                  type="button"
                  className="absolute -right-1 -top-1 flex h-7 w-7 items-center justify-center rounded-full border border-border bg-surface text-xs shadow-card"
                  aria-label={t("photos.remove")}
                  onClick={() =>
                    ask({
                      title: t("photos.remove"),
                      // Version 1 has no earlier version keeping the file: the file is deleted;
                      // a later version only drops the link and the earlier version keeps it.
                      text: t(version > 1 ? "photos.confirmRemoveKept" : "photos.confirmRemove"),
                      confirmLabel: t("confirm.deleteYes"),
                      danger: true,
                      action: async () => {
                        const res = await bff(`${base}/documents/${d.id}`, { method: "DELETE" });
                        if (res.ok) await onChanged();
                        else onError(res.message);
                      },
                    })
                  }
                >
                  ×
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {!disabled ? (
        <PhotoPicker
          compact
          onFiles={(list) => void upload(list)}
          jobs={jobs}
          onRetry={(job) => {
            const file = failed.find((f) => `${f.name}-${f.size}-${f.lastModified}` === job.key);
            if (file) void upload([file]);
          }}
          disabled={busy}
        />
      ) : null}
    </div>
  );
}
