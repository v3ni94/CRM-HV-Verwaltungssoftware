"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const MAX_PHOTOS = 10;

/** Neue Schadensmeldung (M21, A55): Titel, Beschreibung und optional Fotos. Fotos werden
 *  zuerst über den Portal-Upload angelegt (die API entfernt Aufnahmedaten) und dann als
 *  Dokumentverknüpfung `document_ids` an die Meldung übergeben. */
export function NewTicket() {
  const t = useTranslations("Tickets");
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [photos, setPhotos] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (title.trim().length < 3) {
      setError(t("titleRequired"));
      return;
    }
    if (description.trim().length < 3) {
      setError(t("descriptionRequired"));
      return;
    }
    setBusy(true);
    const documentIds: string[] = [];
    for (const photo of photos.slice(0, MAX_PHOTOS)) {
      const form = new FormData();
      form.append("file", photo);
      const upload = await bff<{ id: string }>("/api/bff/portal/uploads", { method: "POST", body: form });
      if (!upload.ok) {
        setBusy(false);
        setError(upload.message);
        return;
      }
      documentIds.push(upload.data.id);
    }
    const result = await bff<{ id: string }>("/api/bff/portal/tickets", {
      method: "POST",
      body: JSON.stringify({ title: title.trim(), description: description.trim(), document_ids: documentIds }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setDone(true);
    setTitle("");
    setDescription("");
    setPhotos([]);
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} noValidate aria-busy={busy} aria-labelledby="ticket-new-title" className={`${ui.card} flex flex-col gap-3`}>
      <h2 id="ticket-new-title" className={ui.h2}>
        {t("new")}
      </h2>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {done ? (
        <p role="status" className={ui.success}>
          {t("submitted")}
        </p>
      ) : null}
      <div>
        <label htmlFor="ticket-title" className={ui.label}>
          {t("titleField")}
        </label>
        <input id="ticket-title" className={ui.input} aria-required="true" value={title} onChange={(e) => setTitle(e.target.value)} />
      </div>
      <div>
        <label htmlFor="ticket-description" className={ui.label}>
          {t("description")}
        </label>
        <textarea
          id="ticket-description"
          rows={4}
          aria-required="true"
          className={ui.input}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <div>
        <label htmlFor="ticket-photo" className={ui.label}>
          {t("photo")}
        </label>
        <input
          id="ticket-photo"
          type="file"
          aria-describedby="ticket-photo-hint"
          accept="image/jpeg,image/png"
          multiple
          className={ui.input}
          onChange={(e) => setPhotos(Array.from(e.target.files ?? []).slice(0, MAX_PHOTOS))}
        />
        <p id="ticket-photo-hint" className={ui.help}>
          {t("photoHint")}
        </p>
      </div>
      <div className={ui.formActions}>
        <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
          {t("submit")}
        </button>
      </div>
    </form>
  );
}
