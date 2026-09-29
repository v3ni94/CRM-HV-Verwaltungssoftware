"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { useConfirm } from "@/components/ui/ConfirmSheet";
import { Sheet } from "@/components/ui/Sheet";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { downscale } from "@/lib/image-downscale";
import { ui } from "@/lib/ui";
import { useOnline } from "@/lib/useOnline";

import { HandoverAppointmentButton } from "./HandoverAppointmentButton";
import { HandoverContractLink } from "./HandoverContractLink";
import { HandoverMeterTransfer } from "./HandoverMeterTransfer";
import { HandoverSummary } from "./HandoverSummary";
import { HelperAccessSection } from "./HelperAccessSection";
import { PhotoPicker } from "./PhotoPicker";
import { PhotoStrip } from "./PhotoStrip";
import { PortalAccessBox } from "./PortalAccessBox";
import { SignatureSheet } from "./SignatureSheet";
import { participantName } from "./SignaturePad";
import { STEPS, type Step, stepCount, stepState } from "./steps";
import {
  FIELDS,
  INPUT_HINTS,
  PHOTO_SECTIONS,
  SECTIONS,
  itemTitle,
  type Doc,
  type FieldDef,
  type Full,
  type Item,
  type Section,
} from "./types";
import { DirtyGuardContext, useDirtyGuard, useDirtyGuardState } from "./useDirtyGuard";

type Tab = Step;

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
  { name: "external_object_number", type: "text" },
  { name: "owner_name", type: "text" },
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

/** A save failed because the API was unreachable or broke (status 0 or 5xx): the value stays
 *  in the form and the button turns into "Erneut senden". */
function isRetryable(status: number): boolean {
  return status === 0 || status >= 500;
}

/** Field grid used for the protocol, the deposit, the internal section and every sub record.
 *  One column on phones, two from `sm`, three from `lg`; the input hints choose the keyboard. */
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
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {fields.map((f) => {
        const key = `${id}-${f.name}`;
        const label = t(`fields.${f.name}`);
        const value = form[f.name];
        if (f.type === "checkbox") {
          return (
            <label key={key} className="flex min-h-11 items-center gap-2 self-end text-sm">
              <input type="checkbox" className="h-5 w-5" checked={Boolean(value)} onChange={(e) => onChange(f.name, e.target.checked)} disabled={disabled} />
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
              <select id={key} className={ui.input} value={String(value ?? "")} onChange={(e) => onChange(f.name, e.target.value)} disabled={disabled}>
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
            <div key={key} className={f.wide ? "sm:col-span-2 lg:col-span-3" : ""}>
              <label htmlFor={key} className={ui.label}>
                {label}
              </label>
              <textarea id={key} className={ui.input} rows={3} value={String(value ?? "")} onChange={(e) => onChange(f.name, e.target.value)} disabled={disabled} enterKeyHint="done" />
            </div>
          );
        }
        const hints = INPUT_HINTS[f.name] ?? {};
        return (
          <div key={key}>
            <label htmlFor={key} className={ui.label}>
              {label}
            </label>
            <input
              id={key}
              {...hints}
              type={f.type === "number" ? "number" : f.type === "date" ? "date" : f.type === "time" ? "time" : (hints.type ?? "text")}
              inputMode={f.type === "decimal" ? "decimal" : hints.inputMode}
              enterKeyHint="next"
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

function StatusDot({ state, t }: { state: "attention" | "filled" | "empty"; t: (key: string) => string }) {
  const color = state === "attention" ? "bg-warning-fg" : state === "filled" ? "bg-success-fg" : "bg-border";
  return (
    <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${color}`} data-state={state} data-testid="step-state" role="img" aria-label={t(`stepState.${state}`)} />
  );
}

/**
 * Übergabeprotokoll (M30): sections as steps, every save goes straight to the API, the
 * protocol is locked after completion and continues only as a new version. Locked protocols
 * render `HandoverSummary` from the page; this editor mounts only while the protocol is open.
 *
 * Merge pattern for a later autosave (operator question, not implemented): PATCH
 * /protocols/{id} returns only the protocol part (`_protocol_out`), never the sub records, so
 * a merge must be `setP(prev => ({...prev, ...data}))` and never `setP(data)`.
 *
 * M30-09: once a valid signature exists the content steps are read only until the action
 * "Änderung nach Unterschrift" records a reason (the API answers 409 otherwise).
 */
export function HandoverEditor({ initial }: { initial: Full }) {
  const t = useTranslations("Handover");
  const router = useRouter();
  const online = useOnline();
  const { guard } = useDirtyGuardState();
  const { confirm, confirmSheet } = useConfirm();
  const [p, setP] = useState<Full>(initial);
  const [tab, setTab] = useState<Tab>(initial.locked ? "summary" : STEPS.includes(initial.current_step as Tab) ? (initial.current_step as Tab) : "object");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showHints, setShowHints] = useState(false);
  const [reason, setReason] = useState("");
  const [moreOpen, setMoreOpen] = useState(false);
  const [changeOpen, setChangeOpen] = useState(false);
  const [changeReason, setChangeReason] = useState("");
  const [signFor, setSignFor] = useState<Item | null | undefined>(undefined);
  const navRef = useRef<HTMLElement>(null);
  const locked = p.locked;
  const contentLocked = Boolean(p.content_locked) && !locked;
  const base = `/api/bff/handover/protocols/${p.id}`;
  const stepIndex = STEPS.indexOf(tab);

  useEffect(() => {
    try {
      navRef.current?.querySelector<HTMLElement>('[aria-current="step"]')?.scrollIntoView({ inline: "center", block: "nearest" });
    } catch {
      /* scrollIntoView unavailable */
    }
  }, [tab]);

  async function reload() {
    const res = await bff<Full>(base);
    if (res.ok) {
      setP(res.data);
      guard.reset();
    }
  }

  async function patchProtocol(body: Record<string, unknown>): Promise<number> {
    setError(null);
    const res = await bff(base, { method: "PATCH", body: JSON.stringify(body) });
    if (!res.ok) {
      setError(res.message);
      return res.status;
    }
    setInfo(t("saved"));
    await reload();
    return res.status;
  }

  /** Step switch with the unsaved input question; the `current_step` PATCH is remembered
   *  server side and a failure is reported as a quiet info line. */
  async function switchTab(next: Tab) {
    if (next === tab) return;
    if (guard.isDirty()) {
      const ok = await confirm({
        title: t("unsavedConfirm.title"),
        text: t("unsavedConfirm.text"),
        confirmLabel: t("unsavedConfirm.discard"),
        cancelLabel: t("unsavedConfirm.stay"),
        danger: true,
      });
      if (!ok) return;
      guard.reset();
    }
    setTab(next);
    setInfo(null);
    if (!locked) {
      const res = await bff(base, { method: "PATCH", body: JSON.stringify({ current_step: next }) });
      if (!res.ok) setInfo(t("stepSaveFailed"));
    }
  }

  async function complete(force: boolean) {
    if (!force && p.hints.length > 0) {
      setShowHints(true);
      return;
    }
    const ok = await confirm({ title: t("complete.action"), text: t(force ? "complete.confirmForce" : "complete.confirm"), confirmLabel: t("complete.action") });
    if (!ok) return;
    setBusy(true);
    setError(null);
    const res = await bff<Full>(`${base}/complete`, { method: "POST", body: JSON.stringify({ force }) });
    setBusy(false);
    if (res.ok) {
      setP(res.data);
      setTab("summary");
      setShowHints(false);
      router.refresh();
    } else setError(res.message);
  }

  async function newVersion() {
    if (reason.trim().length < 3) {
      setError(t("versions.reasonRequired"));
      return;
    }
    setBusy(true);
    const res = await bff<Full>(`${base}/versions`, { method: "POST", body: JSON.stringify({ reason }) });
    setBusy(false);
    if (res.ok) router.push(`/makler/uebergabe/${res.data.id}`);
    else setError(res.message);
  }

  async function status(action: "cancel" | "archive" | "unarchive") {
    setMoreOpen(false);
    const ok = await confirm({ title: t(`status.${action}`), text: t(`status.confirm.${action}`), danger: action === "cancel" });
    if (!ok) return;
    const res = await bff(`${base}/status`, { method: "POST", body: JSON.stringify({ action }) });
    if (res.ok) {
      await reload();
      router.refresh();
    } else setError(res.message);
  }

  async function dispatch() {
    setBusy(true);
    const res = await bff<{ created: unknown[]; skipped: { reason: string }[] }>(`${base}/dispatches`, { method: "POST", body: JSON.stringify({ channel: "email" }) });
    setBusy(false);
    if (res.ok) {
      setInfo(t("dispatch.result", { created: res.data.created.length, skipped: res.data.skipped.length }));
      await reload();
    } else setError(res.message);
  }

  async function changeAfterSignature() {
    if (changeReason.trim().length < 3) {
      setError(t("changes.reasonRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    const res = await bff<Full>(`${base}/changes`, { method: "POST", body: JSON.stringify({ reason: changeReason.trim() }) });
    setBusy(false);
    if (res.ok) {
      setP(res.data);
      setChangeOpen(false);
      setChangeReason("");
      setInfo(t("changes.done"));
    } else setError(res.message);
  }

  const contentDisabled = locked || contentLocked;
  const sectionDisabled = (section: Section) => (section === "participants" ? locked : contentDisabled);
  const pdfHref = `/api/handover-files/handover/protocols/${p.id}/pdf`;
  const pdfLabel = p.finalized ? t("pdf.stored") : t("pdf.preview");

  const headerActions = (
    <>
      <a className={ui.button} href={pdfHref}>
        {pdfLabel}
      </a>
      <HandoverAppointmentButton protocolId={p.id} address={p.address || null} handoverDate={p.handover_date} objectLabel={p.object_label} unitLabel={p.unit_label || p.unit_number} participants={p.participants} />
      {!locked ? (
        <button type="button" className={ui.button} onClick={() => status("cancel")} disabled={busy}>
          {t("status.cancel")}
        </button>
      ) : null}
      {p.status !== "archived" && locked ? (
        <button type="button" className={ui.button} onClick={() => status("archive")} disabled={busy}>
          {t("status.archive")}
        </button>
      ) : null}
      {p.status === "archived" ? (
        <button type="button" className={ui.button} onClick={() => status("unarchive")} disabled={busy}>
          {t("status.unarchive")}
        </button>
      ) : null}
    </>
  );

  return (
    <DirtyGuardContext.Provider value={guard}>
      <div className="flex flex-col gap-4" data-testid="handover-editor">
        <div className="flex flex-wrap items-center gap-2">
          <span className={p.finalized ? ui.badgeSuccess : p.status === "cancelled" ? ui.badgeDanger : ui.badgeGold}>{t(`statusLabel.${p.status}`)}</span>
          {p.version > 1 ? <span className={ui.badge}>{t("versions.label", { version: p.version })}</span> : null}
          <div className="hidden flex-wrap items-center gap-2 sm:flex">{headerActions}</div>
          <button type="button" className={`${ui.button} ml-auto sm:hidden`} onClick={() => setMoreOpen(true)} aria-label={t("more.open")} data-testid="more-actions">
            {t("more.title")}
          </button>
        </div>
        <Sheet open={moreOpen} onClose={() => setMoreOpen(false)} title={t("more.title")} size="sm" testId="more-sheet">
          <div className="flex flex-col gap-2 [&>*]:w-full [&>*]:justify-center">{headerActions}</div>
        </Sheet>
        {locked ? <p className={ui.notice}>{p.status === "cancelled" ? t("lockedCancelled") : t("locked")}</p> : null}
        {contentLocked ? (
          <div className={`${ui.warning} flex flex-col gap-2`} data-testid="content-locked">
            <p>{t("changes.lockedNotice")}</p>
            <div>
              <button type="button" className={ui.button} onClick={() => setChangeOpen(true)} disabled={busy}>
                {t("changes.action")}
              </button>
            </div>
          </div>
        ) : null}
        <Sheet
          open={changeOpen}
          onClose={() => setChangeOpen(false)}
          title={t("changes.action")}
          size="md"
          testId="change-sheet"
          footer={
            <div className={ui.formActions}>
              <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={() => setChangeOpen(false)}>
                {t("cancel")}
              </button>
              <button type="button" className={`${ui.primary} ${ui.actionFull}`} onClick={changeAfterSignature} disabled={busy} data-testid="change-confirm">
                {t("changes.confirm")}
              </button>
            </div>
          }
        >
          <div className="flex flex-col gap-3">
            <p className="text-sm text-muted">{t("changes.help")}</p>
            <label htmlFor="change-reason" className={ui.label}>
              {t("changes.reason")}
            </label>
            <textarea id="change-reason" className={ui.input} rows={3} value={changeReason} onChange={(e) => setChangeReason(e.target.value)} required />
          </div>
        </Sheet>
        {!online ? (
          <p role="status" className={ui.warning} data-testid="offline-notice">
            {t("offlineNotice")}
          </p>
        ) : null}
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {info ? <p className={ui.success}>{info}</p> : null}

        <nav ref={navRef} className={ui.tabBar} aria-label={t("steps")}>
          {STEPS.map((x) => {
            const count = stepCount(x, p);
            return (
              <button key={x} type="button" className={x === tab ? ui.tabActive : ui.tab} onClick={() => switchTab(x)} aria-current={x === tab ? "step" : undefined} data-testid={`step-${x}`}>
                <StatusDot state={stepState(x, p)} t={t} />
                {t(`tabs.${x}`)}
                {count !== null ? <span className={`${ui.num} text-xs text-muted`}>{count}</span> : null}
              </button>
            );
          })}
        </nav>
        <p className="sr-only" aria-live="polite">
          {t("stepProgress", { current: stepIndex + 1, total: STEPS.length })}
        </p>

        {tab === "object" ? (
          <>
            <ProtocolForm p={p} fields={OBJECT_FIELDS} onSave={patchProtocol} disabled={contentDisabled} t={t} id="object" />
            <HandoverContractLink base={base} unitId={p.unit_id} contract={p.contract} disabled={contentDisabled} onChanged={reload} onError={setError} />
          </>
        ) : null}
        {tab === "meters" ? <HandoverMeterTransfer base={base} meters={p.meters} hasUnit={Boolean(p.unit_id)} cancelled={p.status === "cancelled"} onChanged={reload} onError={setError} /> : null}
        {tab === "deposit" ? (
          <>
            <p className={ui.notice}>{t("deposit.notice")}</p>
            <ProtocolForm p={p} fields={DEPOSIT_FIELDS} onSave={patchProtocol} disabled={contentDisabled} t={t} id="deposit" />
          </>
        ) : null}
        {tab === "internal" ? (
          <>
            <p className={ui.notice}>{t("internal.notice")}</p>
            <ProtocolForm p={p} fields={INTERNAL_FIELDS} onSave={patchProtocol} disabled={locked} t={t} id="internal" />
          </>
        ) : null}
        {(SECTIONS as readonly string[]).includes(tab) ? (
          <SectionList section={tab as Section} p={p} base={base} disabled={sectionDisabled(tab as Section)} onChanged={reload} onError={setError} t={t} />
        ) : null}
        {tab === "attachments" ? <Attachments p={p} base={base} disabled={contentDisabled} onChanged={reload} onError={setError} t={t} /> : null}
        {tab === "signatures" ? (
          <div className="flex flex-col gap-3">
            <p className={ui.notice}>{t("signature.consent")}</p>
            {p.signatures.length ? (
              <ul className="grid gap-2 sm:grid-cols-2">
                {p.signatures.map((s) => (
                  <li key={s.id} className={`${ui.card} flex items-start justify-between gap-2 ${s.invalidated_at ? "opacity-70" : ""}`}>
                    <div className="text-sm">
                      <div className="font-medium">{s.signer_name || t("signature.noName")}</div>
                      <div className="text-muted">
                        {s.signer_role ? t(`roles.${s.signer_role}`) : ""} · {formatDateTime(s.signed_at)}
                      </div>
                      {s.invalidated_at ? <div className={`${ui.badgeWarning} mt-1`}>{t("signature.invalidated", { date: formatDateTime(s.invalidated_at) })}</div> : null}
                      {/* eslint-disable-next-line @next/next/no-img-element -- protected same-origin blob, no optimizer */}
                      <img src={`/api/handover-files/documents/${s.document_id}/content`} alt="" className="mt-2 max-h-20 rounded border border-border bg-paper" />
                    </div>
                    {!locked ? (
                      <button
                        type="button"
                        className={ui.buttonSm}
                        onClick={async () => {
                          const ok = await confirm({ title: t("signature.confirmDeleteTitle"), text: t("signature.confirmDelete"), confirmLabel: t("delete"), danger: true });
                          if (!ok) return;
                          const res = await bff(`${base}/signatures/${s.id}`, { method: "DELETE" });
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
            {!locked ? (
              <div className={`${ui.card} flex flex-col gap-2`} data-testid="signature-buttons">
                {p.participants
                  .filter((x) => !p.signatures.some((s) => s.participant_id === x.id && !s.invalidated_at))
                  .map((x) => (
                    <button key={x.id} type="button" className={`${ui.primary} ${ui.actionFull}`} onClick={() => setSignFor(x)}>
                      {t("signature.of", { name: participantName(x) || t("signature.noName") })}
                    </button>
                  ))}
                <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={() => setSignFor(null)}>
                  {t("signature.additional")}
                </button>
              </div>
            ) : null}
            <SignatureSheet open={signFor !== undefined} onClose={() => setSignFor(undefined)} protocolId={p.id} kind={p.kind} participant={signFor ?? null} onSaved={reload} />
          </div>
        ) : null}
        {tab === "summary" ? (
          <div className="flex flex-col gap-4">
            <HandoverSummary p={p} mode={locked ? "locked" : "overview"} onGoTo={(s) => void switchTab(s)} />
            <HelperAccessSection base={base} disabled={locked} t={t} />
            {!locked ? (
              <div className={ui.formActions}>
                {showHints ? (
                  <button type="button" className={`${ui.primary} ${ui.actionFull}`} disabled={busy} onClick={() => complete(true)}>
                    {t("complete.force")}
                  </button>
                ) : (
                  <button type="button" className={`${ui.primary} ${ui.actionFull}`} disabled={busy} onClick={() => complete(false)}>
                    {t("complete.action")}
                  </button>
                )}
                <p className="self-center text-sm text-muted">{t("complete.help")}</p>
              </div>
            ) : null}
            {p.finalized ? (
              <div className={`${ui.card} flex flex-col gap-2`}>
                <h2 className={ui.h2}>{t("dispatch.title")}</h2>
                <p className="text-sm text-muted">{t("dispatch.help")}</p>
                <div>
                  <button type="button" className={ui.button} disabled={busy} onClick={dispatch}>
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
                      <Link href={`/makler/uebergabe/${v.id}`} className="hover:underline">
                        {t("versions.label", { version: v.version })}
                      </Link>{" "}
                      <span className="text-muted">
                        {t(`statusLabel.${v.status}`)}
                        {v.completed_at ? `, ${formatDateTime(v.completed_at)}` : ""}
                        {v.change_reason ? `, ${v.change_reason}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
                <label htmlFor="reason" className={ui.label}>
                  {t("versions.reason")}
                </label>
                <input id="reason" className={ui.input} value={reason} onChange={(e) => setReason(e.target.value)} />
                <div>
                  <button type="button" className={ui.button} disabled={busy} onClick={newVersion}>
                    {t("versions.create")}
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}

        <div className={ui.bottomBar} data-testid="step-footer">
          <button type="button" className={`${ui.button} ${ui.actionFull} flex-1`} onClick={() => switchTab(STEPS[Math.max(0, stepIndex - 1)]!)} disabled={stepIndex <= 0}>
            {t("stepPrev")}
          </button>
          <button type="button" className={`${ui.primary} ${ui.actionFull} flex-1`} onClick={() => switchTab(STEPS[Math.min(STEPS.length - 1, stepIndex + 1)]!)} disabled={stepIndex >= STEPS.length - 1}>
            {t("stepNext")}
          </button>
        </div>
        {confirmSheet}
      </div>
    </DirtyGuardContext.Provider>
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
  onSave: (body: Record<string, unknown>) => Promise<number>;
  disabled: boolean;
  t: (key: string) => string;
  id: string;
}) {
  const guard = useDirtyGuard();
  const [form, setForm] = useState<Record<string, string | boolean>>(() => Object.fromEntries(fields.map((f) => [f.name, valueOf(p as unknown as Record<string, unknown>, f)])));
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(false);
  useEffect(() => () => guard.setDirty(id, false), [guard, id]);
  return (
    <form
      className={`${ui.card} flex flex-col gap-3`}
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        const status = await onSave(toBody(form, fields));
        setBusy(false);
        if (status >= 200 && status < 300) {
          guard.setDirty(id, false);
          setRetry(false);
        } else setRetry(isRetryable(status));
      }}
    >
      <Fields
        id={id}
        fields={fields}
        form={form}
        onChange={(n, v) => {
          setForm((f) => ({ ...f, [n]: v }));
          guard.setDirty(id, true);
        }}
        disabled={disabled}
        t={t}
      />
      {!disabled ? (
        <div className={ui.bottomBar}>
          <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
            {retry ? t("retrySave") : t("save")}
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
  const { confirm, confirmSheet } = useConfirm();
  const [editing, setEditing] = useState<Item | "new" | null>(null);
  const [contactQuery, setContactQuery] = useState("");
  const [contacts, setContacts] = useState<{ id: string; display_name: string }[]>([]);
  const fields = FIELDS[section];
  const tRole = (r: string) => (r ? t(`roles.${r}`) : "");
  const withPhotos = PHOTO_SECTIONS.includes(section);

  async function searchContacts() {
    const res = await bff<{ items?: { id: string; display_name: string }[] } | { id: string; display_name: string }[]>(`/api/bff/contacts?q=${encodeURIComponent(contactQuery)}&page_size=10`);
    if (res.ok) setContacts(Array.isArray(res.data) ? res.data : (res.data.items ?? []));
  }

  async function addFromContact(contactId: string) {
    const res = await bff(`${base}/participants`, { method: "POST", body: JSON.stringify({ contact_id: contactId, role: "other" }) });
    if (res.ok) {
      setContacts([]);
      setContactQuery("");
      await onChanged();
    } else onError(res.message);
  }

  async function remove(item: Item) {
    const ok = await confirm({ title: t("delete"), text: t("confirmDelete"), confirmLabel: t("delete"), danger: true });
    if (!ok) return;
    const res = await bff(`${base}/${section}/${item.id}`, { method: "DELETE" });
    if (res.ok) await onChanged();
    else onError(res.message);
  }

  async function removePhoto(d: Doc) {
    const res = await bff(`${base}/documents/${d.id}`, { method: "DELETE" });
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
          <div className="flex flex-col gap-2 sm:flex-row">
            <input id="contact-search" className={ui.input} value={contactQuery} onChange={(e) => setContactQuery(e.target.value)} placeholder={t("participants.searchPlaceholder")} enterKeyHint="search" />
            <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={searchContacts} disabled={contactQuery.length < 2}>
              {t("participants.search")}
            </button>
          </div>
          {contacts.length ? (
            <ul className="flex flex-wrap gap-2">
              {contacts.map((c) => (
                <li key={c.id}>
                  <button type="button" className={ui.buttonSm} onClick={() => addFromContact(c.id)}>
                    + {c.display_name}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {items.length === 0 ? <p className="text-sm text-muted">{t("empty")}</p> : null}
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <li key={item.id} className={`${ui.card} flex flex-col gap-2`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium">{itemTitle(section, item, tRole)}</span>
              {!disabled ? (
                <span className="flex w-full gap-1 sm:w-auto">
                  <button type="button" className={ui.buttonSm} onClick={() => setEditing(editing && editing !== "new" && editing.id === item.id ? null : item)}>
                    {t("edit")}
                  </button>
                  <button type="button" className={`${ui.buttonSm} ml-auto text-danger-fg`} onClick={() => remove(item)}>
                    {t("delete")}
                  </button>
                </span>
              ) : null}
            </div>
            {section === "participants" && item.contact_id ? <PortalAccessBox base={base} item={item} disabled={disabled} onChanged={onChanged} onError={onError} t={t} /> : null}
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
            {withPhotos ? (
              <Photos key={item.id} base={base} section={section} itemId={item.id} itemTitle={itemTitle(section, item, tRole)} docs={p.documents.filter((d) => d.item_id === item.id)} disabled={disabled} onChanged={onChanged} onError={onError} onRemove={removePhoto} t={t} />
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
            <button type="button" className={`${ui.primary} ${ui.actionFull}`} onClick={() => setEditing("new")}>
              {t(`add.${section}`)}
            </button>
          </div>
        )
      ) : null}
      {confirmSheet}
    </div>
  );
}

type UploadState = "waiting" | "uploading" | "done" | "failed";
type PendingFile = { file: File; state: UploadState };

/** Sequential upload of the picked photos of one entry (FormData with file, section and
 *  item_id); each file gets its own state line. Files are downscaled client side first. */
async function uploadFiles(base: string, section: Section, itemId: string, files: PendingFile[], update: (next: PendingFile[]) => void, only?: number): Promise<PendingFile[]> {
  let current = [...files];
  for (let i = 0; i < current.length; i += 1) {
    if (only !== undefined && i !== only) continue;
    if (current[i]!.state === "done") continue;
    current = current.map((f, j) => (j === i ? { ...f, state: "uploading" } : f));
    update(current);
    const data = new FormData();
    data.append("file", await downscale(current[i]!.file));
    data.append("section", section);
    data.append("item_id", itemId);
    const res = await bff(`${base}/documents`, { method: "POST", body: data });
    current = current.map((f, j) => (j === i ? { ...f, state: res.ok ? "done" : "failed" } : f));
    update(current);
  }
  return current;
}

function UploadList({ files, onRetry, t }: { files: PendingFile[]; onRetry: (index: number) => void; t: (key: string) => string }) {
  return (
    <ul className="flex flex-col gap-1 text-sm" data-testid="upload-status">
      {files.map((f, i) => (
        <li key={`${f.file.name}-${i}`} className="flex flex-wrap items-center justify-between gap-2">
          <span className="truncate">{f.file.name}</span>
          <span className="flex items-center gap-2">
            <span className={f.state === "failed" ? ui.badgeDanger : f.state === "done" ? ui.badgeSuccess : ui.badge} data-state={f.state}>
              {t(`photos.status.${f.state}`)}
            </span>
            {f.state === "failed" ? (
              <button type="button" className={ui.buttonSm} onClick={() => onRetry(i)}>
                {t("photos.retry")}
              </button>
            ) : null}
          </span>
        </li>
      ))}
    </ul>
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
  const guard = useDirtyGuard();
  const id = item ? item.id : `new-${section}`;
  const [form, setForm] = useState<Record<string, string | boolean>>(() => Object.fromEntries(fields.map((f) => [f.name, item ? valueOf(item, f) : f.type === "checkbox" ? false : ""])));
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(false);
  const [photos, setPhotos] = useState<File[]>([]);
  const [uploads, setUploads] = useState<PendingFile[] | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const captureFirst = item === null && PHOTO_SECTIONS.includes(section);
  useEffect(() => () => guard.setDirty(id, false), [guard, id]);

  async function finish() {
    guard.setDirty(id, false);
    await onDone();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    onError(null);
    let targetId = createdId;
    if (!targetId) {
      const res = await bff<{ id: string }>(item ? `${base}/${section}/${item.id}` : `${base}/${section}`, {
        method: item ? "PATCH" : "POST",
        body: JSON.stringify(toBody(form, fields)),
      });
      if (!res.ok) {
        setBusy(false);
        setRetry(isRetryable(res.status));
        onError(res.message);
        return;
      }
      targetId = item ? item.id : res.data.id;
      setCreatedId(targetId);
    }
    if (captureFirst && photos.length) {
      const pending: PendingFile[] = uploads ?? photos.map((file) => ({ file, state: "waiting" }));
      const result = await uploadFiles(base, section, targetId, pending, setUploads);
      setBusy(false);
      if (result.some((f) => f.state === "failed")) return;
    } else setBusy(false);
    await finish();
  }

  async function retryOne(index: number) {
    if (!uploads || !createdId) return;
    setBusy(true);
    const result = await uploadFiles(base, section, createdId, uploads, setUploads, index);
    setBusy(false);
    if (!result.some((f) => f.state === "failed")) await finish();
  }

  return (
    <form className="flex flex-col gap-3" onSubmit={submit} data-testid={`item-form-${section}`}>
      <Fields
        id={id}
        fields={fields}
        form={form}
        onChange={(n, v) => {
          setForm((f) => ({ ...f, [n]: v }));
          guard.setDirty(id, true);
        }}
        disabled={createdId !== null}
        section={section}
        rooms={rooms}
        t={t}
      />
      {captureFirst && uploads === null ? (
        <PhotoPicker
          files={photos}
          onChange={(files) => {
            setPhotos(files);
            guard.setDirty(id, true);
          }}
          disabled={busy}
        />
      ) : null}
      {uploads ? (
        <div className="flex flex-col gap-2">
          <UploadList files={uploads} onRetry={retryOne} t={t} />
          {uploads.some((f) => f.state === "failed") ? <p className="text-sm text-muted">{t("photos.failedHint")}</p> : null}
        </div>
      ) : null}
      <div className={ui.bottomBar}>
        {uploads?.some((f) => f.state === "failed") ? (
          <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={finish} disabled={busy}>
            {t("photos.later")}
          </button>
        ) : (
          <>
            <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
              {retry ? t("retrySave") : t("save")}
            </button>
            <button type="button" className={`${ui.button} ${ui.actionFull}`} onClick={finish} disabled={busy}>
              {t("cancel")}
            </button>
          </>
        )}
      </div>
    </form>
  );
}

function Photos({
  base,
  section,
  itemId,
  itemTitle: title,
  docs,
  disabled,
  onChanged,
  onError,
  onRemove,
  t,
}: {
  base: string;
  section: Section;
  itemId: string;
  itemTitle: string;
  docs: Doc[];
  disabled: boolean;
  onChanged: () => Promise<void>;
  onError: (m: string | null) => void;
  onRemove: (d: Doc) => Promise<void>;
  t: (key: string) => string;
}) {
  const [picked, setPicked] = useState<File[]>([]);
  const [uploads, setUploads] = useState<PendingFile[] | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(files: PendingFile[], only?: number) {
    setBusy(true);
    onError(null);
    const result = await uploadFiles(base, section, itemId, files, setUploads, only);
    setBusy(false);
    if (result.some((f) => f.state === "failed")) return;
    setUploads(null);
    setPicked([]);
    await onChanged();
  }

  return (
    <div className="flex flex-col gap-2">
      <PhotoStrip docs={docs} itemTitle={title} onRemove={disabled ? undefined : onRemove} />
      {!disabled ? (
        <>
          {uploads === null ? <PhotoPicker files={picked} onChange={setPicked} disabled={busy} /> : null}
          {uploads ? <UploadList files={uploads} onRetry={(i) => run(uploads, i)} t={t} /> : null}
          {picked.length && uploads === null ? (
            <div>
              <button type="button" className={`${ui.primary} ${ui.actionFull}`} disabled={busy} onClick={() => run(picked.map((file) => ({ file, state: "waiting" })))}>
                {t("photos.add")}
              </button>
            </div>
          ) : null}
          {uploads?.some((f) => f.state === "failed") ? (
            <div>
              <button
                type="button"
                className={`${ui.button} ${ui.actionFull}`}
                onClick={async () => {
                  setUploads(null);
                  setPicked([]);
                  await onChanged();
                }}
              >
                {t("photos.later")}
              </button>
            </div>
          ) : null}
        </>
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
  const { confirm, confirmSheet } = useConfirm();
  const [busy, setBusy] = useState(false);
  const docs = p.documents.filter((d) => d.kind === "attachment" || (d.kind === "photo" && !d.item_id));
  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    for (const file of Array.from(files)) {
      const data = new FormData();
      data.append("file", file.type.startsWith("image/") ? await downscale(file) : file);
      const res = await bff(`${base}/documents`, { method: "POST", body: data });
      if (!res.ok) onError(res.message);
    }
    setBusy(false);
    await onChanged();
  }
  return (
    <div className={`${ui.card} flex flex-col gap-3`}>
      {docs.length === 0 ? <p className="text-sm text-muted">{t("empty")}</p> : null}
      <ul className="flex flex-col gap-1 text-sm">
        {docs.map((d) => (
          <li key={d.id} className="flex items-center justify-between gap-2">
            <a href={`/api/handover-files/documents/${d.id}/content`} download={d.filename} className="inline-flex min-h-11 items-center underline">
              {d.filename}
            </a>
            <span className="text-muted">{Math.round(d.size / 1024)} KB</span>
            {!disabled ? (
              <button
                type="button"
                className={ui.buttonSm}
                onClick={async () => {
                  const ok = await confirm({ title: t("photos.confirmRemoveTitle"), text: t("photos.confirmRemove"), confirmLabel: t("delete"), danger: true });
                  if (!ok) return;
                  const res = await bff(`${base}/documents/${d.id}`, { method: "DELETE" });
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
        <label className={`${ui.button} ${ui.actionFull} cursor-pointer`}>
          {busy ? t("photos.uploading") : t("attachments.add")}
          <input type="file" accept="image/jpeg,image/png,image/heic,image/heif,application/pdf" multiple className="sr-only" onChange={(e) => upload(e.target.files)} disabled={busy} />
        </label>
      ) : null}
      {confirmSheet}
    </div>
  );
}
