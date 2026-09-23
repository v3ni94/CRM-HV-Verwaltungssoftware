"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

type Note = components["schemas"]["NoteOut"];

export function NotesPanel({ contactId, notes }: { contactId: string; notes: Note[] }) {
  const t = useTranslations("Contacts");
  const router = useRouter();
  const [body, setBody] = useState("");
  const [category, setCategory] = useState("");
  const [pinned, setPinned] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!body.trim()) {
      setError(t("notes.required"));
      return;
    }
    setBusy(true);
    setError(null);
    const result = await bff(`/api/bff/contacts/${contactId}/notes`, {
      method: "POST",
      body: JSON.stringify({ body: body.trim(), category: category.trim() || null, pinned }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setBody("");
    setCategory("");
    setPinned(false);
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      {notes.length ? (
        <ul className="flex flex-col gap-2">
          {notes.map((note) => (
            <li key={note.id} className={ui.card}>
              <p className="mb-1 text-xs text-muted">
                {formatDateTime(note.created_at)}
                {note.category ? `, ${note.category}` : ""}
                {note.pinned ? `, ${t("notes.pinned")}` : ""}
              </p>
              <p className="whitespace-pre-wrap text-sm">{note.body}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted">{t("none")}</p>
      )}
      <form onSubmit={submit} className="flex flex-col gap-2" aria-label={t("notes.add")}>
        <h2 className="text-sm font-semibold">{t("notes.add")}</h2>
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        <label htmlFor="note-body" className={ui.label}>
          {t("notes.body")}
        </label>
        <textarea id="note-body" rows={3} maxLength={20000} className={ui.input} value={body} onChange={(e) => setBody(e.target.value)} />
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="note-category" className={ui.label}>
              {t("notes.category")}
            </label>
            <input id="note-category" maxLength={63} className={ui.input} value={category} onChange={(e) => setCategory(e.target.value)} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={pinned} onChange={(e) => setPinned(e.target.checked)} />
            {t("notes.pinned")}
          </label>
          <button type="submit" className={ui.primary} disabled={busy}>
            {t("notes.save")}
          </button>
        </div>
      </form>
    </div>
  );
}
