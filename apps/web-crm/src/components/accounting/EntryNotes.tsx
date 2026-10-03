"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";
import { formatDateTime as formatBerlinDateTime } from "@/lib/format";

export type EntryNote = {
  id: string;
  note_key: string;
  version: number;
  supersedes_id: string | null;
  body: string;
  created_at: string;
  created_by: string | null;
  is_current: boolean;
};

function formatDateTime(iso: string): string {
  return formatBerlinDateTime(iso);
}

/** Versioned notes on a posted entry (GA05-02, B03): kept apart from the financial content,
 *  append only. A change creates a new version; earlier versions stay visible. Loads on demand. */
export function EntryNotes({ ledgerId, entryId, canWrite }: { ledgerId: string; entryId: string; canWrite: boolean }) {
  const t = useTranslations("Bookkeeping.notes");
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState<EntryNote[] | null>(null);
  const [body, setBody] = useState("");
  const [supersedes, setSupersedes] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const url = `/api/bff/accounting/ledgers/${ledgerId}/entries/${entryId}/notes`;

  const load = async () => {
    const res = await bff<EntryNote[]>(url);
    if (res.ok) setNotes(res.data ?? []);
    else setError(res.message);
  };

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && notes === null) void load();
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<EntryNote>(url, { method: "POST", body: JSON.stringify({ body: body.trim(), supersedes_id: supersedes }) });
    setBusy(false);
    if (res.ok) {
      setBody("");
      setSupersedes(null);
      await load();
    } else setError(res.message);
  };

  return (
    <span className="flex flex-col gap-1">
      <button type="button" className={ui.buttonSm} aria-expanded={open} onClick={toggle}>
        {t("toggle")}
      </button>
      {open ? (
        <span className="flex flex-col gap-1">
          {notes && notes.length === 0 ? <span className={ui.small}>{t("empty")}</span> : null}
          {notes?.map((n) => (
            <span key={n.id} className={n.is_current ? "" : "line-through opacity-70"} data-testid="entry-note">
              <span className={ui.small}>
                {t("version", { version: n.version, at: formatDateTime(n.created_at) })}
                {n.is_current ? "" : ` (${t("superseded")})`}
              </span>{" "}
              <span>{n.body}</span>
              {canWrite && n.is_current ? (
                <button
                  type="button"
                  className={ui.buttonSm}
                  onClick={() => {
                    setSupersedes(n.id);
                    setBody(n.body);
                  }}
                >
                  {t("newVersion")}
                </button>
              ) : null}
            </span>
          ))}
          {canWrite ? (
            <form
              aria-label={t("form")}
              className="flex flex-col gap-1"
              onSubmit={(e) => {
                e.preventDefault();
                void submit();
              }}
            >
              <label className={ui.label} htmlFor={`note-${entryId}`}>
                {supersedes ? t("labelVersion") : t("label")}
              </label>
              <textarea id={`note-${entryId}`} required maxLength={4000} className={ui.input} value={body} onChange={(e) => setBody(e.target.value)} />
              <button type="submit" className={ui.buttonSm} disabled={busy || body.trim().length === 0}>
                {t("save")}
              </button>
            </form>
          ) : null}
          <span className={ui.small}>{t("hint")}</span>
        </span>
      ) : null}
      {error ? (
        <span role="alert" className={ui.error}>
          {error}
        </span>
      ) : null}
    </span>
  );
}
