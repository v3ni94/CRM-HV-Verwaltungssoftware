"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Schwarzes Brett je Objekt (M21-01, A54): notices of the management with validity period and
 *  audience, shown in the portal to tenants and owners of the property. "Beenden" removes a
 *  notice from the portal at once; the record stays. */
export type PropertyNotice = {
  id: string;
  property_id: string;
  title: string;
  body: string;
  valid_from: string;
  valid_to: string | null;
  audience: "tenant" | "owner" | "all";
  document_id: string | null;
  ended_at: string | null;
  is_current: boolean;
  created_at: string;
};

type Draft = {
  title: string;
  body: string;
  valid_from: string;
  valid_to: string;
  audience: PropertyNotice["audience"];
  document_id: string;
};

const AUDIENCES: PropertyNotice["audience"][] = ["all", "tenant", "owner"];
const UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

function today(): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Berlin" }).format(new Date());
}

function emptyDraft(): Draft {
  return { title: "", body: "", valid_from: today(), valid_to: "", audience: "all", document_id: "" };
}

function toDraft(n: PropertyNotice): Draft {
  return {
    title: n.title,
    body: n.body,
    valid_from: n.valid_from,
    valid_to: n.valid_to ?? "",
    audience: n.audience,
    document_id: n.document_id ?? "",
  };
}

export function PropertyNotices({ propertyId }: { propertyId: string }) {
  const t = useTranslations("Notices");
  const [rows, setRows] = useState<PropertyNotice[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<"new" | string | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft());
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const res = await bff<PropertyNotice[]>(`/api/bff/properties/${propertyId}/notices`);
    if (res.ok) {
      setRows(res.data);
      setError(null);
    } else {
      setRows([]);
      setError(res.message);
    }
  }, [propertyId]);

  useEffect(() => {
    void load();
  }, [load]);

  function startNew() {
    setDraft(emptyDraft());
    setFormError(null);
    setEditing("new");
  }

  function startEdit(n: PropertyNotice) {
    setDraft(toDraft(n));
    setFormError(null);
    setEditing(n.id);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.title.trim()) return setFormError(t("errors.title"));
    if (!draft.body.trim()) return setFormError(t("errors.body"));
    if (!draft.valid_from) return setFormError(t("errors.validFrom"));
    if (draft.valid_to && draft.valid_to < draft.valid_from) return setFormError(t("errors.validTo"));
    if (draft.document_id && !UUID.test(draft.document_id.trim())) return setFormError(t("errors.document"));
    setBusy(true);
    setFormError(null);
    const isNew = editing === "new";
    const payload = isNew
      ? {
          title: draft.title.trim(),
          body: draft.body.trim(),
          valid_from: draft.valid_from,
          valid_to: draft.valid_to || null,
          audience: draft.audience,
          document_id: draft.document_id.trim() || null,
        }
      : {
          title: draft.title.trim(),
          body: draft.body.trim(),
          valid_from: draft.valid_from,
          ...(draft.valid_to ? { valid_to: draft.valid_to } : { clear_valid_to: true }),
          audience: draft.audience,
          ...(draft.document_id.trim() ? { document_id: draft.document_id.trim() } : { clear_document: true }),
        };
    const res = isNew
      ? await bff<PropertyNotice>(`/api/bff/properties/${propertyId}/notices`, { method: "POST", body: JSON.stringify(payload) })
      : await bff<PropertyNotice>(`/api/bff/notices/${editing}`, { method: "PATCH", body: JSON.stringify(payload) });
    setBusy(false);
    if (!res.ok) return setFormError(res.message);
    setEditing(null);
    await load();
  }

  async function end(n: PropertyNotice) {
    if (!window.confirm(t("endConfirm", { title: n.title }))) return;
    setBusy(true);
    const res = await bff<PropertyNotice>(`/api/bff/notices/${n.id}/end`, { method: "POST" });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    await load();
  }

  const field = (key: keyof Draft) => (event: { target: { value: string } }) =>
    setDraft((d) => ({ ...d, [key]: event.target.value }));

  return (
    <section className="flex flex-col gap-2" data-testid="property-notices">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={ui.h2}>{t("title")}</h2>
        {editing === null ? (
          <button type="button" className={ui.buttonSm} onClick={startNew}>
            {t("create")}
          </button>
        ) : null}
      </div>
      <p className="text-sm text-muted">{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}

      {editing !== null ? (
        <form onSubmit={submit} className={`${ui.card} flex flex-col gap-3`} aria-label={editing === "new" ? t("create") : t("edit")}>
          <div>
            <label htmlFor="notice-title" className={ui.label}>
              {t("fields.title")}
            </label>
            <input id="notice-title" className={ui.input} value={draft.title} onChange={field("title")} maxLength={300} />
          </div>
          <div>
            <label htmlFor="notice-body" className={ui.label}>
              {t("fields.body")}
            </label>
            <textarea id="notice-body" className={ui.input} rows={5} value={draft.body} onChange={field("body")} />
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label htmlFor="notice-from" className={ui.label}>
                {t("fields.validFrom")}
              </label>
              <input id="notice-from" type="date" className={ui.input} value={draft.valid_from} onChange={field("valid_from")} />
            </div>
            <div>
              <label htmlFor="notice-to" className={ui.label}>
                {t("fields.validTo")}
              </label>
              <input id="notice-to" type="date" className={ui.input} value={draft.valid_to} onChange={field("valid_to")} />
            </div>
            <div>
              <label htmlFor="notice-audience" className={ui.label}>
                {t("fields.audience")}
              </label>
              <select id="notice-audience" className={ui.input} value={draft.audience} onChange={field("audience")}>
                {AUDIENCES.map((a) => (
                  <option key={a} value={a}>
                    {t(`audience.${a}`)}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label htmlFor="notice-document" className={ui.label}>
              {t("fields.document")}
            </label>
            <input id="notice-document" className={ui.input} value={draft.document_id} onChange={field("document_id")} placeholder={t("fields.documentHint")} />
          </div>
          {formError ? (
            <p role="alert" className={ui.alert}>
              {formError}
            </p>
          ) : null}
          <div className={ui.formActions}>
            <button type="submit" className={ui.primary} disabled={busy}>
              {editing === "new" ? t("save") : t("saveChanges")}
            </button>
            <button type="button" className={ui.button} disabled={busy} onClick={() => setEditing(null)}>
              {t("cancel")}
            </button>
          </div>
        </form>
      ) : null}

      {rows === null ? (
        <p className="text-sm text-muted">{t("loading")}</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {rows.map((n) => (
            <li key={n.id} className={`${ui.card} flex flex-col gap-1`}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="flex flex-col gap-0.5">
                  <span className="font-medium">{n.title}</span>
                  <span className="text-xs text-muted">
                    {t("validity", { from: formatDate(n.valid_from), to: n.valid_to ? formatDate(n.valid_to) : t("openEnd") })}
                    {" · "}
                    {t(`audience.${n.audience}`)}
                    {n.document_id ? ` · ${t("withDocument")}` : ""}
                  </span>
                </div>
                <span className={n.ended_at ? ui.badge : n.is_current ? ui.badgeSuccess : ui.badgeWarning}>
                  {n.ended_at ? t("status.ended") : n.is_current ? t("status.current") : t("status.inactive")}
                </span>
              </div>
              <p className="whitespace-pre-wrap text-sm">{n.body}</p>
              {n.ended_at ? null : (
                <div className="flex flex-wrap gap-2">
                  <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => startEdit(n)}>
                    {t("edit")}
                  </button>
                  <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void end(n)}>
                    {t("end")}
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
